"""GDELT connector — adverse media / news (free, no key).

GDELT DOC 2.0 API indexes global news with tone. We query the entity name (+ optional risk
keywords) and emit one NEWS EvidenceEvent per article. Tone < 0 hints adverse media — a cheap
Stage-1 drift signal the engine can weight without an LLM.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from shared.schemas import EvidenceEvent, EvidenceType
from backend.ingest.base import Connector, CustomerRef, make_event

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
RISK_TERMS = "(fraud OR investigation OR lawsuit OR sanction OR probe OR breach OR regulator)"


class GdeltConnector(Connector):
    name = "gdelt"
    source_label = "GDELT"

    def __init__(self, max_records: int = 15, risk_only: bool = False, timespan: str = "24m"):
        self.max_records = max_records
        self.risk_only = risk_only
        self.timespan = timespan

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        query = f'"{customer.legal_name}"'
        if self.risk_only:
            query += f" {RISK_TERMS}"
        params = {
            "query": query, "mode": "artlist", "format": "json",
            "maxrecords": str(self.max_records), "sort": "datedesc", "timespan": self.timespan,
        }
        url = f"{GDELT_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "amina-drift/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", "replace") or "{}")
        out = []
        for a in data.get("articles", [])[: self.max_records]:
            title = a.get("title", "").strip()
            if not title:
                continue
            tone = a.get("tone")
            out.append(make_event(
                connector=self.name, customer=customer, type=EvidenceType.NEWS,
                summary=title,
                source=f"GDELT · {a.get('domain', 'news')}",
                source_url=a.get("url"),
                published_at=a.get("seendate", "20250101000000"),
                payload={"domain": a.get("domain"), "tone": tone, "language": a.get("language")},
                confidence=0.6, resolution_confidence=0.75,  # name-match only → lower
            ))
        return out
