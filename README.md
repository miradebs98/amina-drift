# amina-drift

**Dynamic Risk Profiling System — KYC Drift Detection.**
SwissHacks 2026 · Challenge 4 (AMINA Bank).

We catch **KYC drift**: the slow divergence between what a bank believes about a customer at
onboarding and what's actually true now. We model the KYC profile as a set of **dated, testable
assertions**, then continuously re-validate them against **real-time public intelligence** —
firing the moment a *specific* on-file assertion is contradicted, with cited evidence, cheaply,
and with a human in the loop.

> Everyone else makes onboarding faster or rescreens more often. We catch the moment a specific
> KYC assertion goes stale — with the evidence, cheaply, routed to the right team.

## Architecture (two layers + cost-aware cascade + governance)
```
Layer 1 (public)  ingest/ → resolve/ ─┐
                                       ├─ drift/ → cascade/ → govern/ → frontend/
Layer 2 (internal) data/customers/  ──┘   (engine) (cost)   (HITL+audit) (dashboard)
```
Full context + ownership: **[CLAUDE.md](CLAUDE.md)**. Each lane has its own `CLAUDE.md`.

Architecture, the data contracts, and procedures to add a new source or signal:
**[docs/MECHANISM_AND_EXTENSION.md](docs/MECHANISM_AND_EXTENSION.md)**.

## Team & ownership
| Lane | Owner | Directories |
|---|---|---|
| Domain & Product (UI, KYC profile, deck) | **Giacomo** | `frontend/` `data/customers/` `pitch/` |
| Data & Integration (connectors, cascade, governance, API) | **Mira** | `backend/{ingest,resolve,cascade,govern,api}/` `data/{snapshots,fixtures}/` |
| Drift Modelling (the engine) | **Miguel** | `backend/drift/` |
| Shared contracts (ping before changing) | **all three** | `shared/schemas/` |

## Repo layout
```
shared/schemas/   the 3 data contracts: Assertion · EvidenceEvent/Snapshot · DriftAlert · AuditEntry
backend/ingest/   Layer-1 connectors (GDELT, News RSS, GLEIF, ZEFIX, OpenSanctions/yente, Wayback)
backend/resolve/  entity resolution (event → customer, confidence-gated)
backend/drift/    KYC-drift engine: assertion-diff + slow structural drift + scoring   [Miguel]
backend/cascade/  cost-aware staged pipeline + token/$ + escalation-rate instrumentation
backend/govern/   HITL approval, immutable audit log, RBAC, public/internal data separation
backend/api/      FastAPI
frontend/         analyst dashboard
data/customers/   authored Layer-2 KYC profiles (assertions)
data/snapshots/   time-compressed snapshot timeline for the demo entity
data/fixtures/    cached API payloads → the demo runs offline
eval/scenarios/   the 10 brief use cases as runnable tests
pitch/            .pptx deck + 3-min script
```

## Status — what's real vs. mocked
> **Keep this honest.** Partners read the code. Full state in **[STATUS.md](STATUS.md)**.

| Component | Status |
|---|---|
| Schemas / contracts (incl. 4-dimension tagging) | ✅ done |
| Layer-1 connectors | ✅ **9 live** (SEC L1+L2, Wayback, Google News, GDELT, Event Registry, GLEIF, OpenSanctions, Funding, crt.sh) |
| Entity resolution | 🟡 at-emission (no separate fuzzy step) |
| Drift engine | ✅ done — **live Apertus** (Swiss-sovereign, ~2% escalation) |
| Cost cascade + meter | 🟡 works (Stage-1 gate + CostMeter); no UI widget |
| Governance (audit/HITL/RBAC) | ✅ done — hash-chained tamper-evident log + four-eyes |
| API (keystone) + Network graph | ✅ done |
| Dashboard | 🟡 built (Next.js, twin-diff, HITL UI); live-wire pending |
| Demo entities | ✅ Coinbase · Meridian · HashKey (real startup) |
| 🥇 Combination/breadth threshold + narrative | 🔜 the gold gap (Miguel) |

## Setup
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # TODO: add as deps land
cp .env.example .env                      # add API keys (git-ignored)
# uvicorn backend.api.main:app --reload   # TODO once api/ exists
```

## Judging weights (build to these)
AI Intelligence 25% · **Cost Efficiency 20%** · UX & Explainability 20% · Compliance & Safety 20%
· Engineering 15%.
