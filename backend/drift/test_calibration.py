"""Calibration guardrails — the deliberate Coinbase/Meridian CONTRAST must hold.

Meridian (SaaS, UAE-only, no crypto) silently re-tiers LOW->HIGH. Coinbase onboards already-elevated
as a global regulated crypto exchange, so its crypto/expansion/MiCA news CONFIRMS the baseline — it
must stay MEDIUM (within-band), NOT flip. This pins both, and the baseline-consistency rule behind it.

    python -m pytest backend/drift/test_calibration.py -q      (from the repo root)
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date

from backend.drift.client_state import load_client_state_from_fixtures
from backend.drift.engine import replay
from backend.drift.llm import consistent_with_baseline, MockLLM
from backend.drift.score import assess, tier_for


def test_coinbase_stays_medium():
    """Coinbase must NOT flip — its drift is within-band upward pressure (60 -> ~66), not a re-tier."""
    s = load_client_state_from_fixtures("coinbase")
    r = replay(s)
    assert tier_for(s.baseline_risk_score) == "MEDIUM", f"Coinbase onboards MEDIUM (computed {s.baseline_risk_score})"
    assert r["final_tier"] == "MEDIUM", f"Coinbase must stay MEDIUM, got {r['final_tier']} ({r['final_score']})"
    assert 34 <= r["final_score"] <= 66, f"within-band MEDIUM, got {r['final_score']}"


def test_meridian_flips_coinbase_does_not():
    """The deliberate contrast: same engine, Meridian re-tiers to HIGH, Coinbase does not."""
    mer = replay(load_client_state_from_fixtures("meridian-sands"))
    cb = replay(load_client_state_from_fixtures("coinbase"))
    assert mer["final_tier"] == "HIGH" and cb["final_tier"] == "MEDIUM"
    assert mer["final_score"] > cb["final_score"]


def test_baseline_consistency_rule():
    """Drift = DEVIATION from the baseline; a signal the baseline already asserts is not drift."""
    # crypto event vs an already-crypto baseline → consistent (Coinbase); vs a SaaS baseline → deviation (Meridian)
    assert consistent_with_baseline("business_model", "Retail & institutional digital-asset exchange + custody",
                                    "launches a new crypto trading product") is True
    assert consistent_with_baseline("business_model", "B2B SaaS analytics for SMEs",
                                    "pivots to web3 / crypto trading infrastructure") is False
    # geography: already-global vs UAE-only (restrictive baseline → deviation-capable)
    assert consistent_with_baseline("operating_geographies", "US-origin, expanding globally (EU, UK)",
                                    "expands into european markets") is True
    assert consistent_with_baseline("operating_geographies", "UAE-only operations",
                                    "opens an offshore bvi subsidiary") is False
    # regulatory: a positive licence confirms; an unlicensed activity drifts (even with 'fsra' in between)
    assert consistent_with_baseline("regulatory_status", "NYDFS BitLicense + US MTLs; EU MiCA",
                                    "granted an EU MiCA licence") is True
    assert consistent_with_baseline("regulatory_status", "FSRA-registered fintech",
                                    "offers a retail crypto brokerage without FSRA authorisation") is False
    # genuinely-adverse predicates are never suppressed
    assert consistent_with_baseline("adverse_media_status", "no adverse media on file",
                                    "named in an SEC enforcement action") is False


def test_coinbase_fires_within_band_alert():
    """Decoupled alerting: Coinbase's SEC adverse-media drift fires a flag even though it stays
    MEDIUM (the brief's 'negative news -> reputational risk', no re-tier — not 'No material drift')."""
    r = replay(load_client_state_from_fixtures("coinbase"))
    assert r["final_tier"] == "MEDIUM"
    assert len(r["alerts"]) >= 1, "within-band reputational drift must still flag the manager"
    assert any(("Adverse Media" in al.flag or "Reputational" in al.flag) for al in r["alerts"])


def test_meridian_breadth_combination():
    """Meridian drifts across >=3 risk dimensions — the connect-the-dots combination signal."""
    a = assess(load_client_state_from_fixtures("meridian-sands"), date(2026, 2, 18), MockLLM())
    assert a.breadth >= 3, f"expected >=3 dimensions, got {a.breadth}: {a.dimensions_drifted}"


def test_baseline_is_computed_from_facts():
    """The onboarding prior is COMPUTED from the KYC facts (not hardcoded): a domestic SaaS shop
    onboards LOW, a global crypto exchange onboards MEDIUM, each with a per-factor breakdown."""
    mer = load_client_state_from_fixtures("meridian-sands")
    cb = load_client_state_from_fixtures("coinbase")
    assert tier_for(mer.baseline_risk_score) == "LOW" and mer.baseline_breakdown
    assert tier_for(cb.baseline_risk_score) == "MEDIUM" and cb.baseline_breakdown
    assert cb.baseline_risk_score > mer.baseline_risk_score, "crypto exchange onboards higher than SaaS"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python", "-m", "pytest", __file__, "-q"]))
