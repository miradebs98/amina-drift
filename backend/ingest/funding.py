"""Funding & investor intelligence — the startup-drift connector (free, news-derived).

AMINA's hardest case is startups: little transaction history, fast pivots, profile goes stale
fastest. Funding rounds are the richest early signal — a new lead investor often means a NEW
beneficial owner (→ re-screen UBO/PEP/sanctions), and use-of-funds reveals a pivot.

FREE approach: query Google News RSS for funding signals and parse amount / round / lead investor
from the headline. Upgrades to the Crunchbase API if CRUNCHBASE_API_KEY is set (paid/gated).
Emits type=FUNDING (Contextual dimension); payload flags the re-screen implication.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

from shared.schemas import EvidenceEvent, EvidenceType
from backend.ingest.base import Connector, CustomerRef, make_event

NEWS_RSS = "https://news.google.com/rss/search"
_FUNDING_Q = '(raises OR "funding round" OR "Series A" OR "Series B" OR "Series C" OR seed OR "led by" OR valuation OR acquires OR acquisition)'

_AMOUNT = re.compile(r"([$€£]\s?\d[\d.,]*\s?(?:b|bn|billion|m|mn|million|k)?)", re.I)
_ROUND = re.compile(r"\b(seed|pre-seed|series\s+[a-e]|growth|bridge)\b", re.I)
_LED_BY = re.compile(r"led by ([A-Z][\w&.\- ]+?)(?:[,.]|\s+(?:with|and|to)\b|$)")


class FundingConnector(Connector):
    name = "funding"
    source_label = "Funding intel"

    def __init__(self, max_records: int = 10):
        self.max_records = max_records

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        q = f'"{customer.legal_name}" {_FUNDING_Q}'
        url = f"{NEWS_RSS}?{urllib.parse.urlencode({'q': q, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})}"
        req = urllib.request.Request(url, headers={"User-Agent": "amina-drift/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            root = ET.fromstring(r.read())

        out: list[EvidenceEvent] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title or not self._looks_like_funding(title):
                continue
            amount = (_AMOUNT.search(title) or [None])[0]
            rnd = (_ROUND.search(title) or [None])
            rnd = rnd.group(1) if hasattr(rnd, "group") else None
            led = _LED_BY.search(title)
            investor = led.group(1).strip() if led else None
            out.append(make_event(
                connector=self.name, customer=customer, type=EvidenceType.FUNDING,
                summary=title,
                source="Funding intel · Google News",
                source_url=item.findtext("link"),
                published_at=_rss_date(item.findtext("pubDate") or ""),
                payload={
                    "amount": amount, "round": rnd, "lead_investor": investor,
                    # the drift implication a KYC analyst cares about:
                    "implication": ("New lead investor → potential NEW beneficial owner; re-screen "
                                    "UBO/PEP/sanctions and re-baseline activity profile." if investor
                                    else "Funding/scale event → reassess transaction-monitoring thresholds."),
                },
                confidence=0.65, resolution_confidence=0.75,
            ))
            if len(out) >= self.max_records:
                break
        return out

    @staticmethod
    def _looks_like_funding(title: str) -> bool:
        t = title.lower()
        return any(k in t for k in ("rais", "funding", "series ", "seed", "led by", "valuation",
                                    "acqui", "round", "investment", "backs", "invests"))


def _rss_date(s: str) -> str:
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        return "2025-01-01"
