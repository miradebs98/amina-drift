"""Sanctions + PEP screening — OpenSanctions / yente (free).

Screens the customer AND its UBOs/directors against the OpenSanctions `default` dataset
(OFAC + EU + UN + UK + PEPs + crime/debarment). Emits SANCTIONS_HIT / PEP_HIT for strong matches.

Cost: FREE. Two ways to run (set in .env):
  - self-hosted yente (Apache-2.0, Docker, keyless)  → YENTE_BASE_URL=http://localhost:8000
  - hosted API (free non-commercial, needs a free key) → OPENSANCTIONS_API_KEY=...
Default base = https://api.opensanctions.org. Degrades to [] if unreachable / unauthorised.

Doubles as a screening-grade entity check: a match also tells us the queried name resolves to a
known sanctioned/PEP entity (with a confidence score).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from shared.schemas import EvidenceEvent, EvidenceType
from backend.ingest.base import Connector, CustomerRef, make_event, load_assertions

DEFAULT_BASE = "https://api.opensanctions.org"
MIN_SCORE = 0.70          # below this = not a confident match (avoid false positives)


def _names_to_screen(customer: CustomerRef) -> list[tuple[str, str]]:
    """(schema, name) pairs: the entity + each UBO/director from its KYC assertions."""
    out: list[tuple[str, str]] = [("Company", customer.legal_name)]
    for a in load_assertions(customer.customer_id):
        if a.get("predicate") in ("ubo", "directors"):
            val = a.get("value", "")
            try:                                   # UBO stored as JSON dict {name: role}
                for name in json.loads(val).keys():
                    out.append(("Person", name))
            except Exception:                      # or a plain string
                if val:
                    out.append(("Person", val[:80]))
    # de-dup, keep order
    seen, uniq = set(), []
    for schema, name in out:
        k = name.lower().strip()
        if name and k not in seen:
            seen.add(k)
            uniq.append((schema, name))
    return uniq


class SanctionsConnector(Connector):
    name = "sanctions"
    source_label = "OpenSanctions"

    def __init__(self, dataset: str = "default", min_score: float = MIN_SCORE):
        self.base = (os.getenv("YENTE_BASE_URL") or os.getenv("OPENSANCTIONS_BASE") or DEFAULT_BASE).rstrip("/")
        self.dataset = dataset
        self.min_score = min_score
        self.api_key = os.getenv("OPENSANCTIONS_API_KEY")

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        targets = _names_to_screen(customer)
        queries = {
            f"q{i}": {"schema": schema, "properties": {"name": [name]}}
            for i, (schema, name) in enumerate(targets)
        }
        body = json.dumps({"queries": queries}).encode()
        url = f"{self.base}/match/{self.dataset}"
        headers = {"Content-Type": "application/json", "User-Agent": "amina-drift/0.1"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                print("[sanctions] auth required — set OPENSANCTIONS_API_KEY (free) or "
                      "YENTE_BASE_URL (self-hosted yente). Skipping.")
            else:
                print(f"[sanctions] HTTP {e.code} → skipping")
            return []
        except Exception as e:
            print(f"[sanctions] unreachable ({type(e).__name__}) → skipping")
            return []

        events: list[EvidenceEvent] = []
        responses = data.get("responses", {})
        for i, (schema, name) in enumerate(targets):
            for res in responses.get(f"q{i}", {}).get("results", []):
                score = res.get("score", 0.0)
                if score < self.min_score:
                    continue
                topics = (res.get("properties", {}) or {}).get("topics", []) or []
                is_pep = any("pep" in t for t in topics)
                etype = EvidenceType.PEP_HIT if (is_pep and "sanction" not in topics) else EvidenceType.SANCTIONS_HIT
                caption = res.get("caption", name)
                events.append(make_event(
                    connector=self.name, customer=customer, type=etype,
                    # NAME-only match → a POTENTIAL match to verify, NOT a confirmed identity.
                    # The human analyst must disambiguate (DOB/nationality). This is why HITL exists.
                    summary=(f"Potential {('PEP' if etype == EvidenceType.PEP_HIT else 'sanctions/watchlist')} "
                             f"match (NAME-ONLY, verify identity): '{name}' ~ {caption} "
                             f"[{', '.join(topics) or 'listed'}], name-score {score:.2f}"),
                    source="OpenSanctions",
                    source_url=f"https://www.opensanctions.org/entities/{res.get('id', '')}/",
                    published_at="2026-01-01",
                    payload={"screened_name": name, "matched": caption, "name_score": round(score, 3),
                             "match_basis": "name-only", "needs_human_verification": True,
                             "topics": topics, "datasets": res.get("datasets", [])},
                    # confidence reflects MATCH-on-name, not identity certainty → deliberately capped
                    confidence=min(0.6, score), resolution_confidence=round(score * 0.5, 2),
                ))
        print(f"[sanctions] screened {len(targets)} names → {len(events)} hits")
        return events
