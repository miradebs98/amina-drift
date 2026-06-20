"""Stub connectors — uniform interface, ready for Mira to fill in.

Each returns [] live today but plugs into the runner exactly like a real connector. For the two
demo cases these signals are already covered by the authored fixtures (Meridian) — these stubs are
the roadmap to broaden coverage and to make Coinbase's screening real.
"""
from __future__ import annotations

from shared.schemas import EvidenceEvent
from backend.ingest.base import Connector, CustomerRef

# NOTE: SanctionsConnector graduated to a real connector → backend/ingest/sanctions.py


class RegistryConnector(Connector):
    """Corporate registry — ZEFIX (CH) / Companies House (UK) / ADGM / offshore.
    TODO(Mira): pick the registry by customer.country; emit REGISTRY_CHANGE / OWNERSHIP_CHANGE for
    name / legal-form / domicile / director / UBO changes. Meridian's ADGM events are fixtures."""
    name = "registry"
    source_label = "Registry"
    live = False

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        return []

# NOTE: FundingConnector graduated to a real connector → backend/ingest/funding.py
