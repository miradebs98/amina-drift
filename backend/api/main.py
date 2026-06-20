"""amina-drift API — the keystone that serves CustomerCase to the frontend.

  GET /health              → liveness
  GET /cases               → [summary]  (customer + headline tier/score/flag + cost)
  GET /cases/{key}         → CustomerCase { customer, events, alert, alerts, timeline, cost }
  GET /cases/{key}?refresh=true   → rebuild (re-run ingestion + engine)

Honours OFFLINE_DEMO: default replays fixtures + MockLLM (fast, no network/keys) so the demo and
Giacomo's `live` mode work out of the box. Set OFFLINE_DEMO=false (+ Apertus key) for real sources.

  uvicorn backend.api.main:app --reload --port 8000
Frontend: set NEXT_PUBLIC_DATA_MODE=live and point the client at http://localhost:8000
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.api.cases import build_case, list_cases

app = FastAPI(title="amina-drift API", version="0.1.0")

# Allow the Next.js dev server (and the deployed demo) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # tighten to the frontend origin for a real deployment
    allow_methods=["*"], allow_headers=["*"],
)

# Cases are expensive to build (ingestion + engine) → cache in memory; ?refresh=true rebuilds.
_CASE_CACHE: dict[str, dict] = {}


@app.get("/health")
def health():
    return {"ok": True, "service": "amina-drift"}


@app.get("/cases")
def cases():
    """Summary list for the dashboard's customer picker."""
    return list_cases()


@app.get("/cases/{customer_key}")
def case(customer_key: str, refresh: bool = Query(False)):
    """Full CustomerCase. `customer_key` = customer_id or filename stem."""
    if refresh:
        _CASE_CACHE.pop(customer_key, None)
    if customer_key not in _CASE_CACHE:
        built = build_case(customer_key)
        if built is None:
            raise HTTPException(status_code=404, detail=f"unknown customer '{customer_key}'")
        _CASE_CACHE[customer_key] = built
    return _CASE_CACHE[customer_key]
