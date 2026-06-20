"""Slow structural drift — the profile-embedding trajectory (the headline, the early warning).

No single event needs to contradict anything. We embed each snapshot onto the concept axes, then
watch the trajectory migrate away from the onboarding baseline. When cumulative distance or
velocity crosses a band, we raise an alarm *before* any hard contradiction — and we translate the
move back into assertion language (which predicate each moving axis implicates).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from shared.schemas import Snapshot
from backend.drift import config
from backend.drift.embeddings import ConceptAxisEmbedder, cosine_distance


@dataclass
class Trajectory:
    distance: float = 0.0                 # cumulative drift from the onboarding baseline (cosine)
    velocity: float = 0.0                 # jump from the previous snapshot
    alarm: bool = False                   # early-warning structural alarm tripped?
    per_predicate: dict[str, float] = field(default_factory=dict)  # how much each assertion is implicated
    moved_axes: list[str] = field(default_factory=list)            # for the human-readable rationale


def compute_trajectory(snapshots: list[Snapshot], as_of: date,
                       embedder: ConceptAxisEmbedder | None = None) -> Trajectory:
    """Trajectory using only snapshots up to `as_of`. Baseline = earliest snapshot."""
    embedder = embedder or ConceptAxisEmbedder()
    series = sorted([s for s in snapshots if s.as_of <= as_of], key=lambda s: s.as_of)
    if len(series) < 2:
        return Trajectory()

    base = embedder.from_signal_mix(series[0].signal_mix)
    cur = embedder.from_signal_mix(series[-1].signal_mix)
    prev = embedder.from_signal_mix(series[-2].signal_mix)

    distance = cosine_distance(base, cur)
    velocity = cosine_distance(prev, cur)
    alarm = distance >= config.TRAJECTORY_ALARM_DISTANCE or velocity >= config.TRAJECTORY_VELOCITY_ALARM

    # per-axis movement (above the noise floor) -> implicated predicate
    per_predicate: dict[str, float] = {}
    moved_axes: list[str] = []
    base_mix = series[0].signal_mix
    cur_mix = series[-1].signal_mix
    for axis in config.CONCEPT_AXES:
        delta = cur_mix.get(axis, 0.0) - base_mix.get(axis, 0.0)
        delta = max(0.0, delta - config.TRAJECTORY_NOISE_FLOOR)
        if delta > 0 and axis in config.AXIS_TO_PREDICATE:
            pred = config.AXIS_TO_PREDICATE[axis]
            per_predicate[pred] = per_predicate.get(pred, 0.0) + delta
            moved_axes.append(axis)

    return Trajectory(distance=distance, velocity=velocity, alarm=alarm,
                      per_predicate=per_predicate, moved_axes=moved_axes)
