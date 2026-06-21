// Data-separation + masking policy (UI mirror of backend/govern/data_policy.py — keep in sync).
//
// Layer 1 (public evidence) is shown freely; Layer 2 (internal KYC) carries restricted, PII-grade
// fields (beneficial ownership, source of funds/wealth, PEP detail, tax IDs) that are MASKED by
// default and only revealed to an authorised role — every reveal is written to the audit log.
// This is presentation-only: it never changes scores, alerts, or the engine's inputs.

import type { Assertion, Customer, Role } from "@/lib/types";

export const RESTRICTED_PREDICATES = new Set<string>([
  "ubo",
  "directors",
  "ownership_structure",
  "source_of_funds",
  "source_of_wealth",
  "pep_status",
]);

export const RESTRICTED_ENTITY_FIELDS = ["entity_tin"] as const;

export const REVEAL_ROLES = new Set<Role>(["mlro", "compliance", "admin"]);

// Must not start with "{" — the value formatter (lib/format.ts) only JSON-parses leading-brace values.
export const MASK_TOKEN = "•••••• — restricted (Layer 2 · reveal requires MLRO/Compliance)";

export function canReveal(role: string | null | undefined): boolean {
  return !!role && REVEAL_ROLES.has(role as Role);
}

export function restrictedAssertions(customer: Customer): Assertion[] {
  return (customer.assertions ?? []).filter((a) => RESTRICTED_PREDICATES.has(a.predicate));
}

export function hasRestricted(customer: Customer): boolean {
  if (restrictedAssertions(customer).length > 0) return true;
  const ep = customer.entity_profile ?? {};
  return RESTRICTED_ENTITY_FIELDS.some((f) => Boolean(ep[f]));
}

// A copy of the customer with restricted Layer-2 fields masked (does not mutate the input).
export function maskCustomer(customer: Customer): Customer {
  const assertions = (customer.assertions ?? []).map((a) =>
    RESTRICTED_PREDICATES.has(a.predicate) ? { ...a, value: MASK_TOKEN } : a,
  );
  const ep: Customer["entity_profile"] = { ...(customer.entity_profile ?? {}) };
  for (const f of RESTRICTED_ENTITY_FIELDS) if (ep[f]) ep[f] = MASK_TOKEN;
  return { ...customer, assertions, entity_profile: ep };
}
