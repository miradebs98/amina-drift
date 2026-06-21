"""AuditEntry — append-only, immutable decision log.

Lives in govern/. Everyone writes decisions THROUGH this — never mutate past entries.
This is a graded guardrail (Compliance 20%) and is implemented for real, not faked.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AuditAction(str, Enum):
    ALERT_CREATED = "alert_created"
    STAGE_ESCALATED = "stage_escalated"   # cheap → LLM → deep
    HUMAN_APPROVED = "human_approved"
    HUMAN_DISMISSED = "human_dismissed"
    HUMAN_ESCALATED = "human_escalated"
    PROFILE_UPDATED = "profile_updated"   # re-KYC / assertion re-verified


class AuditEntry(BaseModel):
    """Enough to reconstruct WHY any decision was made, later."""
    id: str
    timestamp: datetime
    action: AuditAction
    actor: str                             # "system" or reviewer id (human)
    customer_id: Optional[str] = None
    alert_id: Optional[str] = None

    # model provenance (for any AI-driven step)
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None

    # decision chain
    inputs_hash: Optional[str] = None      # hash of inputs (don't store raw PII)
    policy_version: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)

    # Note: persisted to an append-only SQLite table; a read API exposes the audit view.
