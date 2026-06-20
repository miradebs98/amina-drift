"""Scoring + risk translation — a transparent weighted sum producing a 0–100 `risk_score`.

Two decoupled axes (the sponsor's framing):
  - SURPRISE  = how far the posterior moved from the prior (drift magnitude, risk-agnostic).
  - RISK_IMPACT = surprise × risk_weight(predicate) × direction (signed; can be ~0 for case (c)).
`risk_score` = baseline (prior) + (100 − baseline) · saturate(Σ risk_impact). Tier = derived band.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from shared.schemas import Assertion
from shared.schemas.dimensions import dimension_for_predicate
from backend.drift import config
from backend.drift.classify import is_candidate, check_envelope_breach, check_screen_match, classify_event
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


def _drift_index(contributions: list[float], decay: float) -> float:
    """Diminishing-returns ACCUMULATION (replaces noisy-OR). The strongest drift counts fully; each
    ADDITIONAL co-moving drift adds less (× decay^rank). This is the connect-the-dots core: the index
    CLIMBS with every extra drifting dimension (so the timeline arc rises as changes accumulate — the
    visible 'drift, not single event' signal), but unlike noisy-OR it does NOT saturate to 1 on a
    handful of moderate signals — so 'moderate but broad' (HashKey) ranks BELOW 'severe' (Binance)."""
    ranked = sorted((c for c in contributions if c > 0), reverse=True)
    return sum(c * (decay ** i) for i, c in enumerate(ranked))


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


def evidence_weight(event_type: str) -> float:
    """How much a cheap-LLM verdict counts by SOURCE TYPE — a website diff is softer than a filing."""
    return config.EVIDENCE_WEIGHT.get(event_type, config.DEFAULT_EVIDENCE_WEIGHT)


@dataclass
class AssertionDrift:
    assertion: Assertion
    surprise: float = 0.0           # drift magnitude in [0,1] (risk-agnostic)
    risk_impact: float = 0.0        # signed contribution to the risk score
    contra: float = 0.0
    staleness: float = 0.0
    envelope: float = 0.0
    trajectory: float = 0.0
    implied_excess: float = 0.0     # this belief's pull into the headroom (0–1), for the level re-derivation
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


def assess(state, as_of: date, llm: LLMClient, embedder: ConceptAxisEmbedder | None = None,
           verdict_cache: dict | None = None) -> Assessment:
    embedder = embedder or ConceptAxisEmbedder()
    # A (assertion, event) verdict is deterministic — it depends only on the assertion and the event,
    # never on `as_of`. So across a replay's many ticks each pair need only be classified ONCE.
    # `verdict_cache` (keyed by (assertion_id, event_id)) carries those verdicts between ticks; left
    # None it's a fresh per-call dict, so a one-shot `assess` behaves exactly as before.
    verdict_cache = {} if verdict_cache is None else verdict_cache
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
        resolve_strengths: list[float] = []     # de-risking events that retract a prior concern
        screen_strengths: list[float] = []      # sanctions/PEP screen hits — re-flags do NOT compound
        envelope_mag = 0.0
        ev_ids: list[str] = []
        rationales: list[str] = []

        for e in events:
            if not is_candidate(A, e):
                continue
            # Sanctions/PEP screen hits are scored DETERMINISTICALLY from match quality (never the LLM):
            # confirmed → strong, name-only/unverified → capped potential (+ needs human verification).
            screen = check_screen_match(A, e)
            if screen is not None:
                screen_strengths.append(screen.strength)
                ev_ids.append(e.id)
                rationales.append(screen.rationale)
                continue
            breach = check_envelope_breach(A, e)
            if breach is not None:
                envelope_mag = max(envelope_mag, breach)
                ev_ids.append(e.id)
                rationales.append(f"{e.summary} — breaches expected envelope.")
                continue
            key = (A.id, e.id)
            v = verdict_cache.get(key)
            if v is None:
                v = classify_event(A, e, llm)        # cheap-LLM verdict — metered once per unique pair
                verdict_cache[key] = v
            llm_used = True                           # an LLM verdict backs this assessment (cached or fresh)
            ew = evidence_weight(e.type.value)        # soft sources (website diff) count less
            if v.verdict == "contradicts":
                strengths.append(v.strength * ew)
                ev_ids.append(e.id)
                rationales.append(v.rationale)
            elif v.verdict == "resolves":
                resolve_strengths.append(v.strength * ew)
                ev_ids.append(e.id)
                rationales.append(v.rationale)

        # Screen matches (sanctions/PEP) combine by MAX, not noisy-OR: re-flagging the SAME unverified
        # name 4× is one open verification item, not 4 independent hits — it must not compound toward
        # certainty. The strongest single match stands; a human clears or confirms it (HITL).
        if screen_strengths:
            strengths.append(max(screen_strengths))
        # Risk is NOT a ratchet: de-risking events (suit dismissed, licence granted) RETRACT the
        # accumulated concern, so the contradiction — and the score — can come back DOWN over time.
        contra = _clamp(_noisy_or(strengths) - _noisy_or(resolve_strengths))
        staleness = min(config.STALENESS_CAP, _years_between(A.last_verified, as_of) * config.STALENESS_DECAY_PER_YEAR)
        traj_term = _clamp(traj.per_predicate.get(pred, 0.0))

        # Drift magnitude = what the EVIDENCE says changed. Staleness is deliberately NOT here: "we
        # haven't re-verified in N years" is a DATA-FRESHNESS / re-KYC signal, not higher inherent risk
        # (it was silently climbing clean clients like Geberit across band edges). It's still computed
        # below and surfaced via `status`/confidence — just kept out of the risk LEVEL.
        surprise = _clamp(
            config.W_CONTRADICTION * contra
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

    # Breadth — # distinct dimensions materially co-moving (connect-the-dots), reported for alerting.
    material_dims = sorted({dimension_for_predicate(ad.assertion.predicate.value).value
                            for ad in per if ad.risk_impact > config.MATERIAL_IMPACT})
    breadth = len(material_dims)

    # ── Risk LEVEL re-derived from the current belief-state — TWO channels so "many moderate drifts"
    # never reads as catastrophic, and one true designation does:
    #   • accumulation — non-designation drift, severity-weighted (d × risk_weight), combined by the
    #     diminishing-returns DRIFT INDEX (not noisy-OR). It CLIMBS with breadth (connect-the-dots: the
    #     timeline arc rises as drifts accumulate) but does NOT saturate — so moderate-but-broad ranks
    #     below severe — then maps smoothly toward ACCUMULATION_CAP (asymptote, never pins).
    #   • critical     — an actual sanctions designation (authoritative-only) jumps straight to its
    #     ceiling (~100). 88–100 is reserved for that.
    baseline = state.baseline_risk_score
    cap = max(config.ACCUMULATION_CAP, baseline)
    contributions: list[float] = []
    critical_level = 0.0
    for ad in per:
        pred = ad.assertion.predicate.value
        d = _clamp(ad.surprise * risk_direction(pred))     # signed invalidation in [0,1]
        ad.implied_excess = d * risk_weight(pred)           # severity-weighted contribution (explainable)
        contributions.append(ad.implied_excess)
        if pred in config.CRITICAL_DESIGNATION and d >= config.CRIT_DESIGNATION_MIN:
            critical_level = max(critical_level, 100.0 * risk_weight(pred))
    drift_index = _drift_index(contributions, config.BREADTH_DECAY)
    g = 1.0 - math.exp(-drift_index / config.DRIFT_SATURATION)    # smooth; breadth climbs it, never pins
    accum_level = baseline + (cap - baseline) * g
    risk_score = int(round(max(accum_level, critical_level)))
    risk_score = max(0, min(100, risk_score))
    surprise_max = max((ad.surprise for ad in per), default=0.0)

    return Assessment(
        as_of=as_of, baseline_score=state.baseline_risk_score, risk_score=risk_score,
        risk_delta=risk_score - state.baseline_risk_score, tier=tier_for(risk_score),
        surprise_max=surprise_max, per_assertion=per, trajectory=traj,
        evidence_ids=list(dict.fromkeys(all_evidence_ids)), llm_used=llm_used,
        breadth=breadth, dimensions_drifted=material_dims,
    )
