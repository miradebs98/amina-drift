"""Data-separation + masking policy — Layer-1 (public) vs Layer-2 (internal KYC).

The challenge's Data-Security requirement: "data separation between public and internal data" +
"data masking" + RBAC. Public Layer-1 evidence (news, registry, sanctions hits) is served freely;
the internal Layer-2 KYC dossier carries restricted, PII-grade fields (beneficial ownership,
source of funds/wealth, PEP detail, tax IDs) that are MASKED by default and only returned to an
authorised role. Every reveal of restricted data is written to the immutable audit log.

This is presentation-layer only: the engine has already scored on the full profile before any
masking happens (mask_customer never touches the object the scorer reads — it deep-copies). So
masking can never affect drift scores, alerts, or decisions.
"""
from __future__ import annotations

import copy
from typing import Optional

# The roles allowed to view (reveal) restricted Layer-2 KYC fields. Analyst is need-to-know:
# masked by default. Reuses the same role vocabulary as govern/rbac.py.
REVEAL_ROLES = {"mlro", "compliance", "admin"}

POLICY_VERSION = "data-policy v1"

# Restricted KYC predicates (assertion.value is masked). Beneficial ownership, the people behind
# the entity, and source-of-funds/wealth are the PII-grade fields a bank gates by need-to-know.
RESTRICTED_PREDICATES = {
    "ubo",
    "directors",
    "ownership_structure",
    "source_of_funds",
    "source_of_wealth",
    "pep_status",
}

# Restricted static-identity fields (entity_profile.*) — tax identifiers.
RESTRICTED_ENTITY_FIELDS = {"entity_tin"}

# Shown in place of a restricted value (kept free of "{" so the UI's JSON-aware value formatter
# treats it as plain text).
MASK_TOKEN = "•••••• — restricted (Layer 2 · reveal requires MLRO/Compliance)"


def can_reveal(role: Optional[str]) -> bool:
    return (role or "").lower() in REVEAL_ROLES


def restricted_field_labels(cust: dict) -> list[str]:
    """Human-readable list of which restricted fields THIS customer actually carries
    (for the audit entry + the UI banner). Never includes the values."""
    labels: list[str] = []
    for a in cust.get("assertions", []):
        if a.get("predicate") in RESTRICTED_PREDICATES:
            labels.append(a["predicate"])
    ep = cust.get("entity_profile", {}) or {}
    for f in RESTRICTED_ENTITY_FIELDS:
        if ep.get(f):
            labels.append(f)
    return labels


def mask_customer(cust: dict) -> dict:
    """Return a DEEP COPY of the customer dict with restricted Layer-2 fields masked.

    Never mutates the input (the caller's cached, full object stays intact — the engine and the
    decision flow keep reading the real values)."""
    masked = copy.deepcopy(cust)
    for a in masked.get("assertions", []):
        if a.get("predicate") in RESTRICTED_PREDICATES:
            a["value"] = MASK_TOKEN
            a["restricted"] = True            # marker the UI can style; harmless extra key
    ep = masked.get("entity_profile")
    if isinstance(ep, dict):
        for f in RESTRICTED_ENTITY_FIELDS:
            if ep.get(f):
                ep[f] = MASK_TOKEN
    return masked


def apply(case: dict, role: Optional[str]) -> dict:
    """Apply the data policy to a built CustomerCase for a given role.

    Authorised role → return as-is (full). Otherwise → return a copy with the customer masked.
    Only `case["customer"]` is masked; the public Layer-1 `events` are untouched."""
    if can_reveal(role):
        return case
    out = dict(case)                          # shallow copy of the case wrapper
    out["customer"] = mask_customer(case["customer"])
    out["data_masked"] = True                 # transparency flag (additive, backward-compatible)
    return out
