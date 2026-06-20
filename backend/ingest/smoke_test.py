"""Smoke tests for the ingestion layer — run after config changes.

  python -m backend.ingest.smoke_test           # offline + config tests (deterministic, no network)
  python -m backend.ingest.smoke_test --live     # also hit real sources (needs network)

Exits non-zero on first failure. Designed to answer: "does the new config always work?"
"""
from __future__ import annotations

import os
import sys

from shared.schemas import EvidenceEvent
from backend.ingest.base import CustomerRef, load_assertions
from backend.ingest.relevance import RelevanceFilter
from backend.ingest.runner import collect
from backend.ingest.sec_earnings import SecEarningsConnector

PASS, FAIL = "✅", "❌"
_failures = 0


def check(name: str, cond: bool, detail: str = ""):
    global _failures
    print(f"  {PASS if cond else FAIL} {name}{(' — ' + detail) if detail else ''}")
    if not cond:
        _failures += 1


def _valid_events(events, customer_id):
    """All are EvidenceEvent, right customer, time-sorted, JSON round-trips."""
    if not all(isinstance(e, EvidenceEvent) for e in events):
        return False, "non-EvidenceEvent in stream"
    if any(e.customer_id != customer_id for e in events):
        return False, "wrong customer_id"
    ts = [e.published_at for e in events]
    if ts != sorted(ts):
        return False, "not time-sorted"
    for e in events:  # schema round-trip
        EvidenceEvent.model_validate_json(e.model_dump_json())
    return True, ""


# ── offline / config tests (no network) ─────────────────────────────────────
def test_offline_both():
    print("\n[1] Offline fixtures — both customers")
    for cid, lo in [("meridian-sands", 5), ("coinbase-global", 5)]:
        ev = collect(cid, live=False)
        ok, why = _valid_events(ev, cid)
        check(f"{cid}: {len(ev)} events, schema-valid", ok and len(ev) >= lo, why or f"{len(ev)} events")
        check(f"{cid}: every event cites a source", all(e.source for e in ev))


def test_relevance_modes():
    print("\n[2] Relevance filter modes resolve safely (never crash, never silent-charge)")
    saved = os.environ.get("RELEVANCE_EMBEDDINGS")
    try:
        for mode, expect in [("lexical", "lexical"), ("openai", "lexical"), ("local", "lexical"), (None, "lexical")]:
            os.environ.pop("RELEVANCE_EMBEDDINGS", None) if mode is None else os.environ.__setitem__("RELEVANCE_EMBEDDINGS", mode)
            rf = RelevanceFilter()
            check(f"mode={mode} → '{rf.mode}' (no key → free)", rf.mode == expect, rf.mode)
        # ranking actually works
        rf = RelevanceFilter()
        ranked = rf.rank("crypto trading derivatives", ["we sell coffee", "crypto derivatives desk launched", "office supplies"])
        check("ranking returns best passage first", ranked and "crypto" in ranked[0].passage.lower())
    finally:
        os.environ.pop("RELEVANCE_EMBEDDINGS", None)
        if saved is not None:
            os.environ["RELEVANCE_EMBEDDINGS"] = saved


def test_customer_resolution():
    print("\n[3] Customer identity resolution")
    cb = CustomerRef.load("coinbase-global")
    check("Coinbase: ticker=COIN", cb.ticker == "COIN", str(cb.ticker))
    check("Coinbase: 10-digit CIK", bool(cb.cik) and len(cb.cik) == 10, str(cb.cik))
    check("Coinbase: domain parsed", cb.domain == "coinbase.com", str(cb.domain))
    ms = CustomerRef.load("meridian-sands")
    check("Meridian: no ticker (fictional, not listed)", ms.ticker is None, str(ms.ticker))
    check("assertions load for both", len(load_assertions("coinbase-global")) > 5 and len(load_assertions("meridian-sands")) > 5)


def test_resilience():
    print("\n[4] Resilience — no crashes on edge cases")
    # SEC on a non-listed entity → [] (no ticker), not an exception
    ev = SecEarningsConnector().fetch(CustomerRef.load("meridian-sands"))
    check("SEC on non-listed customer → 0 events, no crash", ev == [])
    # unknown customer → clear error
    try:
        CustomerRef.load("does-not-exist")
        check("unknown customer raises", False)
    except FileNotFoundError:
        check("unknown customer raises FileNotFoundError", True)


# ── live tests (network) ─────────────────────────────────────────────────────
def test_live():
    print("\n[5] LIVE — real sources (network)")
    os.environ.setdefault("SEC_USER_AGENT", "amina-drift smoke (team@sablier.it)")
    cb = CustomerRef.load("coinbase-global")
    sec = SecEarningsConnector(limit=3, with_earnings=False).fetch(cb)
    check(f"SEC L1: {len(sec)} real Coinbase filings", len(sec) > 0)
    check("SEC events have real sec.gov URLs", all("sec.gov" in (e.source_url or "") for e in sec))
    l2 = SecEarningsConnector(limit=1, with_earnings=False, with_text=True, text_top_k=1).fetch(cb)
    cited = [e for e in l2 if e.payload.get("relevance_mode")]
    check(f"SEC L2: {len(cited)} cited passages (mode={cited[0].payload['relevance_mode'] if cited else 'n/a'})", len(cited) > 0)
    full = collect("coinbase-global", live=True)
    ok, why = _valid_events(full, "coinbase-global")
    check(f"full live roster: {len(full)} merged events, schema-valid", ok and len(full) > 10, why)


def main(argv):
    print("=== ingestion smoke test ===")
    test_offline_both()
    test_relevance_modes()
    test_customer_resolution()
    test_resilience()
    if "--live" in argv:
        try:
            test_live()
        except Exception as e:
            check(f"live tests crashed: {type(e).__name__}: {e}", False)
    print(f"\n=== {'ALL PASS ✅' if _failures == 0 else str(_failures) + ' FAILURES ❌'} ===")
    return 1 if _failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
