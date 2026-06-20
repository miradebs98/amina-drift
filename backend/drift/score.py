"""Scoring + risk translation — a transparent weighted sum producing a 0–100 `risk_score`.

Two decoupled axes (the sponsor's framing):
  - SURPRISE  = how far the posterior moved from the prior (drift magnitude, risk-agnostic).
  - RISK_IMPACT = surprise × risk_weight(predicate) × direction (signed; can be ~0 for case (c)).
`risk_score` = baseline (prior) + (100 − baseline) · saturate(Σ risk_impact). Tier = derived band.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from shared.schemas import Assertion
from shared.schemas.dimensions import dimension_for_predicate
from backend.drift import config
from backend.drift.classify import is_candidate, check_envelope_breach, classify_event
from backend.drift.llm import LLMClient
from backend.drift.trajectory import Trajectory, compute_trajectory
from backend.drift.embeddings import ConceptAxisEmbedder

_OUTPUT_PREDICATES = {"risk_score", "risk_tier"}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _noisy_or(strengths: list[float]) -> float:
    prod = 1.0
    for s in strengths:
        prod *= (1.0 - s)
    return 1.0 - prod


def _years_between(d0: date, d1: date) -> float:
    return max(0.0, (d1 - d0).days / 365.25)


def tier_for(risk_score: int) -> str:
    tier = config.TIER_BANDS[0][0]
    for name, lower in config.TIER_BANDS:
        if risk_score >= lower:
            tier = name
    return tier


def risk_weight(predicate: str) -> float:
    return config.RISK_WEIGHT.get(predicate, config.DEFAULT_RISK_WEIGHT)


def risk_direction(predicate: str) -> float:
    return config.RISK_DIRECTION.get(predicate, config.DEFAULT_RISK_DIRECTION)


def compute_inherent_score(assertions, llm) -> tuple[int, list[dict]]:
    """The PRIOR, COMPUTED from the client's own KYC facts (no hardcoded number): the weight-averaged
    inherent risk LEVEL across the onboarding profile, normalised 0–100. Drift is measured from this.
    `llm.score_factors` rates each factor's level (deterministic MockLLM, or Apertus + a per-factor why)."""
    facts = [{"predicate": a.predicate.value, "value": str(a.value)}
             for a in assertions if a.predicate.value not in _OUTPUT_PREDICATES]
    if not facts:
        return 30, []
    factors = llm.score_factors(facts)
    den = sum(risk_weight(f["predicate"]) for f in factors) or 1.0
    num = sum(f["level"] * risk_weight(f["predicate"]) for f in factors)
    return max(0, min(100, int(round(100 * num / den)))), factors


@dataclass
class AssertionDrift:
    assertion: Assertion
    surprise: float = 0.0           # drift magnitude in [0,1] (risk-agnostic)
    risk_impact: float = 0.0        # signed contribution to the risk score
    contra: float = 0.0
    staleness: float = 0.0
    envelope: float = 0.0
    trajectory: float = 0.0
    status: str = "valid"
    confidence: float = 1.0
    evidence_ids: list[str] = field(default_factory=list)
    rationales: list[str] = field(default_factory=list)


@dataclass
class Assessment:
    as_of: date
    baseline_score: int
    risk_score: int
    risk_delta: int                 # risk_score − baseline (the headline movement)
    tier: str
    surprise_max: float             # biggest single-assertion surprise (drives case a/b/c)
    per_assertion: list[AssertionDrift]
    trajectory: Trajectory
    evidence_ids: list[str]
    llm_used: bool = False
    breadth: int = 0                            # # distinct risk dimensions co-moving (connect-the-dots)
    dimensions_drifted: list[str] = field(default_factory=list)


def assess(state, as_of: date, llm: LLMClient, embedder: ConceptAxisEmbedder | None = None) -> Assessment:
    embedder = embedder or ConceptAxisEmbedder()
    traj = compute_trajectory(state.snapshots, as_of, embedder)
    events = [e for e in state.evidence if e.published_at.date() <= as_of]

    per: list[AssertionDrift] = []
    all_evidence_ids: list[str] = []
    llm_used = False

    for A in state.assertions:
        pred = A.predicate.value
        if pred in _OUTPUT_PREDICATES:
            continue

        strengths: list[float] = []
        envelope_mag = 0.0
        ev_ids: list[str] = []
        rationales: list[str] = []

        for e in events:
            if not is_candidate(A, e):
                continue
            breach = check_envelope_breach(A, e)
            if breach is not None:
                envelope_mag = max(envelope_mag, breach)
                ev_ids.append(e.id)
                rationales.append(f"{e.summary} — breaches expected envelope.")
                continue
            v = classify_event(A, e, llm)
            llm_used = True
            if v.verdict == "contradicts":
                strengths.append(v.strength)
                ev_ids.append(e.id)
                rationales.append(v.rationale)

        contra = _noisy_or(strengths)
        staleness = min(config.STALENESS_CAP, _years_between(A.last_verified, as_of) * config.STALENESS_DECAY_PER_YEAR)
        traj_term = _clamp(traj.per_predicate.get(pred, 0.0))

        surprise = _clamp(
            config.W_CONTRADICTION * contra
            + config.W_STALENESS * staleness
            + config.W_ENVELOPE * envelope_mag
            + config.W_TRAJECTORY * traj_term
        )
        impact = surprise * risk_weight(pred) * risk_direction(pred)
        conf = _clamp(A.confidence * (1 - contra) - staleness)
        status = ("contradicted" if (contra >= 0.5 or envelope_mag >= 0.9)
                  else "stale" if conf < config.STALE_STATUS_BELOW else "valid")

        per.append(AssertionDrift(
            assertion=A, surprise=surprise, risk_impact=impact, contra=contra, staleness=staleness,
            envelope=envelope_mag, trajectory=traj_term, status=status, confidence=conf,
            evidence_ids=ev_ids, rationales=rationales,
        ))
        all_evidence_ids.extend(ev_ids)

    # Breadth — the "connect-the-dots" core: count distinct dimensions among MATERIAL contributors;
    # ≥3 co-moving gets a combination boost (5 quiet changes across dimensions > 1 loud one).
    material_dims = sorted({dimension_for_predicate(ad.assertion.predicate.value).value
                            for ad in per if ad.risk_impact > config.MATERIAL_IMPACT})
    breadth = len(material_dims)
    breadth_factor = 1.0 + config.BREADTH_BONUS * max(0, breadth - 2)

    total_impact = sum(ad.risk_impact for ad in per) * breadth_factor
    saturate = min(1.0, total_impact / config.RISK_SCORE_FULL_DRIFT)
    risk_score = int(round(state.baseline_risk_score + (100 - state.baseline_risk_score) * saturate))
    risk_score = max(0, min(100, risk_score))
    surprise_max = max((ad.surprise for ad in per), default=0.0)

    return Assessment(
        as_of=as_of, baseline_score=state.baseline_risk_score, risk_score=risk_score,
        risk_delta=risk_score - state.baseline_risk_score, tier=tier_for(risk_score),
        surprise_max=surprise_max, per_assertion=per, trajectory=traj,
        evidence_ids=list(dict.fromkeys(all_evidence_ids)), llm_used=llm_used,
        breadth=breadth, dimensions_drifted=material_dims,
    )
