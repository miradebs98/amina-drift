"""DriftAlert — a detected drift, with its explanation and governance state.

Produced by the drift engine; the UI renders these, the cascade attaches cost metadata, and
govern attaches the human decision. This shape is the UI contract.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DriftType(str, Enum):
    EVENT = "event"            # discrete: one event contradicts one assertion
    STRUCTURAL = "structural"  # slow trajectory drift across snapshots (the headline)


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GovernanceState(str, Enum):
    PENDING = "pending"        # awaiting human review (HITL)
    APPROVED = "approved"      # analyst confirmed the flag
    DISMISSED = "dismissed"    # analyst overrode (false positive)
    ESCALATED = "escalated"    # sent to compliance / EDD


class DriftAlert(BaseModel):
    """The unit the analyst sees. Every field below the line is REQUIRED for explainability."""
    id: str
    customer_id: str
    drift_type: DriftType
    flag: str                              # maps to a brief use-case flag, e.g.
                                           # "Ownership Change – KYC Drift", "Material Business Model Change"
    severity: Severity
    drift_score: float                     # contribution to risk re-tiering (0..1)
    # risk_score is a DERIVED OUTPUT (computed by the scoring model), NOT a monitored assertion.
    # The onboarding baseline lives in customer.risk_model.onboarding_score; the engine recomputes it.
    old_risk_score: Optional[int] = None   # 0–100 score BEFORE drift (rolled-up KYC output)
    new_risk_score: Optional[int] = None   # 0–100 score AFTER drift → the number that moves on stage
    old_risk_tier: str                     # derived band of old_risk_score, e.g. "LOW"
    new_risk_tier: str                     # derived band of new_risk_score, e.g. "HIGH" → green→amber→red

    # --- explainability (no alert without these) ---
    contradicted_assertion_id: Optional[str] = None   # the PRIMARY belief invalidated (the headline)
    also_contradicts: list[str] = Field(default_factory=list)  # other assertion ids this drift episode breaks
    evidence_ids: list[str] = Field(default_factory=list)  # EvidenceEvent ids (each has source_url)
    rationale: str                         # human-readable why, grounded in the evidence
    what_would_flip: Optional[str] = None  # contestability: what would change this decision
    recommended_action: str                # echo the brief's "recommended action" column
    confidence: float = Field(ge=0.0, le=1.0)

    # --- cost metadata (the cascade fills these) ---
    stage_reached: int = 1                 # 1 cheap / 2 LLM / 3 deep
    model_used: Optional[str] = None
    tokens_used: int = 0

    # --- governance (govern/ fills these via HITL) ---
    governance_state: GovernanceState = GovernanceState.PENDING
    reviewer: Optional[str] = None
    decided_at: Optional[datetime] = None

    created_at: datetime

    # Note: these are produced by the diff/trajectory engine; never emit a flag whose
    #   evidence doesn't actually support the rationale (anti-hallucination gate).
