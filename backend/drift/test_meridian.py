"""End-to-end: replay Meridian Sands offline and assert the silent LOW(28)->HIGH drift holds.

    python -m pytest backend/drift/test_meridian.py -q      (from the repo root)
"""
import sys
import pathlib
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.drift.client_state import load_client_state_from_fixtures
from backend.drift.engine import replay
from backend.drift.score import assess
from backend.drift.classify import anti_hallucination_gate
from backend.drift.llm import MockLLM, Verdict
from shared.schemas import EvidenceEvent, EvidenceType

_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _state():
    return load_client_state_from_fixtures("meridian-sands")


def _result():
    return replay(_state())


def test_low_to_high_arc():
    s = _state()
    assert s.baseline_risk_score == 28, "Meridian onboards at 28 (LOW)"
    r = _result()
    tiers = [t["tier"] for t in r["timeline"]]
    scores = [t["risk_score"] for t in r["timeline"]]
    assert tiers[0] == "LOW" and scores[0] == 28
    assert r["final_tier"] == "HIGH" and r["final_score"] >= 67, "must silently re-tier to HIGH"
    assert all(_RANK[b] >= _RANK[a] for a, b in zip(tiers, tiers[1:])), "tier never goes backwards"
    assert "MEDIUM" in tiers and tiers.index("MEDIUM") < tiers.index("HIGH")
    assert all(b >= a for a, b in zip(scores, scores[1:])), "risk_score is monotonic non-decreasing"


def test_alerts_explainable_and_scored():
    r = _result()
    assert len(r["alerts"]) >= 2
    for al in r["alerts"]:
        assert al.rationale and al.recommended_action and al.evidence_ids and al.what_would_flip
        assert al.old_risk_score is not None and al.new_risk_score is not None
        assert al.new_risk_score > al.old_risk_score


def test_three_situations_present():
    r = _result()
    sits = {t["situation"].split(":")[0] for t in r["timeline"]}
    assert "b" in sits, "must produce risk-flag situations"
    assert sits & {"a", "c"}, "must also produce non-flag (gentle / notable) situations"


def test_no_premature_adverse_media():
    # the adverse-media investigation lands 2025-11; before that, adverse_media must NOT be contradicted
    a = assess(_state(), date(2025, 1, 20), MockLLM())
    am = next(ad for ad in a.per_assertion if ad.assertion.predicate.value == "adverse_media_status")
    assert am.contra == 0.0 and am.envelope == 0.0, "no adverse-media contradiction before the investigation"


def test_cost_is_cheap_dominant():
    assert _result()["cost"]["escalation_rate"] < 0.5


def test_anti_hallucination_gate():
    fake = EvidenceEvent(id="x", entity_ref="Meridian", type=EvidenceType.NEWS,
                         summary="routine annual report, nothing notable", source="test",
                         published_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    bad = Verdict("contradicts", 0.9, "claims a crypto pivot", evidence_quote="crypto brokerage license")
    assert anti_hallucination_gate(bad, fake).verdict == "ambiguous"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python", "-m", "pytest", __file__, "-q"]))
