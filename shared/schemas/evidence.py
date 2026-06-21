"""EvidenceEvent / Snapshot — what Layer 1 connectors emit.

Connectors produce these; the drift engine consumes them. This shape is the cross-layer contract.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    NEWS = "news"                        # adverse-media / news article (GDELT, News RSS)
    REGISTRY_CHANGE = "registry_change"  # name/legal-form/domicile change (GLEIF, ZEFIX)
    OWNERSHIP_CHANGE = "ownership_change"# new UBO/shareholder/director
    SANCTIONS_HIT = "sanctions_hit"      # OpenSanctions / yente match
    PEP_HIT = "pep_hit"
    WEBSITE_CHANGE = "website_change"    # Wayback diff / domain switch
    FUNDING = "funding"                  # funding round / Crunchbase
    TRANSACTION = "transaction"          # internal (Layer 2) behavioural signal


class EvidenceEvent(BaseModel):
    """One dated, sourced public (or internal) signal about an entity."""
    id: str
    entity_ref: str                      # the raw entity name/id as seen in the source
    customer_id: Optional[str] = None    # set at emission once matched to a customer (None = unresolved)
    resolution_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    type: EvidenceType
    summary: str                         # one-line human-readable summary (for the timeline)
    payload: dict[str, Any] = Field(default_factory=dict)  # structured details
    source: str                          # "GDELT", "ZEFIX", "yente", ...
    source_url: Optional[str] = None     # REQUIRED for anything shown in the UI (citation)
    published_at: datetime
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    raw_ref: Optional[str] = None        # hash/pointer to cached raw payload (data/fixtures/)

    # Note: connectors fill these; raw payload is cached to data/fixtures/ for offline demo.
    # Note: customer_id + resolution_confidence are set at emission (matched by the customer's known
    # identifiers — ticker/LEI/domain/name — and confidence-gated).


class Snapshot(BaseModel):
    """A reconstructed public-profile snapshot of a customer at a point in time.
    The sequence of snapshots over time is what makes SLOW structural drift visible."""
    customer_id: str
    as_of: date
    business_description: Optional[str] = None   # scraped/derived text (for embedding trajectory)
    domain: Optional[str] = None
    domicile: Optional[str] = None
    legal_form: Optional[str] = None
    ubo: Optional[dict[str, float]] = None
    signal_mix: dict[str, float] = Field(default_factory=dict)  # topic/geo distribution this window
    source_urls: list[str] = Field(default_factory=list)

    # Note: the time-compressed snapshot series for the trajectory detector is assembled in
    # backend/drift/client_state.py.
    # Note: consecutive snapshots are diffed / the embedding trajectory is tracked across the series.
