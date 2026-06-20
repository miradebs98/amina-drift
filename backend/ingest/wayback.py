"""Wayback Machine connector — website change over time (free, no key).

THE differentiator source. The CDX API lists historical snapshots of a customer's domain. We
collapse by content digest, so each emitted event marks a point where the homepage content
*actually changed* — the raw fuel for slow business-model drift (e.g. SaaS → crypto). Most teams
never diff a customer's website over time.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from shared.schemas import EvidenceEvent, EvidenceType
from backend.ingest.base import Connector, CustomerRef, make_event

CDX_URL = "http://web.archive.org/cdx/search/cdx"


class WaybackConnector(Connector):
    name = "wayback"
    source_label = "Wayback Machine"

    def __init__(self, max_changes: int = 8, from_year: int = 2019):
        self.max_changes = max_changes
        self.from_year = from_year

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        if not customer.domain:
            return []
        params = {
            "url": customer.domain, "output": "json",
            "fl": "timestamp,original,digest,statuscode",
            "collapse": "digest",                 # one row per distinct content version
            "from": f"{self.from_year}0101", "filter": "statuscode:200",
        }
        url = f"{CDX_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "amina-drift/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            rows = json.loads(r.read().decode("utf-8", "replace") or "[]")
        if not rows or len(rows) < 2:
            return []
        rows = rows[1:]  # drop header
        # Keep evenly-spaced content changes (signal = the homepage was rewritten)
        step = max(1, len(rows) // self.max_changes)
        out = []
        for i in range(0, len(rows), step):
            ts, original, digest = rows[i][0], rows[i][1], rows[i][2]
            snap = f"http://web.archive.org/web/{ts}/{original}"
            out.append(make_event(
                connector=self.name, customer=customer, type=EvidenceType.WEBSITE_CHANGE,
                summary=f"{customer.legal_name} homepage content changed (snapshot {ts[:8]})",
                source="Wayback Machine",
                source_url=snap,
                published_at=ts,
                payload={"digest": digest, "snapshot_ts": ts, "domain": customer.domain},
                confidence=0.7,
            ))
            if len(out) >= self.max_changes:
                break
        return out
