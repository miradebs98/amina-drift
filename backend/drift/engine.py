"""Engine — turn an Assessment into a DriftAlert, and replay a customer's timeline.

`assess_drift` = one tick (read ClientState at clock.now() -> maybe a DriftAlert).
`replay`       = drive a SimClock over the whole timeline -> the LOW->HIGH score arc + alerts.

The three sponsor-confirmed situations are surfaced on every tick:
  (a) gentle drift  — small surprise, score nudges, NO flag
  (b) risk flag     — big surprise + risk score crosses a tier -> DriftAlert
  (c) notable       — big surprise but ~no risk movement (e.g. a clean funding round) -> logged, NO flag
"""
from __future__ import annotations

from datetime import datetime, time, timezone

from shared.schemas import DriftAlert, DriftType, Severity, GovernanceState
from backend.drift import config
from backend.drift.llm import LLMClient, MockLLM
from backend.drift.embeddings import ConceptAxisEmbedder
from backend.drift.score import Assessment, assess

_TIER_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_SEVERITY = {"LOW": Severity.LOW, "MEDIUM": Severity.MEDIUM, "HIGH": Severity.HIGH}

# predicate -> (use-case flag, recommended action) — echoes the brief's signal->action table.
_FLAGS = {
    "business_model": ("Material Business Model Change", "Update risk classification; escalate for compliance review."),
    "product_mix": ("Material Business Model Change", "Update risk classification; escalate for compliance review."),
    "operating_geographies": ("Structural Risk Change – Geographic Expansion",
                              "Trigger enhanced due diligence; re-check beneficial ownership & corridors."),
    "ubo": ("Ownership Change – KYC Drift", "Full ownership verification; re-screen against sanctions/PEP lists."),
    "pep_status": ("PEP Exposure – Re-screen", "EDD; senior-management approval; ongoing PEP monitoring."),
    "digital_asset_policy": ("Digital-Asset Policy Change", "Re-scope digital-asset risk; verify custody/treasury controls."),
    "source_of_funds": ("Source-of-Funds Change", "Re-verify source of funds; reassess transaction monitoring."),
    "regulatory_status": ("Regulatory-Scope Risk", "Verify licensing (FSRA); escalate potential unlicensed activity."),
    "adverse_media_status": ("Adverse Media – Investigation", "Trigger EDD; compliance review; consider SAR filing."),
    "expected_monthly_volume": ("Behavioural-Envelope Breach", "AML review; reassess transaction-monitoring thresholds."),
}
_DEFAULT_ACTION = "Refresh KYC scope; reassess activity profile and transaction-monitoring thresholds."


def _label_situation(fired: bool, tick_surprise: float) -> str:
    """(b) a drift alert fired this tick · (c) fresh surprise but no flag = notable · (a) gentle drift.
    Note: this is DRIFT-based, not band-based — a flag no longer means 'crossed a tier'."""
    if fired:
        return "b:flag"
    if tick_surprise >= config.SURPRISE_FLAG_THRESHOLD:
        return "c:notable"
    return "a:gentle"


def assess_drift(state, clock, llm: LLMClient | None = None, embedder: ConceptAxisEmbedder | None = None):
    llm = llm or MockLLM()
    a = assess(state, clock.now(), llm, embedder)
    alert = None
    if _TIER_RANK[a.tier] > _TIER_RANK[tier_of(state.baseline_risk_score)]:
        alert = build_alert(state, a, state.baseline_risk_score, tier_of(state.baseline_risk_score), llm)
    return a, alert


def tier_of(score: int) -> str:
    from backend.drift.score import tier_for
    return tier_for(score)


def build_alert(state, a: Assessment, prev_score: int, prev_tier: str, llm: LLMClient,
                tick_surprise: float | None = None) -> DriftAlert:
    contributors = sorted(
        [ad for ad in a.per_assertion if ad.risk_impact > 0.02 and ad.evidence_ids],
        key=lambda ad: ad.risk_impact, reverse=True,
    )
    top = contributors[0] if contributors else max(a.per_assertion, key=lambda ad: ad.risk_impact)

    hard = any(ad.contra >= 0.5 or ad.envelope >= 0.9 for ad in contributors)
    drift_type = DriftType.EVENT if hard else DriftType.STRUCTURAL

    preds = [ad.assertion.predicate.value for ad in contributors[:2]]
    # --- static fallbacks (the deterministic MockLLM path keeps today's flags + wording) ---
    static_flag = " + ".join(_FLAGS.get(p, ("Risk Profile Drift", _DEFAULT_ACTION))[0] for p in preds) or "Risk Profile Drift"
    static_action = _FLAGS.get(preds[0], ("", _DEFAULT_ACTION))[1] if preds else _DEFAULT_ACTION
    moved = ", ".join(a.trajectory.moved_axes) or "n/a"
    static_rationale = (
        f"Onboarded {state.onboarded_as_of:%Y} ({state.baseline_risk_score}/{tier_of(state.baseline_risk_score)}) as: {_baseline_desc(state)}. "
        f"Public record up to {a.as_of:%Y-%m} now shows: "
        + "; ".join(r for ad in contributors[:4] for r in ad.rationales[:1])
        + f". Profile-embedding trajectory migrated (axes: {moved}; distance={a.trajectory.distance:.2f}). "
        f"Composite KYC risk re-scored {prev_score}→{a.risk_score} ({prev_tier}→{a.tier})."
    )

    # --- Stage-3 risk interpretation: the LLM judges the drift EPISODE -> flag / action / why ---
    from shared.schemas.dimensions import dimension_for_predicate
    drifts = [{
        "predicate": ad.assertion.predicate.value,
        "belief": str(ad.assertion.value)[:120],
        "evidence": ad.rationales[:2],
        "surprise": round(ad.surprise, 3),
        "dimension": dimension_for_predicate(ad.assertion.predicate.value).value,
    } for ad in contributors[:5]]
    context = {
        "client": state.legal_name, "onboarded": f"{state.onboarded_as_of:%Y}",
        "baseline_score": state.baseline_risk_score,
        "now_score": a.risk_score, "now_tier": a.tier, "moved_from": f"{prev_score}/{prev_tier}",
    }
    before = llm.meter.heavy_tokens
    judgment = llm.interpret_risk(drifts, context)      # ApiLLM = real interpretation; MockLLM = static
    heavy_tokens = llm.meter.heavy_tokens - before

    flag = judgment.flag or static_flag
    action = judgment.recommended_action or static_action
    rationale = judgment.reasoning or static_rationale

    return DriftAlert(
        id=f"alert-{state.customer_id}-{a.as_of:%Y%m%d}",
        customer_id=state.customer_id,
        drift_type=drift_type,
        flag=flag,
        severity=_SEVERITY[a.tier],
        drift_score=round(tick_surprise if tick_surprise is not None else a.surprise_max, 2),
        old_risk_score=prev_score,
        new_risk_score=a.risk_score,
        old_risk_tier=prev_tier,
        new_risk_tier=a.tier,
        contradicted_assertion_id=top.assertion.id,
        also_contradicts=[ad.assertion.id for ad in contributors[1:]],
        evidence_ids=a.evidence_ids,
        rationale=rationale,
        what_would_flip=("Confirmation that the new activity/geographies/ownership are within licensed "
                         "scope and covered by the existing risk assessment."),
        recommended_action=action,
        confidence=0.9,
        stage_reached=3 if a.llm_used else 1,
        model_used=getattr(llm, "heavy_model", None) or type(llm).__name__,
        tokens_used=heavy_tokens,
        governance_state=GovernanceState.PENDING,
        created_at=datetime.combine(a.as_of, time.min, tzinfo=timezone.utc),
    )


def _baseline_desc(state) -> str:
    for A in state.assertions:
        if A.predicate.value == "business_model":
            return str(A.value)
    return "regulated customer"


def replay(state, llm: LLMClient | None = None, embedder: ConceptAxisEmbedder | None = None,
           verdict_cache: dict | None = None) -> dict:
    from backend.drift.clock import SimClock
    llm = llm or MockLLM()
    embedder = embedder or ConceptAxisEmbedder()
    # One verdict cache for the whole timeline: each (assertion, event) pair is classified once, not
    # re-classified on every subsequent tick. Pass your own dict to also share it with a later
    # standalone assess() on the same llm (e.g. the API's per-assertion decomposition pass).
    verdict_cache = {} if verdict_cache is None else verdict_cache

    dates = sorted({e.published_at.date() for e in state.evidence}
                   | {s.as_of for s in state.snapshots}
                   | {state.onboarded_as_of})
    clock = SimClock(dates[0])
    timeline, alerts = [], []
    prev_score = state.baseline_risk_score
    prev_breadth, fired_critical = 0, set()
    prev_contradicted: set[str] = set()
    prev_surprise: dict[str, float] = {}
    for d in dates:
        clock.advance_to(d)
        a = assess(state, d, llm, embedder, verdict_cache)
        # per-tick (incremental) surprise: how much the most-affected belief's drift JUMPED this tick
        # (captures new contradictions, envelope breaches, partial drift) + the profile trajectory velocity
        deltas = [max(0.0, ad.surprise - prev_surprise.get(ad.assertion.id, 0.0)) for ad in a.per_assertion]
        tick_surprise = max(deltas + [a.trajectory.velocity], default=0.0)

        # ── DRIFT-based alerting (NOT band crossing). The tier is now only a LABEL/cadence; what fires an
        # alert is the DRIFT itself: a NEW assumption invalidated, the drift spanning ≥N dimensions, an
        # actual critical designation, or a sharp one-tick jump in the level. This finally catches
        # within-band drift (a client doubling risk inside MEDIUM) and stops band-edge false alerts
        # (a clean client nudging across 34 fires nothing).
        contradicted_now = {ad.assertion.id for ad in a.per_assertion
                            if ad.contra >= 0.5 or ad.envelope >= 0.9}
        newly_contradicted = [ad for ad in a.per_assertion
                              if ad.assertion.id in (contradicted_now - prev_contradicted)
                              and ad.risk_impact > config.MATERIAL_IMPACT]
        breadth_cross = a.breadth >= config.BREADTH_MIN_DIMS > prev_breadth
        new_critical = [ad for ad in a.per_assertion
                        if ad.assertion.predicate.value in config.CRITICAL_PREDICATES
                        and ad.contra >= config.CRITICAL_CONTRA
                        and ad.assertion.predicate.value not in fired_critical]
        velocity_spike = (a.risk_score - prev_score) >= config.VELOCITY_ALERT_POINTS
        fired = bool(newly_contradicted or breadth_cross or new_critical or velocity_spike)

        timeline.append({"as_of": d, "risk_score": a.risk_score, "tier": a.tier,
                         "surprise": round(tick_surprise, 2), "situation": _label_situation(fired, tick_surprise),
                         "traj_distance": round(a.trajectory.distance, 3)})
        if fired:
            alerts.append(build_alert(state, a, prev_score, tier_of(prev_score), llm, tick_surprise))
            for ad in new_critical:
                fired_critical.add(ad.assertion.predicate.value)
        prev_score = a.risk_score
        prev_breadth = a.breadth
        prev_contradicted = contradicted_now
        for ad in a.per_assertion:
            prev_surprise[ad.assertion.id] = ad.surprise
    return {
        "customer_id": state.customer_id,
        "timeline": timeline,
        "alerts": alerts,
        "final_score": prev_score,
        # current tier reflects the current score — NOT the ratcheted alert tier: with de-risking
        # (resolves) the level can fall back, so the reported tier must be able to come down too.
        "final_tier": tier_of(prev_score),
        "cost": {"cheap_calls": llm.meter.cheap_calls, "heavy_calls": llm.meter.heavy_calls,
                 "total_tokens": llm.meter.total_tokens, "escalation_rate": round(llm.meter.escalation_rate, 3)},
    }
