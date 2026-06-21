"""amina-drift · drift engine.

Reads a per-customer `ClientState` (assembled from the shared contracts) and produces
`DriftAlert`s. Pure-stdlib + `shared.schemas` — no heavy deps, runs offline.

Public entry points:
    from backend.drift.engine import assess_drift, replay
    from backend.drift.client_state import load_client_state_from_fixtures
"""
