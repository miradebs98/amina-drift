"""Shared data contracts for amina-drift.

⚠️ CHANGING ANYTHING HERE CAN BREAK ALL THREE LANES.
Ping the other two founders before editing. These shapes are frozen Friday night.

- Assertion / ExpectedEnvelope  → what the bank believes (Giacomo authors, Miguel/Mira consume)
- EvidenceEvent / Snapshot      → what a connector emits (Mira produces, Miguel consumes)
- DriftAlert                    → a detected drift (Miguel produces, Giacomo's UI renders)
- AuditEntry                    → append-only decision log (Mira owns, everyone writes through it)
"""

from .assertion import Assertion, ExpectedEnvelope, AssertionStatus, Predicate
from .evidence import EvidenceEvent, Snapshot, EvidenceType
from .alert import DriftAlert, DriftType, Severity, GovernanceState
from .audit import AuditEntry, AuditAction

__all__ = [
    "Assertion", "ExpectedEnvelope", "AssertionStatus", "Predicate",
    "EvidenceEvent", "Snapshot", "EvidenceType",
    "DriftAlert", "DriftType", "Severity", "GovernanceState",
    "AuditEntry", "AuditAction",
]
