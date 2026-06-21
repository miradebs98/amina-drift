// Live API client — talks to the FastAPI backend (backend/api). CORS is open, so
// the browser calls it directly. Same signatures as fixtures.ts for case data,
// plus the real governance endpoints (decisions + immutable audit log).

import type {
  CustomerCase,
  DecisionInput,
  DecisionResult,
  AuditRow,
  VerifyResult,
  Role,
} from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      cache: "no-store",
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API}. Is the backend running?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = (b as { detail?: string }).detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// ── case data (live mode) ──────────────────────────────────────────────────
type CaseResponse = CustomerCase & Record<string, unknown>;

export async function getCase(customerId: string): Promise<CustomerCase | null> {
  try {
    // The dashboard is an authenticated first-party compliance workstation, so it retrieves the
    // full KYC dossier and applies need-to-know MASKING of restricted Layer-2 fields in the UI
    // (lib/policy.ts), logging every reveal. The API itself is default-deny: a caller presenting no
    // authorised role (e.g. `curl /cases/{id}`) receives the masked dossier.
    const c = await j<CaseResponse>(`/cases/${encodeURIComponent(customerId)}?role=compliance`);
    return {
      customer: c.customer,
      events: c.events,
      alert: c.alert,
      // connect-the-dots extras (pass through for the 4-lane view)
      dimensions_drifted: c.dimensions_drifted as CustomerCase["dimensions_drifted"],
      breadth: c.breadth as number | undefined,
      assertion_drift: c.assertion_drift as CustomerCase["assertion_drift"],
      // the real risk-score arc + final state (so the gauge/replay show onboarding → final, not the alert delta)
      timeline: c.timeline as CustomerCase["timeline"],
      final_score: c.final_score as number | undefined,
      final_tier: c.final_tier as string | undefined,
    };
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function getNetwork(customerId: string): Promise<unknown | null> {
  try {
    return await j(`/cases/${encodeURIComponent(customerId)}/network`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function listCases(): Promise<CustomerCase[]> {
  const summaries = await j<{ customer_id: string }[]>(`/cases`);
  const full = await Promise.all(summaries.map((s) => getCase(s.customer_id)));
  return full.filter((c): c is CustomerCase => Boolean(c));
}

// ── governance (always live — the audit log is real, never faked) ───────────
export async function postDecision(input: DecisionInput): Promise<DecisionResult> {
  const { alert_id, ...body } = input;
  return j<DecisionResult>(`/alerts/${encodeURIComponent(alert_id)}/decision`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getAudit(customerId?: string, alertId?: string): Promise<AuditRow[]> {
  const qs = new URLSearchParams();
  if (customerId) qs.set("customer_id", customerId);
  if (alertId) qs.set("alert_id", alertId);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return j<AuditRow[]>(`/audit${suffix}`);
}

export async function verifyAudit(): Promise<VerifyResult> {
  return j<VerifyResult>(`/audit/verify`);
}

// Reveal restricted Layer-2 KYC fields (RBAC-gated) → writes one immutable audit entry.
// Throws ApiError(403) if the role is not MLRO/Compliance/Admin.
export async function revealInternal(input: {
  customerId: string;
  reviewer: string;
  role: Role;
  note?: string;
}): Promise<{ ok: boolean; audit_id: string; customer_id: string; revealed_fields: string[] }> {
  const { customerId, ...body } = input;
  return j(`/cases/${encodeURIComponent(customerId)}/reveal`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
