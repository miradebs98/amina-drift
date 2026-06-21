"""Proves the alert-level confidence is DERIVED from evidence strength, not hardcoded.

Run: pytest backend/drift/test_alert_confidence.py -q
The helper reads only `ad.contra`, so we stub contributors with SimpleNamespace (no engine spin-up).
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.drift.engine import _alert_confidence


def test_confidence_tracks_evidence_strength():
    weak = _alert_confidence([SimpleNamespace(contra=0.30)], ["e1"])
    strong = _alert_confidence([SimpleNamespace(contra=0.95)], ["e1", "e2", "e3"])
    # in-band and genuinely graded
    assert 0.55 <= weak <= 0.97
    assert 0.55 <= strong <= 0.97
    assert strong > weak                          # stronger, better-cited drift → higher confidence
    assert weak != 0.9 and strong != 0.9          # derived, not the old hardcoded 0.9


def test_confidence_floor_when_no_scored_driver():
    # an alert can fire on a velocity/trajectory jump with no scored contributor → moderate floor
    assert _alert_confidence([], []) == 0.6


def test_more_citations_raise_confidence_at_equal_strength():
    one = _alert_confidence([SimpleNamespace(contra=0.6)], ["e1"])
    many = _alert_confidence([SimpleNamespace(contra=0.6)], ["e1", "e2", "e3", "e4"])
    assert many >= one
