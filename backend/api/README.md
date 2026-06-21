# backend/api — the keystone

FastAPI that assembles **`CustomerCase`** = `{ customer, events, alert }` by wiring the three layers:

```
customer ← data/customers/*.json
events   ← backend.ingest.runner.collect() (live or fixtures)
alert    ← backend.drift.engine.replay()
```

## Endpoints
| Route | Returns |
|---|---|
| `GET /health` | liveness |
| `GET /cases` | summary list (customer + final tier/score + headline flag + cost) for the dashboard picker |
| `GET /cases/{key}` | full `CustomerCase` (+ `alerts`, `timeline`, `cost`). `key` = customer_id or filename stem |
| `GET /cases/{key}?refresh=true` | rebuild (re-run ingestion + engine) |

## Run
```bash
pip install -r requirements.txt
uvicorn backend.api.main:app --reload --port 8000
# OFFLINE_DEMO=true (default) → fixtures + MockLLM, no network/keys. Fast + deterministic.
# OFFLINE_DEMO=false + Apertus key → real sources + Apertus cascade.
```

## Frontend wiring
The dashboard's data facade already supports it: set `NEXT_PUBLIC_DATA_MODE=live` and point the
live client at `http://localhost:8000`. The `CustomerCase` shape matches `frontend/lib/types`.
The API returns extra fields (`alerts`, `timeline`, `cost`) — safe to ignore or use for richer views.

## Design notes
- **ID bridge:** loads a customer by `customer_id` OR filename stem (the engine keyed Coinbase as
  "coinbase", the runner as "coinbase-global" — both resolve here).
- **No-drift case:** if the engine flags nothing, returns an honest `flag:"No material drift"`
  alert (keeps the non-null UI contract; truthfully says "screened, nothing contradicted").
- **Cost cache:** built cases are memoised in-process; `?refresh=true` rebuilds.

## ⚠️ Known behaviours
1. **`escalation_rate` is context-sensitive** — ~0.036 from `run_demo` (no `.env`) vs 1.0 when
   `.env` is loaded (via this API). Cost-meter accounting should be stabilised so the
   cost-efficiency numbers are reproducible.
