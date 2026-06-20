"""amina-drift API — the keystone that serves CustomerCase to the frontend.

  GET /health              → liveness
  GET /cases               → [summary]  (customer + headline tier/score/flag + cost)
  GET /cases/{key}         → CustomerCase { customer, events, alert, alerts, timeline, cost }
  GET /cases/{key}?refresh=true   → rebuild (re-run ingestion + engine)

Honours OFFLINE_DEMO: default replays fixtures + MockLLM (fast, no network/keys) so the demo and
Giacomo's `live` mode work out of the box. Set OFFLINE_DEMO=false (+ Apertus key) for real sources.

  uvicorn backend.api.main:app --reload --port 8000
Frontend: set NEXT_PUBLIC_DATA_MODE=live and point the client at http://localhost:8000
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.api.cases import build_case, list_cases
from backend.govern import audit, decisions, rbac

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
def case(customer_key: str, refresh: bool = Query(False)):
    """Full CustomerCase. `customer_key` = customer_id or filename stem."""
    if refresh:
        _CASE_CACHE.pop(customer_key, None)
    if customer_key not in _CASE_CACHE:
        built = build_case(customer_key)
        if built is None:
            raise HTTPException(status_code=404, detail=f"unknown customer '{customer_key}'")
        _CASE_CACHE[customer_key] = built
    return _CASE_CACHE[customer_key]


# ── Governance: HITL decisions + the immutable audit trail ───────────────────
class Decision(BaseModel):
    action: str                       # approve | override | escalate
    reviewer: str = "analyst"
    role: str = "analyst"             # analyst | mlro | compliance | admin (RBAC)
    note: str = ""
    customer_id: Optional[str] = None # fallback if the alert isn't cached
    severity: Optional[str] = None


def _find_alert(alert_id: str):
    """Authoritative (customer_id, severity, model_used) from the cached cases."""
    for case in _CASE_CACHE.values():
        for a in [case["alert"], *case.get("alerts", [])]:
            if a["id"] == alert_id:
                return case["customer"]["customer_id"], a["severity"], a.get("model_used")
    return None


@app.post("/alerts/{alert_id}/decision")
def decide(alert_id: str, body: Decision):
    """HITL disposition → persisted + written to the immutable audit log (RBAC-gated)."""
    found = _find_alert(alert_id)
    cid = found[0] if found else body.customer_id
    severity = found[1] if found else body.severity
    model = found[2] if found else None
    if not cid or not severity:
        raise HTTPException(404, f"alert '{alert_id}' not found — load its case first (or pass customer_id+severity)")
    try:
        result = decisions.apply_decision(
            alert_id=alert_id, customer_id=cid, severity=severity, action=body.action,
            reviewer=body.reviewer, role=body.role, note=body.note, model_used=model)
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
