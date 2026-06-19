"""Assertion — what the bank believes about a customer (Layer 2 KYC profile).

A KYC profile is NOT a document — it's a set of dated, sourced, testable assertions.
Drift detection = continuously re-validating each assertion against the evidence stream.

OWNER of content/fields: Giacomo (ex-KYC RM — source of truth on what a real KYC profile holds).
OWNER of format: locked by all three. Ping before changing.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Predicate(str, Enum):
    """The attribute of the customer this assertion is about. Extend as needed (ping team)."""
    BUSINESS_MODEL = "business_model"            # e.g. "B2B SaaS / payments software"
    LEGAL_FORM = "legal_form"                    # e.g. "AG", "GmbH"
    DOMICILE = "domicile"                        # e.g. "Zug, CH"
    UBO = "ubo"                                  # beneficial owners {name: pct}
    DIRECTORS = "directors"                      # board / signatories
    DOMAIN = "domain"                            # primary website domain
    EXPECTED_MONTHLY_VOLUME = "expected_monthly_volume"   # behavioural envelope (CHF)
    COUNTERPARTY_GEOGRAPHIES = "counterparty_geographies" # expected country set
    PRODUCT_MIX = "product_mix"                  # expected products/services used
    RISK_TIER = "risk_tier"                      # LOW / MEDIUM / HIGH (the rolled-up belief)
    ACTIVITY_LEVEL = "activity_level"            # e.g. "dormant", "active"


class AssertionStatus(str, Enum):
    VALID = "valid"                  # believed true, recently verified
    STALE = "stale"                  # confidence decayed past threshold — re-verify
    CONTRADICTED = "contradicted"    # public evidence contradicts it
    UNDER_REVIEW = "under_review"    # flagged, awaiting human adjudication


class ExpectedEnvelope(BaseModel):
    """For behavioural assertions: the expected range/set authored at onboarding.
    A breach of this envelope is a drift signal (money-mule, dormancy break, scale change)."""
    low: Optional[float] = None
    high: Optional[float] = None
    allowed_set: Optional[list[str]] = None      # e.g. allowed counterparty countries
    unit: Optional[str] = None                   # e.g. "CHF/month"


class Assertion(BaseModel):
    """One atomic, testable belief the bank holds about a customer."""
    id: str
    customer_id: str
    predicate: Predicate
    value: str                                   # the believed value (stringified; UBO/dicts as JSON)
    expected_envelope: Optional[ExpectedEnvelope] = None
    as_of: date                                  # when this was established
    last_verified: date                          # belief clock — drives staleness/decay
    source: str                                  # e.g. "onboarding deck", "ZEFIX"
    source_url: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    status: AssertionStatus = AssertionStatus.VALID
    notes: Optional[str] = None                  # Giacomo's RM context for the demo

    # TODO(Giacomo): author the real demo customer's assertions in data/customers/.
    # TODO(Miguel): decay confidence over time; flip status on contradiction.
