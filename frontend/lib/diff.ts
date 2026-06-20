import type { CustomerCase } from "./types";

// The "live twin" (Layer-1 / PUBLIC) view of each contradicted belief, grounded in
// the cited evidence. Presence in this map = the onboarding belief is contradicted.
// Authored by Giacomo (UI) to render the engine's contradictions; each `now` summarizes
// the linked EvidenceEvents. Meridian is simulated; Coinbase evidence is real/citable.
type NowEntry = { now: string; evidenceIds: string[] };

const NOW_MAP: Record<string, Record<string, NowEntry>> = {
  "meridian-sands": {
    MS1: { now: "Web3 / crypto trading infrastructure", evidenceIds: ["MS-EV1", "MS-EV5"] },
    MS2: { now: "UAE + new offshore entity (BVI)", evidenceIds: ["MS-EV2"] },
    MS3: { now: "+ Crescent Sovereign Partners 30% (PEP-adjacent)", evidenceIds: ["MS-EV3"] },
    MS4: { now: "Retail crypto brokerage product launched", evidenceIds: ["MS-EV5"] },
    MS5: { now: "Corporate crypto treasury adopted (BTC/ETH/USDC)", evidenceIds: ["MS-EV8"] },
    MS7: { now: "Increasingly crypto trading proceeds", evidenceIds: ["MS-EV5", "MS-EV6"] },
    MS8: { now: "~6M AED/mo — ~12× the onboarding envelope", evidenceIds: ["MS-EV6"] },
    MS9: { now: "Regulated activity offered without FSRA authorisation", evidenceIds: ["MS-EV5"] },
    MS10: { now: "PEP-adjacent UBO via the new investor", evidenceIds: ["MS-EV3"] },
    MS12: { now: "Co-founder named in a fraud investigation", evidenceIds: ["MS-EV7"] },
  },
  "coinbase-global": {
    CB1: { now: "+ derivatives (Deribit), L2 (Base), staking", evidenceIds: ["CB-EV3", "CB-EV6"] },
    CB4: { now: "Global, incl. EU (MiCA) & Germany", evidenceIds: ["CB-EV5"] },
    CB5: { now: "EU MiCA + BaFin custody licences added", evidenceIds: ["CB-EV2", "CB-EV5"] },
    CB7: { now: "SEC suit (2023) → later dismissed (2025)", evidenceIds: ["CB-EV4", "CB-EV7"] },
  },
};

const EXCLUDE = new Set(["risk_score", "risk_tier"]);

export type DiffRow = {
  assertionId: string;
  predicate: string;
  then: string;
  now: string;
  evidenceIds: string[];
  changed: boolean;
};

export function getTwinDiff(c: CustomerCase): { rows: DiffRow[]; changed: number; total: number } {
  const map = NOW_MAP[c.customer.customer_id] ?? {};
  const rows: DiffRow[] = c.customer.assertions
    .filter((a) => !EXCLUDE.has(a.predicate))
    .map((a) => {
      const hit = map[a.id];
      return {
        assertionId: a.id,
        predicate: a.predicate,
        then: a.value,
        now: hit?.now ?? "No material change — re-verified",
        evidenceIds: hit?.evidenceIds ?? [],
        changed: Boolean(hit),
      };
    });
  // changed rows first
  rows.sort((a, b) => Number(b.changed) - Number(a.changed));
  return { rows, changed: rows.filter((r) => r.changed).length, total: rows.length };
}
