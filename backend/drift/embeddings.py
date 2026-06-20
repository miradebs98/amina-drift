"""Profile embedding — deliberately interpretable and offline.

We embed onto a small set of RISK-RELEVANT concept axes (config.CONCEPT_AXES), not into a generic
768-dim text space. A move in this space is human-readable ("crypto axis went 0.0 -> 0.85"), which
is exactly what a compliance audience needs. Swap `ConceptAxisEmbedder` for a real sentence-encoder
later without touching the trajectory math — both return a vector aligned to CONCEPT_AXES.
"""
from __future__ import annotations

import math
from typing import Sequence

from backend.drift import config


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """1 - cosine similarity, clamped to [0, 1]."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 1.0
    sim = dot / (na * nb)
    return max(0.0, min(1.0, 1.0 - sim))


class ConceptAxisEmbedder:
    """Project a signal_mix dict OR free text onto CONCEPT_AXES -> a vector in that fixed order."""

    axes = config.CONCEPT_AXES

    def from_signal_mix(self, signal_mix: dict[str, float]) -> list[float]:
        vec = [float(signal_mix.get(axis, 0.0)) for axis in self.axes]
        total = sum(vec)
        return [v / total for v in vec] if total > 0 else vec  # L1-normalise: composition, not magnitude

    def from_text(self, text: str) -> list[float]:
        t = f" {text.lower()} "
        vec = []
        for axis in self.axes:
            seeds = config.AXIS_SEEDS.get(axis, [])
            hits = sum(t.count(seed.lower()) for seed in seeds)
            # squash hit count into [0,1] so the vector stays comparable to a signal_mix
            vec.append(1.0 - math.exp(-hits)) if hits else vec.append(0.0)
        return vec
