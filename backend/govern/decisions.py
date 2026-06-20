"""HITL decision workflow — RBAC check → persist decision → write the immutable audit entry.

This replaces Giacomo's faked `dispose()` toast with a real, auditable disposition.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.govern import audit, rbac

DEFAULT_POLICY = "drift-model v2.3"   # matches the version shown in the UI


def apply_decision(*, alert_id: str, customer_id: str, severity: str, action: str,
                   reviewer: str, role: str = "analyst", note: str = "",
                   model_used: Optional[str] = None, policy_version: str = DEFAULT_POLICY) -> dict:
    """Disposition an alert. Raises PermissionError(reason) if RBAC denies it."""
    action = (action or "").lower()
    allowed, reason = rbac.can(role, action, severity)
    if not allowed:
        raise PermissionError(reason)

    state = rbac.ACTION_TO_STATE[action]
    audit_action = rbac.ACTION_TO_AUDIT[action]
    decided_at = datetime.now(timezone.utc).isoformat()
    # hash the decision context — provenance WITHOUT storing raw KYC/PII in the log
    inputs_hash = hashlib.sha256(f"{alert_id}|{customer_id}|{severity}".encode()).hexdigest()

    conn = audit._conn()
    try:
        conn.execute(
            """INSERT INTO decisions(alert_id,customer_id,governance_state,reviewer,role,note,decided_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(alert_id) DO UPDATE SET
                 governance_state=excluded.governance_state, reviewer=excluded.reviewer,
                 role=excluded.role, note=excluded.note, decided_at=excluded.decided_at""",
            (alert_id, customer_id, state, reviewer, role, note, decided_at))
        conn.commit()
    finally:
        conn.close()

    audit_id = audit.record(
        action=audit_action, actor=reviewer, role=role, customer_id=customer_id, alert_id=alert_id,
        model_name=model_used, model_version=policy_version, inputs_hash=inputs_hash,
        policy_version=policy_version, details={"note": note, "new_state": state, "ui_action": action},
    )
    return {"alert_id": alert_id, "governance_state": state, "reviewer": reviewer, "role": role,
            "decided_at": decided_at, "audit_id": audit_id}


def get_decision(alert_id: str) -> Optional[dict]:
    """Persisted disposition for an alert (used to overlay onto freshly-built alerts)."""
    conn = audit._conn()
    try:
        row = conn.execute("SELECT * FROM decisions WHERE alert_id=?", (alert_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None
