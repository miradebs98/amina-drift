import type { CustomerCase } from "./types";

// The "live twin" (Layer-1 / PUBLIC) view of each contradicted belief, grounded in
// the cited evidence. Presence in this map = the onboarding belief is contradicted.
// Authored by Giacomo (UI) to render the engine's contradictions; each `now` summarizes
// the linked EvidenceEvents. Meridian is simulated; Coinbase evidence is real/citable.
type NowEntry = { now: string; evidenceIds: string[] };

const NOW_MAP: Record<string, Record<string, NowEntry>> = {
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
  // Authored "now" summaries (curated polish) take priority; otherwise fall back to the engine's
  // own per-belief drift (assertion_drift) so EVERY customer's twin-diff is correct from real output.
  const map = NOW_MAP[c.customer.customer_id] ?? {};
  const drift = new Map((c.assertion_drift ?? []).map((d) => [d.assertion_id, d]));
  const rows: DiffRow[] = c.customer.assertions
    .filter((a) => !EXCLUDE.has(a.predicate))
    .map((a) => {
      const hit = map[a.id];
      const ad = drift.get(a.id);
      const engineChanged = Boolean(ad && (ad.status === "contradicted" || ad.risk_impact > 0.05));
      const now =
        hit?.now ??
        (engineChanged ? ad?.why?.join("; ") || "Contradicted by public evidence" : "No material change — re-verified");
      return {
        assertionId: a.id,
        predicate: a.predicate,
        then: a.value,
        now,
        evidenceIds: hit?.evidenceIds ?? ad?.evidence_ids ?? [],
        changed: Boolean(hit) || engineChanged,
      };
    });
  // changed rows first
  rows.sort((a, b) => Number(b.changed) - Number(a.changed));
  return { rows, changed: rows.filter((r) => r.changed).length, total: rows.length };
}
