// Fixtures data source — reads the committed JSON mocks so the demo runs fully
// offline. Same function signatures as the (future) live client in client.ts.

import type { Customer, EvidenceEvent, DriftAlert, CustomerCase } from "@/lib/types";

import meridianCustomer from "@/mock/customers/meridian-sands.json";
import coinbaseCustomer from "@/mock/customers/coinbase.json";
import meridianEvents from "@/mock/events/meridian.json";
import coinbaseEvents from "@/mock/events/coinbase.json";
import meridianAlert from "@/mock/alerts/meridian.json";
import coinbaseAlert from "@/mock/alerts/coinbase.json";

type EventsFile = { events: EvidenceEvent[] };
type AlertFile = { alert: DriftAlert };

const CASES: Record<string, CustomerCase> = {
  "meridian-sands": {
    customer: meridianCustomer as unknown as Customer,
    events: (meridianEvents as unknown as EventsFile).events,
    alert: (meridianAlert as unknown as AlertFile).alert,
  },
  "coinbase-global": {
    customer: coinbaseCustomer as unknown as Customer,
    events: (coinbaseEvents as unknown as EventsFile).events,
    alert: (coinbaseAlert as unknown as AlertFile).alert,
  },
};

const ORDER = ["meridian-sands", "coinbase-global"];

export async function listCases(): Promise<CustomerCase[]> {
  return ORDER.map((id) => CASES[id]);
}

export async function getCase(customerId: string): Promise<CustomerCase | null> {
  return CASES[customerId] ?? null;
}
