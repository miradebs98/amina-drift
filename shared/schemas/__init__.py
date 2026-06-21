"""Shared data contracts for amina-drift.

⚠️ CHANGING ANYTHING HERE CAN BREAK EVERY LAYER. These shapes are the cross-layer contract.

- Assertion / ExpectedEnvelope  → what the bank believes
- EvidenceEvent / Snapshot      → what a connector emits
- DriftAlert                    → a detected drift (the engine produces, the UI renders)
- AuditEntry                    → append-only decision log (everyone writes through it)
"""

from .assertion import Assertion, ExpectedEnvelope, AssertionStatus, Predicate
from .evidence import EvidenceEvent, Snapshot, EvidenceType
from .alert import DriftAlert, DriftType, Severity, GovernanceState
from .audit import AuditEntry, AuditAction
from .dimensions import Dimension, dimension_for_predicate, dimension_for_evidence

__all__ = [
    "Assertion", "ExpectedEnvelope", "AssertionStatus", "Predicate",
    "EvidenceEvent", "Snapshot", "EvidenceType",
    "DriftAlert", "DriftType", "Severity", "GovernanceState",
    "AuditEntry", "AuditAction",
    "Dimension", "dimension_for_predicate", "dimension_for_evidence",
]
