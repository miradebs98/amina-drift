"""Unit guardrail for the baseline-consistency rule (the offline MockLLM stand-in).

Drift = DEVIATION from the on-file baseline: a signal the baseline ALREADY asserts is not drift.
(The old Coinbase/Meridian arc tests were removed — Meridian was fabricated and is no longer a
calibration target; the real-roster behaviour is validated against Apertus, not MockLLM.)

    python -m pytest backend/drift/test_calibration.py -q      (from the repo root)
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.drift.llm import consistent_with_baseline


def test_baseline_consistency_rule():
    """A signal already part of the on-file baseline CONFIRMS it; only a deviation contradicts."""
    # crypto event vs an already-crypto baseline → consistent; vs a SaaS baseline → deviation
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


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python", "-m", "pytest", __file__, "-q"]))
