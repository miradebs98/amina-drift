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
    """The attribute of the customer an assertion is about.

    Grouped by KYC section, mirroring a real AMINA B2B onboarding file (Giacomo, ex-RM).
    KEY DISTINCTION: not every field a bank collects is a *monitorable* assertion. Immutable
    identity (incorporation date, commercial-register number, TIN) lives in the `entity_profile`
    header of the customer file, NOT here — the drift engine never re-validates it. Predicates
    are the dated, testable BELIEFS the engine re-checks against public intelligence.

    ⭐ = high-value drift target exercised by the demo. Extend as needed (ping team).
    """
    # --- Business & activity (categorical beliefs that get CONTRADICTED) ---
    BUSINESS_MODEL = "business_model"            # ⭐ "B2B securitization" → broken by a crypto pivot
    INDUSTRY_SECTOR = "industry_sector"          # NOGA/NAICS-style classification
    PRODUCT_MIX = "product_mix"                  # products/services used (incl. services requested at AMINA)
    LISTING_STATUS = "listing_status"            # private vs listed on a stock exchange

    # --- Identity / legal (slow-moving, but material when they change) ---
    LEGAL_FORM = "legal_form"                    # e.g. "AG", "GmbH"
    DOMICILE = "domicile"                        # registered seat: country of incorporation + reg. address
    PRINCIPAL_PLACE_OF_BUSINESS = "principal_place_of_business"  # where actually managed/operated
    DOMAIN = "domain"                            # primary website domain

    # --- Ownership & control ---
    UBO = "ubo"                                  # ⭐ beneficial owners >25% {name: pct/role}
    DIRECTORS = "directors"                      # board / authorised signatories
    OWNERSHIP_STRUCTURE = "ownership_structure"  # type + chain (holding / organigram)

    # --- Geographic footprint (behavioural envelopes) ---
    OPERATING_GEOGRAPHIES = "operating_geographies"       # where the business operates
    COUNTERPARTY_GEOGRAPHIES = "counterparty_geographies" # clients/suppliers country set

    # --- Financial profile & funds (envelopes + source) ---
    EXPECTED_MONTHLY_VOLUME = "expected_monthly_volume"   # behavioural envelope (CHF)
    FINANCIAL_PROFILE = "financial_profile"      # turnover / total assets band
    SOURCE_OF_WEALTH = "source_of_wealth"        # ⭐ how the entity's wealth was historically generated
    SOURCE_OF_FUNDS = "source_of_funds"          # ⭐ origin of the funds transacting through AMINA
    ACTIVITY_LEVEL = "activity_level"            # e.g. "dormant", "active"

    # --- Digital assets (AMINA-specific — the crypto KYC core) ---
    DIGITAL_ASSET_POLICY = "digital_asset_policy"      # ⭐ digital-asset treasury policy on file?
    DIGITAL_ASSET_HOLDINGS = "digital_asset_holdings"  # ⭐ classes held + source (exchange/mining)

    # --- Tax ---
    TAX_RESIDENCY = "tax_residency"              # entity tax residence + TIN
    TAX_CLASSIFICATION = "tax_classification"    # FATCA / CRS status

    # --- Screening & compliance status (the headline drift targets) ---
    REGULATORY_STATUS = "regulatory_status"      # regulated/supervised? licenses held + regulator
    PEP_STATUS = "pep_status"                    # ⭐ any PEP among directors / UBOs
    SANCTIONS_STATUS = "sanctions_status"        # ⭐ entity / director / UBO sanctions exposure
    ADVERSE_MEDIA_STATUS = "adverse_media_status"# ⭐ investigations/litigation/financial-crime media

    # --- Rolled-up output (the KYC's verdict; drift is framed as movement of this) ---
    RISK_SCORE = "risk_score"                    # ⭐ 0–100 composite KYC risk score — the demo re-scores it LOW→HIGH
    RISK_TIER = "risk_tier"                      # derived band of risk_score (LOW 0–33 / MED 34–66 / HIGH 67–100), display only


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
