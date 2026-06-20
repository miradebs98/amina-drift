// TypeScript mirror of shared/schemas/*.py — the data contracts.
// Keep in sync with the Pydantic models. Source of truth = backend/shared/schemas.

// ── Assertion (assertion.py) ───────────────────────────────────────────────
export type AssertionStatus = "valid" | "stale" | "contradicted" | "under_review";

export interface ExpectedEnvelope {
  low?: number | null;
  high?: number | null;
  allowed_set?: string[] | null;
  unit?: string | null;
}

export interface Assertion {
  id: string;
  customer_id: string;
  predicate: string; // Predicate enum value
  value: string;
  expected_envelope?: ExpectedEnvelope | null;
  as_of: string; // date
  last_verified: string; // date
  source: string;
  source_url?: string | null;
  confidence: number;
  status: AssertionStatus;
  notes?: string | null;
}

// ── Customer file (data/customers/*.json) ──────────────────────────────────
export type RiskBand = "LOW" | "MEDIUM" | "HIGH";

export interface RiskModel {
  scale: string;
  bands: Record<RiskBand, string>; // e.g. { LOW: "0-33", ... }
  onboarding_score: number;
  onboarding_band: RiskBand;
}

export interface KycReview {
  cadence_months_by_band: Record<RiskBand, number>;
  last_review: string;
  next_periodic_review: string;
}

export interface EntityProfile {
  legal_name?: string;
  legal_form?: string;
  country_of_incorporation?: string;
  date_of_incorporation?: string;
  commercial_register_number?: string;
  lei?: string;
  registered_address?: string;
  principal_place_of_business?: string;
  website?: string;
  listed_on_exchange?: boolean;
  ticker?: string;
  regulated_financial_entity?: string | boolean;
  entity_tax_residency?: string;
  entity_tin?: string;
  [k: string]: unknown;
}

export interface Customer {
  customer_id: string;
  legal_name: string;
  onboarded_as_of: string;
  purpose_of_relationship?: string;
  risk_model: RiskModel;
  kyc_review: KycReview;
  entity_profile: EntityProfile;
  assertions: Assertion[];
}

// ── EvidenceEvent (evidence.py) ────────────────────────────────────────────
export type EvidenceType =
  | "news"
  | "registry_change"
  | "ownership_change"
  | "sanctions_hit"
  | "pep_hit"
  | "website_change"
  | "funding"
  | "transaction";

// The 4 KYC-drift dimensions (shared/schemas/dimensions.py)
export type Dimension =
  | "identity_ownership"
  | "network_risk"
  | "behavioural_drift"
  | "contextual_change";

export interface EvidenceEvent {
  id: string;
  entity_ref: string;
  customer_id?: string | null;
  resolution_confidence?: number | null;
  type: EvidenceType;
  summary: string;
  payload: Record<string, unknown>;
  source: string;
  source_url?: string | null;
  published_at: string; // datetime
  confidence: number;
  raw_ref?: string | null;
  dimension?: Dimension; // which of the 4 risk dimensions this signal belongs to
}

// per-belief drift decomposition (API: assertion_drift) — WHY each belief moved
export interface AssertionDrift {
  assertion_id: string;
  predicate: string;
  dimension: Dimension;
  value: string;
  status: AssertionStatus;
  surprise: number;
  risk_impact: number;
  contradiction: number;
  staleness: number;
  envelope_breach: number;
  trajectory: number;
  confidence: number;
  evidence_ids: string[];
  why: string[];
}

// ── DriftAlert (alert.py) ──────────────────────────────────────────────────
export type DriftType = "event" | "structural";
export type Severity = "low" | "medium" | "high";
export type GovernanceState = "pending" | "approved" | "dismissed" | "escalated";

export interface DriftAlert {
  id: string;
  customer_id: string;
  drift_type: DriftType;
  flag: string;
  severity: Severity;
  drift_score: number;
  old_risk_score?: number | null;
  new_risk_score?: number | null;
  old_risk_tier: string;
  new_risk_tier: string;
  contradicted_assertion_id?: string | null;
  also_contradicts: string[];
  evidence_ids: string[];
  rationale: string;
  what_would_flip?: string | null;
  recommended_action: string;
  confidence: number;
  stage_reached: number;
  model_used?: string | null;
  tokens_used: number;
  governance_state: GovernanceState;
  reviewer?: string | null;
  decided_at?: string | null;
  created_at: string;
}

// ── Composite view model the UI works with ─────────────────────────────────
export interface CustomerCase {
  customer: Customer;
  events: EvidenceEvent[];
  alert: DriftAlert;
  // connect-the-dots extras (API emits these; optional so fixtures-lite still type-checks)
  dimensions_drifted?: Dimension[];
  breadth?: number;
  assertion_drift?: AssertionDrift[];
}

// ── Governance (backend/govern) ────────────────────────────────────────────
export type Role = "analyst" | "mlro" | "compliance" | "admin";
export type DecisionAction = "approve" | "override" | "escalate";

export interface DecisionInput {
  alert_id: string;
  action: DecisionAction;
  reviewer: string;
  role: Role;
  note: string;
  customer_id?: string; // fallback so the backend can resolve a cold-cache alert
  severity?: string;
}

export interface DecisionResult {
  alert_id: string;
  governance_state: GovernanceState;
  reviewer: string;
  role: Role;
  decided_at: string;
  audit_id: string;
}

export interface AuditRow {
  seq: number;
  id: string;
  timestamp: string;
  action: string;
  actor: string;
  role: string;
  customer_id?: string | null;
  alert_id?: string | null;
  model_name?: string | null;
  model_version?: string | null;
  inputs_hash?: string | null;
  policy_version?: string | null;
  details?: Record<string, unknown>;
  prev_hash?: string | null;
  entry_hash?: string | null;
}

export interface VerifyResult {
  ok: boolean;
  length: number;
  head?: string;
  broken_at_seq?: number;
}
