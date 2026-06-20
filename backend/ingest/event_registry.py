"""Event Registry (newsapi.ai) connector — rich news + sentiment (partner-provided key).

The hackathon provides Event Registry access (the "News MCP"). Its REST API is much richer than
Google News RSS / GDELT: per-article SENTIMENT, source, date, concepts/entities, and clustered
"events". We use article sentiment as a cheap adverse-media drift signal (negative tone spike) and
the article body/concepts as business-change signal.

Needs EVENTREGISTRY_API_KEY (or NEWSAPI_AI_KEY) in .env. Degrades to [] if absent/unreachable.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from shared.schemas import EvidenceEvent, EvidenceType
from backend.ingest.base import Connector, CustomerRef, make_event

# Default = public Event Registry. Override with EVENTREGISTRY_BASE_URL if your credentials are
# for the partner News MCP gateway (a different host that speaks the same API).
ER_BASE = os.getenv("EVENTREGISTRY_BASE_URL", "https://eventregistry.org").rstrip("/")
ER_URL = f"{ER_BASE}/api/v1/article/getArticles"


class EventRegistryConnector(Connector):
    name = "event_registry"
    source_label = "Event Registry"

    def __init__(self, count: int = 20, risk_only: bool = False):
        self.count = count
        self.risk_only = risk_only
        self.api_key = os.getenv("EVENTREGISTRY_API_KEY") or os.getenv("NEWSAPI_AI_KEY")

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        if not self.api_key:
            print("[event_registry] no EVENTREGISTRY_API_KEY → skipped")
            return []
        body = {
            "action": "getArticles",
            "keyword": customer.legal_name,
            "keywordOper": "and",
            "lang": ["eng"],
            "articlesSortBy": "date",
            "articlesCount": self.count,
            "includeArticleSentiment": True,
            "includeArticleConcepts": True,
            "resultType": "articles",
            "apiKey": self.api_key,
        }
        if self.risk_only:
            body["keyword"] = [customer.legal_name, "investigation OR fraud OR sanctions OR lawsuit OR probe"]
            body["keywordOper"] = "and"
        req = urllib.request.Request(
            ER_URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "amina-drift/0.1"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as e:
            print(f"[event_registry] HTTP {e.code} (check EVENTREGISTRY_API_KEY) → skipping")
            return []
        except Exception as e:
            print(f"[event_registry] unreachable ({type(e).__name__}) → skipping")
            return []
        if data.get("error"):
            print(f"[event_registry] API error: {data['error']} → skipping")
            return []

        events: list[EvidenceEvent] = []
        for a in data.get("articles", {}).get("results", [])[: self.count]:
            title = (a.get("title") or "").strip()
            if not title:
                continue
            sentiment = a.get("sentiment")            # -1..+1 (None if unscored)
            concepts = [c.get("label", {}).get("eng") for c in (a.get("concepts") or [])[:5]]
            events.append(make_event(
                connector=self.name, customer=customer, type=EvidenceType.NEWS,
                summary=title,
                source=f"Event Registry · {(a.get('source') or {}).get('title', 'news')}",
                source_url=a.get("url"),
                published_at=a.get("date") or a.get("dateTime") or "2025-01-01",
                payload={"sentiment": sentiment, "concepts": [c for c in concepts if c],
                         "publisher": (a.get("source") or {}).get("title")},
                # negative-sentiment articles get higher confidence as a *risk* signal
                confidence=0.7 if (sentiment is not None and sentiment < -0.2) else 0.6,
                resolution_confidence=0.8,
            ))
        print(f"[event_registry] {len(events)} articles (sentiment-tagged)")
        return events
