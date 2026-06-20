"""Google News RSS connector — news / adverse media (free, no key).

Parses the Google News RSS search feed for the entity name. Stdlib XML only.
Complements GDELT (different coverage); both emit NEWS EvidenceEvents.
"""
from __future__ import annotations

import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

from shared.schemas import EvidenceEvent, EvidenceType
from backend.ingest.base import Connector, CustomerRef, make_event

NEWS_RSS = "https://news.google.com/rss/search"


class NewsRssConnector(Connector):
    name = "news_rss"
    source_label = "Google News"

    def __init__(self, max_records: int = 12, risk_only: bool = False):
        self.max_records = max_records
        self.risk_only = risk_only

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        q = f'"{customer.legal_name}"'
        if self.risk_only:
            q += " (fraud OR investigation OR sanctions OR lawsuit OR probe)"
        url = f"{NEWS_RSS}?{urllib.parse.urlencode({'q': q, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})}"
        req = urllib.request.Request(url, headers={"User-Agent": "amina-drift/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            root = ET.fromstring(r.read())
        out = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = item.findtext("link")
            pub = item.findtext("pubDate") or ""
            src = (item.find("{*}source") is not None and item.find("{*}source").text) or "Google News"
            if not title:
                continue
            out.append(make_event(
                connector=self.name, customer=customer, type=EvidenceType.NEWS,
                summary=title,
                source=f"Google News · {src}",
                source_url=link,
                published_at=_rss_date(pub),
                payload={"publisher": src},
                confidence=0.6, resolution_confidence=0.75,
            ))
            if len(out) >= self.max_records:
                break
        return out


def _rss_date(s: str) -> str:
    # RFC-822 "Mon, 05 May 2025 14:00:00 GMT" → ISO date; fall back handled by base._as_dt
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        return "2025-01-01"
