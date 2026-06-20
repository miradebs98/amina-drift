"""Case assembly — the keystone that wires all three lanes into one `CustomerCase`.

CustomerCase = { customer, events, alert } (the shape the frontend consumes), built by:
  customer  ← data/customers/*.json           (Giacomo / Layer 2)
  events    ← backend.ingest.runner.collect()  (Mira / Layer 1 — live or fixtures)
  alert     ← backend.drift.engine.replay()     (Miguel / the engine)

Resolves the cross-lane ID mismatch: the engine fixture-loader keyed Coinbase as "coinbase",
the runner uses the real customer_id "coinbase-global". We load by EITHER and always drive the
runner + engine off the real customer_id.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional

from backend.ingest.base import CUSTOMERS_DIR
from backend.ingest.runner import collect
from shared.schemas import (Assertion, DriftAlert, DriftType, Severity, GovernanceState,
                            dimension_for_predicate, dimension_for_evidence)
from backend.drift.client_state import ClientState, _MOCK_SNAPSHOTS
from backend.drift.engine import replay
from backend.drift.llm import get_llm
from backend.drift.score import tier_for
from backend.govern.decisions import get_decision


def _customer_files():
    return sorted(CUSTOMERS_DIR.glob("*.json"))


def _load_customer(key: str) -> Optional[dict]:
    """Find a customer by filename stem OR customer_id (handles the ID mismatch)."""
    for p in _customer_files():
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if p.stem == key or d.get("customer_id") == key:
            return d
    return None


def _json(model) -> dict:
    return json.loads(model.model_dump_json())


def _overlay_decision(alert: dict) -> dict:
    """Overlay any persisted HITL decision so an actioned alert stays actioned across rebuilds."""
    d = get_decision(alert["id"])
    if d:
        alert["governance_state"] = d["governance_state"]
        alert["reviewer"] = d["reviewer"]
        alert["decided_at"] = d["decided_at"]
    return alert


def _safe_timeline(timeline: list[dict]) -> list[dict]:
    out = []
    for t in timeline:
        row = dict(t)
        if isinstance(row.get("as_of"), date):
            row["as_of"] = row["as_of"].isoformat()
        out.append(row)
    return out


def _clean_alert(cid: str, baseline: int, n_events: int, when: datetime) -> DriftAlert:
    """Honest 'no material drift' record when the engine flags nothing — keeps the UI contract
    (alert is non-null) and truthfully says 'we screened, nothing contradicted'."""
    band = tier_for(baseline)
    return DriftAlert(
        id=f"alert-{cid}-clean", customer_id=cid, drift_type=DriftType.EVENT,
        flag="No material drift", severity=Severity.LOW, drift_score=0.0,
        old_risk_score=baseline, new_risk_score=baseline, old_risk_tier=band, new_risk_tier=band,
        contradicted_assertion_id=None, also_contradicts=[], evidence_ids=[],
        rationale=f"Monitored {n_events} public signals; no on-file KYC assertion was contradicted.",
        recommended_action="No action — continue monitoring.", confidence=0.6,
        model_used="none", governance_state=GovernanceState.PENDING, created_at=when,
    )


def build_case(key: str, live: Optional[bool] = None) -> Optional[dict]:
    cust = _load_customer(key)
    if cust is None:
        return None
    cid = cust["customer_id"]

    events = collect(cid, live=live)                       # Mira's Layer-1 stream (live or fixtures)
    assertions = [Assertion(**a) for a in cust["assertions"]]
    baseline = int(cust.get("risk_model", {}).get("onboarding_score", 30))
    snapshots = _MOCK_SNAPSHOTS.get(cid, lambda _c: [])(cid)  # Meridian has mock snapshots; others []

    state = ClientState(
        customer_id=cid, legal_name=cust.get("legal_name", cid),
        onboarded_as_of=date.fromisoformat(cust["onboarded_as_of"]),
        baseline_risk_score=baseline, assertions=assertions,
        evidence=events, snapshots=snapshots,
    )
    r = replay(state, get_llm())                           # Miguel's engine

    # ── 4-dimension tagging (connect-the-dots): tag each event + which dimensions drifted ──
    pred_by_id = {a.id: a.predicate.value for a in assertions}

    def _event_json(e):
        d = _json(e)
        d["dimension"] = dimension_for_evidence(d["type"]).value
        return d

    def _dims_for_alert(al) -> list[str]:
        ids = ([al.contradicted_assertion_id] if al.contradicted_assertion_id else []) + list(al.also_contradicts)
        return sorted({dimension_for_predicate(pred_by_id.get(i, "")).value for i in ids if i in pred_by_id})

    alerts = r["alerts"]
    latest = max((e.published_at for e in events), default=datetime.now(timezone.utc))
    # Headline = the most MATERIAL drift episode (highest resulting score, tie-break latest),
    # not just the chronologically last (which can be a minor early nudge).
    headline = (max(alerts, key=lambda al: ((al.new_risk_score or 0), al.created_at))
                if alerts else _clean_alert(cid, baseline, len(events), latest))

    return {
        "customer": cust,
        "events": [_event_json(e) for e in events],        # each tagged with its dimension
        "alert": _overlay_decision(_json(headline)),       # the headline alert (UI contract)
        "alerts": [_overlay_decision(_json(a)) for a in alerts],  # full episode list (richer views)
        "timeline": _safe_timeline(r["timeline"]),         # the risk-score arc
        "cost": r["cost"],                                 # cheap/heavy/tokens/escalation
        "final_score": r["final_score"], "final_tier": r["final_tier"],
        # connect-the-dots: which of the 4 dimensions the headline drift spans (≥3 = strong signal)
        "dimensions_drifted": _dims_for_alert(headline),
    }


def list_cases(live: Optional[bool] = None) -> list[dict]:
    out = []
    for p in _customer_files():
        try:
            cid = json.loads(p.read_text())["customer_id"]
        except Exception:
            continue
        c = build_case(cid, live=live)
        if not c:
            continue
        a = c["alert"]
        out.append({
            "customer_id": cid, "legal_name": c["customer"].get("legal_name"),
            "baseline_score": int(c["customer"].get("risk_model", {}).get("onboarding_score", 30)),
            "final_score": c["final_score"], "final_tier": c["final_tier"],
            "headline_flag": a["flag"], "severity": a["severity"],
            "n_events": len(c["events"]), "n_alerts": len(c["alerts"]),
            "escalation_rate": c["cost"].get("escalation_rate"),
        })
    return out
