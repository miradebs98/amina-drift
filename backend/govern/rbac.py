"""Role-based access control — lightweight but real (the four-eyes principle).

Anyone can escalate up or mark a false positive. But CONFIRMING a HIGH-severity re-tier (which
moves a customer into EDD / potential SAR territory) requires MLRO sign-off — a second pair of
eyes. This is demonstrable on stage and is what a bank jury expects.
"""
from __future__ import annotations

ROLES = ["analyst", "mlro", "compliance", "admin"]
_RANK = {r: i for i, r in enumerate(ROLES)}

# UI action -> persisted governance_state (matches the UI buttons: Approve / Override / Escalate)
ACTION_TO_STATE = {
    "approve": "approved",
    "override": "dismissed",
    "dismiss": "dismissed",
    "escalate": "escalated",
}
# UI action -> AuditAction value (shared/schemas/audit.py)
ACTION_TO_AUDIT = {
    "approve": "human_approved",
    "override": "human_dismissed",
    "dismiss": "human_dismissed",
    "escalate": "human_escalated",
}


def can(role: str, action: str, severity: str) -> tuple[bool, str]:
    """Return (allowed, reason_if_denied)."""
    role = (role or "analyst").lower()
    action = (action or "").lower()
    if role not in _RANK:
        return False, f"unknown role '{role}'"
    if action not in ACTION_TO_STATE:
        return False, f"unknown action '{action}'"
    # Escalating up or overriding (false-positive) is open to any analyst+.
    if action in ("escalate", "override", "dismiss"):
        return True, ""
    # Approving (confirming the drift finding) — HIGH needs MLRO four-eyes.
    if action == "approve":
        if str(severity).lower() == "high" and _RANK[role] < _RANK["mlro"]:
            return False, "approving a HIGH-severity re-tier requires MLRO sign-off (four-eyes)"
        return True, ""
    return False, f"unhandled action '{action}'"
