"""Ingestion runner — run all connectors for a customer → one merged EvidenceEvent stream.

  OFFLINE_DEMO=true (default): replay fixtures only → deterministic, no network, no keys.
  OFFLINE_DEMO=false: run the live connectors (each caches to data/fixtures/ for offline reuse).

The merged, de-duplicated, time-sorted stream is what the drift engine (Miguel) consumes.

  python -m backend.ingest.runner coinbase-global          # offline (fixtures)
  OFFLINE_DEMO=false python -m backend.ingest.runner coinbase-global --live
"""
from __future__ import annotations

import os
import sys

from shared.schemas import EvidenceEvent
from backend.ingest.base import Connector, CustomerRef, offline
from backend.ingest.fixtures import FixtureConnector
from backend.ingest.sec_earnings import SecEarningsConnector
from backend.ingest.gdelt import GdeltConnector
from backend.ingest.news_rss import NewsRssConnector
from backend.ingest.wayback import WaybackConnector
from backend.ingest.gleif import GleifConnector
from backend.ingest.sanctions import SanctionsConnector
from backend.ingest.event_registry import EventRegistryConnector
from backend.ingest.funding import FundingConnector
from backend.ingest.cert_transparency import CertTransparencyConnector
from backend.ingest.stubs import RegistryConnector

# SEC_LEVEL2=true → also read 10-K text and emit cited passages relevant to each assertion
# (uses OpenAI embeddings if OPENAI_API_KEY is set, else lexical). Off by default (extra latency).
_LEVEL2 = os.getenv("SEC_LEVEL2", "false").lower() == "true"

# The full source roster. Add a source = add a line here.
LIVE_CONNECTORS: list[Connector] = [
    SecEarningsConnector(with_text=_LEVEL2),   # SEC filings + earnings calls (grain_lite)
    EventRegistryConnector(), # rich news + sentiment (partner key)
    GdeltConnector(),         # adverse media / news tone
    NewsRssConnector(),       # Google News
    WaybackConnector(),       # website change over time
    CertTransparencyConnector(),  # crt.sh — new infra subdomains (digital exhaust, pre-announcement)
    GleifConnector(),         # legal entity + ownership graph
    SanctionsConnector(),     # OpenSanctions/yente — sanctions + PEP screening (entity + UBOs)
    FundingConnector(),       # funding rounds + new investors → UBO re-screen (startup drift)
    RegistryConnector(),      # stub → ZEFIX/Companies House/ADGM
]


def collect(customer_id: str, *, live: bool | None = None, refresh: bool = False) -> list[EvidenceEvent]:
    """Return the merged EvidenceEvent stream for a customer."""
    customer = CustomerRef.load(customer_id)
    use_live = (not offline()) if live is None else live

    events: list[EvidenceEvent] = []
    if use_live:
        for c in LIVE_CONNECTORS:
            got = c.fetch_cached(customer, refresh=refresh)
            print(f"[{c.name:12}] {len(got):3d} events")
            events += got
        # always fold in authored fixtures (Meridian + any seeded signals)
        events += FixtureConnector().fetch(customer)
    else:
        events = FixtureConnector().fetch(customer)
        print(f"[fixtures   ] {len(events):3d} events (offline)")

    # de-dupe by id, sort oldest→newest
    seen, merged = set(), []
    for e in events:
        if e.id not in seen:
            seen.add(e.id)
            merged.append(e)
    merged.sort(key=lambda e: e.published_at)
    return merged


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m backend.ingest.runner <customer_id> [--live] [--refresh]")
        return 2
    customer_id = argv[0]
    live = "--live" in argv or None
    refresh = "--refresh" in argv
    events = collect(customer_id, live=live, refresh=refresh)
    print(f"\n=== {customer_id}: {len(events)} merged events ===")
    for e in events:
        d = e.published_at.date().isoformat()
        print(f"  {d}  {e.type.value:16} {e.source[:22]:22} | {e.summary[:64]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
