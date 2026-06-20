"""FixtureConnector — replays seeded EvidenceEvents from data/fixtures/.

Two jobs:
  1. The ONLY source for Meridian Sands (fictional → no live data exists).
  2. The offline-demo backbone: replays cached/authored events so the full pipeline runs with
     no network and no keys (great for the stage demo + CI).

Reads any `data/fixtures/<customer_id>-events*.json` (the authored `{"events": [...]}` files)
AND any `<customer_id>.<connector>.cache.json` (live fetches cached by other connectors).
"""
from __future__ import annotations

import json
from pathlib import Path

from shared.schemas import EvidenceEvent
from backend.ingest.base import Connector, CustomerRef, FIXTURES_DIR


class FixtureConnector(Connector):
    name = "fixtures"
    source_label = "fixture"
    live = False

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        # Scan all event/cache fixtures and keep events whose customer_id matches — robust to
        # file naming (e.g. "meridian-events.example.json" for customer "meridian-sands").
        events: list[EvidenceEvent] = []
        seen: set[str] = set()
        files = sorted(set(FIXTURES_DIR.glob("*events*.json")) | set(FIXTURES_DIR.glob("*.cache.json")))
        for fp in files:
            events.extend(self._load(fp, customer.customer_id, seen))
        return events

    @staticmethod
    def _load(fp: Path, customer_id: str, seen: set[str]) -> list[EvidenceEvent]:
        out: list[EvidenceEvent] = []
        try:
            raw = json.loads(fp.read_text())
        except Exception as e:
            print(f"[fixtures] skip {fp.name}: {e}")
            return out
        rows = raw.get("events", raw) if isinstance(raw, dict) else raw
        for row in rows:
            if not isinstance(row, dict) or "id" not in row or row["id"] in seen:
                continue
            if row.get("customer_id") != customer_id:
                continue
            try:
                out.append(EvidenceEvent(**row))
                seen.add(row["id"])
            except Exception as e:
                print(f"[fixtures] invalid event in {fp.name}: {e}")
        return out
