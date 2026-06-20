"""backend.api — the FastAPI wire between the drift engine and Giacomo's dashboard.

Lane note: `backend/api/` is Mira's lane. This is a STARTER that wires Miguel's engine
(`backend/drift/`) to the exact `CustomerCase` shape the frontend already consumes, so Giacomo can
flip `NEXT_PUBLIC_DATA_MODE=live`. Mira owns extending it (govern/HITL approval endpoints +
AuditEntry, live ingest, cost-per-1000). See `cases.py` for the pure (FastAPI-free) assembly.
"""
