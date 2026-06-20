"""GLEIF connector — legal entity + ownership graph (free, no key).

GLEIF's LEI API resolves an entity and exposes parent/child relationships. We emit:
  - a REGISTRY_CHANGE event for the entity record (legal name, jurisdiction, status), and
  - OWNERSHIP_CHANGE events for any direct parent/child links (corporate-structure signal).
Diffing these over time catches structural drift (new offshore parent, status change).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from shared.schemas import EvidenceEvent, EvidenceType
from backend.ingest.base import Connector, CustomerRef, make_event

GLEIF_API = "https://api.gleif.org/api/v1/lei-records"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "amina-drift/0.1",
                                               "Accept": "application/vnd.api+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


class GleifConnector(Connector):
    name = "gleif"
    source_label = "GLEIF"

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        # Resolve the LEI record by lei (preferred) or legal name.
        if customer.lei:
            url = f"{GLEIF_API}/{urllib.parse.quote(customer.lei)}"
            rec = (_get(url) or {}).get("data")
            records = [rec] if rec else []
        else:
            q = urllib.parse.urlencode({"filter[entity.legalName]": customer.legal_name, "page[size]": "1"})
            records = (_get(f"{GLEIF_API}?{q}") or {}).get("data", [])
        if not records:
            return []
        rec = records[0]
        attrs = rec.get("attributes", {})
        entity = attrs.get("entity", {})
        lei = attrs.get("lei") or rec.get("id")
        name = (entity.get("legalName") or {}).get("name", customer.legal_name)
        juris = entity.get("jurisdiction")
        status = entity.get("status")
        out = [make_event(
            connector=self.name, customer=customer, type=EvidenceType.REGISTRY_CHANGE,
            summary=f"GLEIF LEI record: {name} — jurisdiction {juris}, status {status}",
            source="GLEIF",
            source_url=f"https://search.gleif.org/#/record/{lei}",
            published_at=(attrs.get("registration", {}) or {}).get("lastUpdateDate", "2025-01-01"),
            payload={"lei": lei, "jurisdiction": juris, "status": status},
            confidence=0.9, resolution_confidence=0.95 if customer.lei else 0.7,
        )]
        # Direct parent relationship (ownership structure)
        rels = rec.get("relationships", {})
        parent_link = ((rels.get("direct-parent", {}) or {}).get("links", {}) or {}).get("related")
        if parent_link:
            try:
                p = (_get(parent_link) or {}).get("data", {})
                pname = ((p.get("attributes", {}).get("entity", {}) or {}).get("legalName", {}) or {}).get("name")
                if pname:
                    out.append(make_event(
                        connector=self.name, customer=customer, type=EvidenceType.OWNERSHIP_CHANGE,
                        summary=f"GLEIF direct parent on file: {pname}",
                        source="GLEIF", source_url=f"https://search.gleif.org/#/record/{lei}",
                        published_at="2025-01-01", payload={"direct_parent": pname}, confidence=0.85,
                    ))
            except Exception:
                pass
        return out
