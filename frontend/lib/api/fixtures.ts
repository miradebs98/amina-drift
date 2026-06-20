// Fixtures data source — reads the committed JSON mocks so the demo runs fully
// offline. Same function signatures as the live client in client.ts.

import type { Customer, EvidenceEvent, DriftAlert, CustomerCase } from "@/lib/types";

import meridianCustomer from "@/mock/customers/meridian-sands.json";
import coinbaseCustomer from "@/mock/customers/coinbase.json";
import hashkeyCustomer from "@/mock/customers/hashkey.json";
import meridianEvents from "@/mock/events/meridian.json";
import coinbaseEvents from "@/mock/events/coinbase.json";
import hashkeyEvents from "@/mock/events/hashkey.json";
import meridianAlert from "@/mock/alerts/meridian.json";
import coinbaseAlert from "@/mock/alerts/coinbase.json";
import hashkeyAlert from "@/mock/alerts/hashkey.json";
import meridianNetwork from "@/mock/network/meridian.json";
import coinbaseNetwork from "@/mock/network/coinbase.json";
import hashkeyNetwork from "@/mock/network/hashkey.json";
import meridianInsights from "@/mock/insights/meridian.json";
import coinbaseInsights from "@/mock/insights/coinbase.json";
import hashkeyInsights from "@/mock/insights/hashkey.json";

type EventsFile = { events: EvidenceEvent[] };
type AlertFile = { alert: DriftAlert };
type Insights = Pick<CustomerCase, "dimensions_drifted" | "breadth" | "assertion_drift">;

const CASES: Record<string, CustomerCase> = {
  "meridian-sands": {
    customer: meridianCustomer as unknown as Customer,
    events: (meridianEvents as unknown as EventsFile).events,
    alert: (meridianAlert as unknown as AlertFile).alert,
    ...(meridianInsights as unknown as Insights),
  },
  "coinbase-global": {
    customer: coinbaseCustomer as unknown as Customer,
    events: (coinbaseEvents as unknown as EventsFile).events,
    alert: (coinbaseAlert as unknown as AlertFile).alert,
    ...(coinbaseInsights as unknown as Insights),
  },
  "hashkey-group": {
    customer: hashkeyCustomer as unknown as Customer,
    events: (hashkeyEvents as unknown as EventsFile).events,
    alert: (hashkeyAlert as unknown as AlertFile).alert,
    ...(hashkeyInsights as unknown as Insights),
  },
};

// network graph per customer (backend/network/graph.py shape)
const NETWORK: Record<string, unknown> = {
  "meridian-sands": meridianNetwork,
  "coinbase-global": coinbaseNetwork,
  "hashkey-group": hashkeyNetwork,
};

const ORDER = ["meridian-sands", "hashkey-group", "coinbase-global"];

export async function listCases(): Promise<CustomerCase[]> {
  return ORDER.map((id) => CASES[id]);
}

export async function getCase(customerId: string): Promise<CustomerCase | null> {
  return CASES[customerId] ?? null;
}

export async function getNetwork(customerId: string): Promise<unknown | null> {
  return NETWORK[customerId] ?? null;
}
