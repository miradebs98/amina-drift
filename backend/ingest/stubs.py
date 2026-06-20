"""Stub connectors — uniform interface, ready for Mira to fill in.

Each returns [] live today but plugs into the runner exactly like a real connector. For the two
demo cases these signals are already covered by the authored fixtures (Meridian) — these stubs are
the roadmap to broaden coverage and to make Coinbase's screening real.
"""
from __future__ import annotations

from shared.schemas import EvidenceEvent
from backend.ingest.base import Connector, CustomerRef


class SanctionsConnector(Connector):
    """OpenSanctions / yente — sanctions + PEP screening (entity + UBOs).
    TODO(Mira): POST name to https://api.opensanctions.org/match/default (free non-commercial) or
    self-host yente; emit SANCTIONS_HIT / PEP_HIT events with the matched list + score.
    Doubles as entity resolution (fuzzy match). Coinbase has a real historic OFAC settlement (CB6)."""
    name = "sanctions"
    source_label = "OpenSanctions"
    live = False

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        return []


class RegistryConnector(Connector):
    """Corporate registry — ZEFIX (CH) / Companies House (UK) / ADGM / offshore.
    TODO(Mira): pick the registry by customer.country; emit REGISTRY_CHANGE / OWNERSHIP_CHANGE for
    name / legal-form / domicile / director / UBO changes. Meridian's ADGM events are fixtures."""
    name = "registry"
    source_label = "Registry"
    live = False

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        return []


class FundingConnector(Connector):
    """Funding / scale signals — Crunchbase / funding news.
    TODO(Mira): emit FUNDING events (round, amount, investors) → scale-risk drift. Can be derived
    from the news connectors with a funding filter to avoid a paid Crunchbase key."""
    name = "funding"
    source_label = "Funding"
    live = False

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        return []
