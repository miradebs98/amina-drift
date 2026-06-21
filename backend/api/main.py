"""amina-drift API — the keystone that serves CustomerCase to the frontend.

  GET /health              → liveness
  GET /cases               → [summary]  (customer + headline tier/score/flag + cost)
  GET /cases/{key}         → CustomerCase { customer, events, alert, alerts, timeline, cost }
  GET /cases/{key}?refresh=true   → rebuild (re-run ingestion + engine)

Honours OFFLINE_DEMO: default replays fixtures + MockLLM (fast, no network/keys) so the demo and
the frontend's `live` mode work out of the box. Set OFFLINE_DEMO=false (+ Apertus key) for real sources.

  uvicorn backend.api.main:app --reload --port 8000
Frontend: set NEXT_PUBLIC_DATA_MODE=live and point the client at http://localhost:8000
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.api.cases import build_case, list_cases
from backend.govern import audit, data_policy, decisions, rbac

app = FastAPI(title="amina-drift API", version="0.1.0")

# Allow the Next.js dev server (and the deployed demo) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # tighten to the frontend origin for a real deployment
    allow_methods=["*"], allow_headers=["*"],
)

# Cases are expensive to build (ingestion + engine) → cache in memory; ?refresh=true rebuilds.
_CASE_CACHE: dict[str, dict] = {}


@app.get("/health")
def health():
    return {"ok": True, "service": "amina-drift"}


@app.get("/cases")
def cases():
    """Summary list for the dashboard's customer picker."""
    return list_cases()


@app.get("/cases/{customer_key}")
def case(customer_key: str, refresh: bool = Query(False), role: str = Query("analyst")):
    """Full CustomerCase. `customer_key` = customer_id or filename stem.

    Data policy: Layer-2 KYC fields (UBO, source of funds/wealth, PEP, tax IDs) are MASKED unless
    `role` is authorised (MLRO/Compliance/Admin) — secure-by-default. The cached case is always the
    full object; masking is applied to a copy at response time, so scoring/decisions are unaffected.
    """
    if refresh:
        _CASE_CACHE.pop(customer_key, None)
    if customer_key not in _CASE_CACHE:
        built = build_case(customer_key)
        if built is None:
            raise HTTPException(status_code=404, detail=f"unknown customer '{customer_key}'")
        _CASE_CACHE[customer_key] = built
    return data_policy.apply(_CASE_CACHE[customer_key], role)


# ── Governance: HITL decisions + the immutable audit trail ───────────────────
class Decision(BaseModel):
    action: str                       # approve | override | escalate
    reviewer: str = "analyst"
    role: str = "analyst"             # analyst | mlro | compliance | admin (RBAC)
    note: str = ""
    customer_id: Optional[str] = None # fallback if the alert isn't cached
    severity: Optional[str] = None


class RevealRequest(BaseModel):
    reviewer: str = "analyst"
    role: str = "analyst"             # must be MLRO/Compliance/Admin to reveal (data_policy)
    note: str = ""


def _find_alert(alert_id: str):
    """Return (customer_id, full alert dict) from the cached cases."""
    for case in _CASE_CACHE.values():
        for a in [case["alert"], *case.get("alerts", [])]:
            if a["id"] == alert_id:
                return case["customer"]["customer_id"], case["customer"].get("legal_name"), a
    return None


def _decision_context(alert: dict, customer_name: Optional[str]) -> dict:
    """A human-readable, hashed snapshot of WHAT was decided (frozen into the audit entry)."""
    return {
        "alert_id": alert.get("id"),
        "customer": customer_name,
        "flag": alert.get("flag"),
        "severity": alert.get("severity"),
        "old_risk": f'{alert.get("old_risk_tier")} {alert.get("old_risk_score")}',
        "new_risk": f'{alert.get("new_risk_tier")} {alert.get("new_risk_score")}',
        "contradicted_assertion": alert.get("contradicted_assertion_id"),
        "also_contradicts": alert.get("also_contradicts", []),
        "evidence_count": len(alert.get("evidence_ids", [])),
        "recommended_action": alert.get("recommended_action"),
    }


@app.post("/alerts/{alert_id}/decision")
def decide(alert_id: str, body: Decision):
    """HITL disposition → persisted + written to the immutable audit log (RBAC-gated)."""
    found = _find_alert(alert_id)
    alert = found[2] if found else None
    cid = found[0] if found else body.customer_id
    severity = (alert["severity"] if alert else None) or body.severity
    model = alert.get("model_used") if alert else None
    context = _decision_context(alert, found[1]) if alert else {"alert_id": alert_id, "severity": severity}
    if not cid or not severity:
        raise HTTPException(404, f"alert '{alert_id}' not found — load its case first (or pass customer_id+severity)")
    try:
        result = decisions.apply_decision(
            alert_id=alert_id, customer_id=cid, severity=severity, action=body.action,
            reviewer=body.reviewer, role=body.role, note=body.note, model_used=model, context=context)
    except PermissionError as e:        # RBAC denied (four-eyes)
        raise HTTPException(403, str(e))
    # Update the cached alert in place so it stays fresh AND findable for a follow-up decision
    # (e.g. analyst escalates → MLRO approves the same alert).
    for case in _CASE_CACHE.values():
        for a in [case["alert"], *case.get("alerts", [])]:
            if a["id"] == alert_id:
                a["governance_state"] = result["governance_state"]
                a["reviewer"] = result["reviewer"]
                a["decided_at"] = result["decided_at"]
    return result


@app.get("/audit")
def get_audit(customer_id: Optional[str] = None, alert_id: Optional[str] = None):
    """The immutable trail (filterable). What the analyst sees as 'why was this decided'."""
    return audit.query(customer_id, alert_id)


@app.get("/audit/verify")
def verify_audit():
    """Tamper-evidence: recompute the hash chain and report integrity."""
    return audit.verify_chain()


@app.post("/cases/{customer_key}/reveal")
def reveal_internal(customer_key: str, body: RevealRequest):
    """Reveal restricted Layer-2 KYC fields (RBAC-gated) → writes one immutable audit entry.

    Need-to-know access to masked PII-grade KYC data is itself a logged event: who revealed what,
    for which customer, when. Only MLRO/Compliance/Admin may reveal; anyone else gets 403.
    """
    from backend.api.cases import _load_customer
    cust = _load_customer(customer_key)
    if cust is None:
        raise HTTPException(404, f"unknown customer '{customer_key}'")
    if not data_policy.can_reveal(body.role):
        raise HTTPException(403, "revealing restricted Layer-2 KYC data requires an MLRO or Compliance role")
    fields = data_policy.restricted_field_labels(cust)
    audit_id = audit.record(
        action="internal_data_revealed", actor=body.reviewer, role=body.role,
        customer_id=cust["customer_id"], alert_id=None, policy_version=data_policy.POLICY_VERSION,
        details={"note": body.note, "revealed_fields": fields,
                 "customer": cust.get("legal_name")},
    )
    return {"ok": True, "audit_id": audit_id, "customer_id": cust["customer_id"], "revealed_fields": fields}


@app.get("/cases/{customer_key}/network")
def network(customer_key: str):
    """Network Risk dimension: connected entities (investors/partners/UBOs) + sanctions/PEP flags."""
    from backend.api.cases import _load_customer
    from backend.network.graph import build_graph
    cust = _load_customer(customer_key)
    if cust is None:
        raise HTTPException(404, f"unknown customer '{customer_key}'")
    return build_graph(cust["customer_id"])


@app.get("/roles")
def roles():
    return {"roles": rbac.ROLES}
