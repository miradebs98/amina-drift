"""FastAPI app — exposes the drift engine to the frontend.

Run (from repo root):
    pip install -r requirements.txt
    export $(grep -v '^#' .env | xargs)          # optional: real Apertus (else offline MockLLM)
    uvicorn backend.api.main:app --reload --port 8000

Then point the dashboard at it:  NEXT_PUBLIC_DATA_MODE=live  NEXT_PUBLIC_API_URL=http://localhost:8000

Endpoints:
    GET /api/health                  -> liveness + which LLM is active
    GET /api/customers               -> CustomerCase[]   (drift-ranked)
    GET /api/customers/{id}          -> CustomerCase
    GET /api/metrics/cost            -> aggregate staged-cascade cost

Lane note (Mira): HITL approval endpoints (POST /api/alerts/{id}/approve|dismiss|escalate) +
AuditEntry writes belong in govern/ — intentionally NOT stubbed here (we never fake the audit log).
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.api.cases import (
    CASE_ORDER,
    PUBLIC_TO_LOADER,
    build_case,
    cost_summary,
    list_cases,
)
from backend.drift.llm import get_llm

app = FastAPI(title="AMINA Drift API", version="0.1.0")

# Next.js dev server (3000) talks to this (8000) cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "llm": type(get_llm()).__name__, "cases": CASE_ORDER}


@app.get("/api/customers")
def get_customers():
    return list_cases()


@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: str):
    if customer_id not in PUBLIC_TO_LOADER:
        raise HTTPException(status_code=404, detail=f"unknown customer '{customer_id}'")
    return build_case(customer_id)


@app.get("/api/metrics/cost")
def get_cost():
    return cost_summary()
