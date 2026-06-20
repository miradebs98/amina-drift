"""Assemble a `CustomerCase` ({customer, events, alert}) — the exact shape the frontend consumes.

Pure / FastAPI-free so it can be unit-tested and reused by Mira's cascade/govern. It drives
Miguel's engine: load ClientState -> replay the timeline (per-tick risk + cascade cost) -> build the
one aggregate DriftAlert (onboarding baseline -> now).

Frontend contract (frontend/lib/api/fixtures.ts):
    GET /api/customers            -> CustomerCase[]   (drift-ranked: Meridian first)
    GET /api/customers/{id}       -> CustomerCase
    CustomerCase = { customer, events, alert }   (+ extra `timeline` & `cost` for the real curve/meter)

ID note: the frontend + customer JSON use the public id (`coinbase-global`), but the engine's
fixture loader keys on the file stem (`coinbase`). We map public id -> loader key here and normalise
the engine's output back to the public id so everything downstream is consistent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env so the engine sees DRIFT_LLM_* (Apertus) without an explicit `export` (best-effort).
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass

from backend.drift.client_state import load_client_state_from_fixtures
from backend.drift.engine import build_alert, replay
from backend.drift.llm import get_llm
from backend.drift.score import assess, tier_for

# public id (frontend / customer.json) -> engine fixture-loader key (data/customers/<key>.json)
PUBLIC_TO_LOADER = {
    "meridian-sands": "meridian-sands",
    "coinbase-global": "coinbase",
}
# display order: highest-drift first (matches the frontend fixtures' ORDER)
CASE_ORDER = ["meridian-sands", "coinbase-global"]

# Engine calls can be slow on live Apertus; a case is deterministic per process, so cache it.
_CACHE: dict[str, dict] = {}


def _strip_underscore(obj):
    """Drop the human-annotation keys (_comment/_note/_role_in_demo) the JSON files carry."""
    if isinstance(obj, dict):
        return {k: _strip_underscore(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_underscore(v) for v in obj]
    return obj


def _load_customer_json(loader_key: str) -> dict:
    with open(REPO_ROOT / "data" / "customers" / f"{loader_key}.json") as f:
        return _strip_underscore(json.load(f))


def _jsonable_timeline(timeline: list[dict]) -> list[dict]:
    out = []
    for t in timeline:
        t = dict(t)
        as_of = t.get("as_of")
        if hasattr(as_of, "isoformat"):
            t["as_of"] = as_of.isoformat()
        out.append(t)
    return out


def build_case(public_id: str, *, use_cache: bool = True) -> dict:
    """Return one CustomerCase dict for the frontend. Raises KeyError on unknown id."""
    if use_cache and public_id in _CACHE:
        return _CACHE[public_id]

    loader_key = PUBLIC_TO_LOADER[public_id]
    state = load_client_state_from_fixtures(loader_key)
    state.customer_id = public_id                       # normalise to the id the frontend uses

    llm = get_llm()
    result = replay(state, llm)                          # per-tick risk trajectory + cascade cost
    timeline = result["timeline"]
    final_tick = timeline[-1]

    # ONE aggregate alert spanning onboarding baseline -> now (matches the frontend's single alert).
    baseline = state.baseline_risk_score
    final_assessment = assess(state, final_tick["as_of"], llm)
    alert = build_alert(state, final_assessment, baseline, tier_for(baseline), llm,
                        final_tick.get("surprise"))
    alert.customer_id = public_id

    case = {
        "customer": _load_customer_json(loader_key),
        "events": [e.model_dump(mode="json") for e in state.evidence],
        "alert": alert.model_dump(mode="json"),
        # --- extras beyond the strict {customer,events,alert} contract (frontend ignores unknowns):
        # the real per-tick risk curve (for DriftScoreOverTime) and the staged-cascade cost meter.
        "timeline": _jsonable_timeline(timeline),
        "cost": {**result["cost"], "llm": type(llm).__name__},
    }

    # Safety net the frontend cares about: every cited evidence id must resolve to an event.
    ev_ids = {e["id"] for e in case["events"]}
    case["alert"]["evidence_ids"] = [eid for eid in case["alert"]["evidence_ids"] if eid in ev_ids]

    if use_cache:
        _CACHE[public_id] = case
    return case


def list_cases() -> list[dict]:
    return [build_case(cid) for cid in CASE_ORDER]


def cost_summary() -> dict:
    """Aggregate the staged-cascade cost across all cases (Cost Efficiency story)."""
    cases = list_cases()
    cheap = sum(c["cost"]["cheap_calls"] for c in cases)
    heavy = sum(c["cost"]["heavy_calls"] for c in cases)
    tokens = sum(c["cost"]["total_tokens"] for c in cases)
    total_calls = cheap + heavy
    return {
        "cases": len(cases),
        "cheap_calls": cheap,
        "heavy_calls": heavy,
        "total_tokens": tokens,
        "escalation_rate": round(heavy / total_calls, 3) if total_calls else 0.0,
        "llm": cases[0]["cost"]["llm"] if cases else None,
        "_note": "Cost-per-1,000-analyses (USD) is Mira's cascade lane; this is the raw call/token split.",
    }
