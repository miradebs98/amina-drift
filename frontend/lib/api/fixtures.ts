// Fixtures data source — reads the committed JSON mocks so the demo runs fully
// offline. Same function signatures as the live client in client.ts.
// Generated from the backend (Apertus) so fixtures match the validated roster.

import type { Customer, EvidenceEvent, DriftAlert, CustomerCase } from "@/lib/types";

import coinbaseCustomer from "@/mock/customers/coinbase.json";
import binanceCustomer from "@/mock/customers/binance.json";
import hashkeyCustomer from "@/mock/customers/hashkey.json";
import geberitCustomer from "@/mock/customers/geberit.json";
import coinbaseEvents from "@/mock/events/coinbase.json";
import binanceEvents from "@/mock/events/binance.json";
import hashkeyEvents from "@/mock/events/hashkey.json";
import geberitEvents from "@/mock/events/geberit.json";
import coinbaseAlert from "@/mock/alerts/coinbase.json";
import binanceAlert from "@/mock/alerts/binance.json";
import hashkeyAlert from "@/mock/alerts/hashkey.json";
import geberitAlert from "@/mock/alerts/geberit.json";
import coinbaseNetwork from "@/mock/network/coinbase.json";
import binanceNetwork from "@/mock/network/binance.json";
import hashkeyNetwork from "@/mock/network/hashkey.json";
import geberitNetwork from "@/mock/network/geberit.json";
import coinbaseInsights from "@/mock/insights/coinbase.json";
import binanceInsights from "@/mock/insights/binance.json";
import hashkeyInsights from "@/mock/insights/hashkey.json";
import geberitInsights from "@/mock/insights/geberit.json";

type EventsFile = { events: EvidenceEvent[] };
type AlertFile = { alert: DriftAlert };
type Insights = Pick<
  CustomerCase,
  "dimensions_drifted" | "breadth" | "assertion_drift" | "timeline" | "final_score" | "final_tier"
>;

const CASES: Record<string, CustomerCase> = {
  "coinbase-global": {
    customer: coinbaseCustomer as unknown as Customer,
    events: (coinbaseEvents as unknown as EventsFile).events,
    alert: (coinbaseAlert as unknown as AlertFile).alert,
    ...(coinbaseInsights as unknown as Insights),
  },
  binance: {
    customer: binanceCustomer as unknown as Customer,
    events: (binanceEvents as unknown as EventsFile).events,
    alert: (binanceAlert as unknown as AlertFile).alert,
    ...(binanceInsights as unknown as Insights),
  },
  "hashkey-group": {
    customer: hashkeyCustomer as unknown as Customer,
    events: (hashkeyEvents as unknown as EventsFile).events,
    alert: (hashkeyAlert as unknown as AlertFile).alert,
    ...(hashkeyInsights as unknown as Insights),
  },
  geberit: {
    customer: geberitCustomer as unknown as Customer,
    events: (geberitEvents as unknown as EventsFile).events,
    alert: (geberitAlert as unknown as AlertFile).alert,
    ...(geberitInsights as unknown as Insights),
  },
};

// network graph per customer (backend/network/graph.py shape)
const NETWORK: Record<string, unknown> = {
  "coinbase-global": coinbaseNetwork,
  binance: binanceNetwork,
  "hashkey-group": hashkeyNetwork,
  geberit: geberitNetwork,
};

const ORDER = ["coinbase-global", "binance", "hashkey-group", "geberit"];

export async function listCases(): Promise<CustomerCase[]> {
  return ORDER.map((id) => CASES[id]);
}

export async function getCase(customerId: string): Promise<CustomerCase | null> {
  return CASES[customerId] ?? null;
}

export async function getNetwork(customerId: string): Promise<unknown | null> {
  return NETWORK[customerId] ?? null;
}
