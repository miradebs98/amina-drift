"""The 4 risk dimensions — the spine of 'connect the dots'.

KYC drift is dangerous because no single signal crosses a threshold; it's the COMBINATION of
quiet changes across dimensions over time. Tagging every belief and signal with its dimension lets
the engine fire on co-movement (≥N dimensions drifting together) and lets the UI show the
convergence. (AMINA's framework — Identity, Network, Behavioural, Contextual.)
"""
from __future__ import annotations

from enum import Enum


class Dimension(str, Enum):
    IDENTITY = "identity_ownership"     # WHO they are: UBO, directors, PEP, residency, name, domicile
    NETWORK = "network_risk"            # WHO they're connected to: partners, sanctions links, adverse media, shells
    BEHAVIOURAL = "behavioural_drift"   # WHAT their money does: volume, geographies, counterparties
    CONTEXTUAL = "contextual_change"    # life/industry: wealth source, business pivot, funding, litigation


# Assertion predicate → dimension
PREDICATE_DIMENSION: dict[str, Dimension] = {
    # Identity & Ownership
    "ubo": Dimension.IDENTITY, "directors": Dimension.IDENTITY,
    "ownership_structure": Dimension.IDENTITY, "pep_status": Dimension.IDENTITY,
    "domicile": Dimension.IDENTITY, "legal_form": Dimension.IDENTITY, "legal_name": Dimension.IDENTITY,
    "principal_place_of_business": Dimension.IDENTITY, "tax_residency": Dimension.IDENTITY,
    "tax_classification": Dimension.IDENTITY, "listing_status": Dimension.IDENTITY,
    # Network Risk
    "sanctions_status": Dimension.NETWORK, "adverse_media_status": Dimension.NETWORK,
    # Behavioural Drift
    "expected_monthly_volume": Dimension.BEHAVIOURAL, "counterparty_geographies": Dimension.BEHAVIOURAL,
    "activity_level": Dimension.BEHAVIOURAL, "financial_profile": Dimension.BEHAVIOURAL,
    # Contextual Changes
    "business_model": Dimension.CONTEXTUAL, "product_mix": Dimension.CONTEXTUAL,
    "industry_sector": Dimension.CONTEXTUAL, "operating_geographies": Dimension.CONTEXTUAL,
    "regulatory_status": Dimension.CONTEXTUAL, "source_of_funds": Dimension.CONTEXTUAL,
    "source_of_wealth": Dimension.CONTEXTUAL, "digital_asset_policy": Dimension.CONTEXTUAL,
    "digital_asset_holdings": Dimension.CONTEXTUAL, "domain": Dimension.CONTEXTUAL,
}

# EvidenceType → dimension
EVIDENCE_DIMENSION: dict[str, Dimension] = {
    "ownership_change": Dimension.IDENTITY, "registry_change": Dimension.IDENTITY,
    "pep_hit": Dimension.IDENTITY,
    "sanctions_hit": Dimension.NETWORK, "news": Dimension.NETWORK,   # generic news = adverse-media default
    "transaction": Dimension.BEHAVIOURAL,
    "website_change": Dimension.CONTEXTUAL, "funding": Dimension.CONTEXTUAL,
}


def dimension_for_predicate(predicate: str) -> Dimension:
    return PREDICATE_DIMENSION.get(predicate, Dimension.CONTEXTUAL)


def dimension_for_evidence(evidence_type: str) -> Dimension:
    return EVIDENCE_DIMENSION.get(evidence_type, Dimension.NETWORK)
