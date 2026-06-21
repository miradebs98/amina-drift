# amina-drift — a KYC-drift early-warning system

**SwissHacks 2026 · Challenge 4 · AMINA Bank**

> *"Banks are looking in the rearview mirror. The moment perception and reality separate, risk begins."*

A KYC profile is not a document — it is a set of **dated, testable assertions** (UBO = X · business =
SaaS · domicile = CH). amina-drift continuously re-validates each assertion against a real-time stream
of public intelligence and flags the moment one is **contradicted** — with cited evidence, cheaply,
routed to the right team with a human in the loop.

**The wedge:** everyone else makes onboarding faster or rescreens more often. We catch the moment a
*specific on-file KYC assumption* is invalidated by public events — including the slow, structural
drift that no single signal crosses.

---

## 1. What it does (the two halves of the brief's mandate)

> *"The system should not only detect immediate fraud signals, but also monitor slow, structural
> changes in customers or counterparties that invalidate previous KYC assumptions."*

Two complementary detectors run over the same belief set:

- **Event-drift (immediate).** A discrete public event contradicts a specific assertion — a sanctions
  hit, a new beneficial owner, a licence action, an adverse-media investigation. High-precision, cheap,
  every claim cited. This drives the live demo roster.
- **Slow-structural drift (the hard part).** No single event contradicts anything — the customer's
  public *profile* migrates over months (SaaS → crypto, onshore → offshore). The engine embeds dated
  profile snapshots onto interpretable risk concept-axes and alarms when the cumulative trajectory
  crosses a band — *before* any hard contradiction. (See [MECHANISM_AND_EXTENSION.md](MECHANISM_AND_EXTENSION.md) §0.)

---

## 2. Architecture & data pipeline

```
 Layer 2 (internal, simulated)     Layer 1 (public, real-time)        Engine (backend/drift/)
 data/customers/*.json             backend/ingest/* (10 connectors)   ┌─────────────────────────────────┐
 ┌────────────────────┐            ┌───────────────────┐              │ ① GATE → ② VERDICT → ③ SCORE →   │
 │ KYC profile =      │            │ each connector →  │              │   relevance  cheap LLM   0–100   │
 │ Assertion[]        │───────────▶│ EvidenceEvent     │─────────────▶│   (no LLM)  (Apertus-8B) level   │
 │ (testable beliefs) │  resolve   │ (uniform schema)  │   feed       │              ↓                   │
 └────────────────────┘  to client └───────────────────┘              │            ④ ALERT (drift-based) │
                                                                       └─────────────────────────────────┘
                                                                                       │
                                                  ⑤ GOVERN (HITL approve/escalate → hash-chained audit)
                                                                                       │
                                                  ⑥ API (FastAPI) ──▶ Next.js analyst dashboard
```

- **Layer 1 (public, real):** 10 connectors emit a uniform `EvidenceEvent` stream.
- **Layer 2 (internal, simulated):** the bank's onboarding KYC profile, authored as `Assertion[]`.
- **Cost cascade:** a cheap Stage-1 gate filters most pairs (no LLM); only candidates reach the cheap
  LLM; only escalations reach the frontier model.
- **Governance:** every alert is `PENDING` until a human acts; decisions write to an immutable,
  hash-chained audit log.

Full mechanism + extension guide: **[MECHANISM_AND_EXTENSION.md](MECHANISM_AND_EXTENSION.md)**.

---

## 3. Public data sources (Layer 1) — and how they're accessed

Every source is a `Connector` (`backend/ingest/`) emitting the same `EvidenceEvent`. Roster &
status: **[backend/ingest/SOURCES.md](backend/ingest/SOURCES.md)**.

| Connector | Source | Key | Emits |
|---|---|---|---|
| `sec_earnings.py` | SEC EDGAR filings + 10-K text → cited passages | none (UA string) | filings, ownership, cited quotes |
| `wayback.py` | Wayback Machine CDX (homepage change over time) | none | website_change |
| `gleif.py` | GLEIF LEI + ownership graph | none | registry/ownership |
| `gdelt.py` | GDELT adverse-media tone | none | news |
| `news_rss.py` | Google News RSS | none | news |
| `event_registry.py` | Event Registry news + sentiment | partner key | news (+ sentiment) |
| `sanctions.py` | OpenSanctions / yente (entity + UBO/PEP screening) | free key or self-host | sanctions_hit, pep_hit |
| `funding.py` | Funding rounds + lead investor → UBO re-screen | none | funding |
| `cert_transparency.py` | crt.sh new-infra subdomains (digital exhaust) | none | website_change |
| `stubs.py` | ZEFIX / Companies House / ADGM | varies | (stub) |

Each connector caches its pulls to `data/fixtures/` so the demo runs fully offline. Add a source =
subclass `Connector`, add one line to `runner.LIVE_CONNECTORS` (see SOURCES.md / doc §4.1).

---

## 4. Baseline KYC assumptions (Layer 2)

The bank's onboarding profile is a set of dated, sourced, testable beliefs in
`data/customers/<id>.json`. Example — **Coinbase** (onboards *elevated*, score 60 / MEDIUM):

| Predicate | On-file belief (the assumption the engine re-tests) |
|---|---|
| `business_model` | Retail & institutional digital-asset exchange + custody |
| `regulatory_status` | US-listed (NASDAQ: COIN); registered MSB; state money-transmitter licences |
| `operating_geographies` | US-origin, expanding internationally |
| `ubo` / `ownership_structure` | Public free float; no >25% UBO |
| `sanctions_status` / `pep_status` | No designation / no PEP at onboarding |

The engine never re-validates immutable identity (incorporation number, LEI) — only the **monitorable
beliefs**. Contract: `shared/schemas/assertion.py`.

---

## 5. Demo roster & example risk signals (with reasoning)

Run offline by default; the numbers below are the engine's real output.

| Client | Onboard → now | What the engine detected (event-drift) |
|---|---|---|
| **Coinbase** | 60 → **67** | **+19** on the SEC suit (06 Jun 2023, *adverse-media + regulatory contradicted*), peak 81 on Base launch, then **−14** when the SEC **dismissed** the case (27 Feb 2025, *litigation resolved*). Rise-then-fall — the model de-risks when reality improves. |
| **HashKey** | 55 → **82** | Gradual re-tier over 18 months via a chain of real public events (funding rounds, IPO, homepage changes flagged for review, a name-only screen match correctly weighted as a *potential*). The slow-drift hero, via event accumulation. |
| **Binance** | 58 → **84** | FCA ban (+22), then CFTC/SEC/DOJ episodes; saturates near the cap. Settlement included sanctions-program failures but **no designation**, so it correctly stays below the 88 sanctions-reserved ceiling. |
| **Geberit** | 22 → **22** | Ordinary corporate news (results, buyback, internal CFO promotion, ESG upgrade) → **no drift**. The false-positive control: noise does not move risk. |

Each detected drift maps deterministically to a **flag + recommended action** (the brief's
signal→action table; `engine.py::_FLAGS`), e.g. *Adverse Media → Trigger EDD; consider SAR*.

> The four above are **real companies** and demonstrate **event-drift**. The **slow-structural**
> detector (§1) is exercised separately by **Meridian Sands** — a *fully fictional* client with
> reconstructed profile snapshots — so it is intentionally **not in the live roster above**; see §9.

---

## 6. AI model selection & cost efficiency

- **Sovereign by choice:** the LLM cascade runs **Apertus** (`swiss-ai/Apertus-8B / 70B-Instruct`,
  Swiss-built, open, hosted on CSCS) — data-sovereign and well-suited to a Swiss bank. The interface is
  OpenAI-compatible, so any model can be swapped in via `.env` (`get_llm()`); a deterministic `MockLLM`
  is the offline fallback.
- **General-purpose LLMs are disqualified as *final* compliance deciders** (hallucination), so every
  generative output is **grounded and cited**, with a human in the loop — never an automated decision.
- **Cost cascade** (`cost` block from `replay()`, measured on Coinbase / Apertus):

  ```
  63 (belief × event) pairs
    → Stage-1 gate filtered 44%         no LLM, $0
    → Stage-2 cheap model   35 calls    35,284 tokens
    → Stage-3 heavy model    2 calls     2,151 tokens   (5.4% escalation)
  ```
  ≈ **88% cheaper** than routing every pair through the frontier model. The `cost` block reports
  `cost_per_1000_analyses` / `cost_per_1000_alerts` live. Cost model: doc §8.

---

## 7. Security, governance & compliance

- **Data separation:** Layer 1 (public) and Layer 2 (internal KYC) are distinct stores; the public
  pipeline never reads internal beliefs except to test them.
- **Human-in-the-loop (real):** approve / override / escalate → Re-KYC posts to `backend/govern/`;
  **four-eyes RBAC** (closing a HIGH re-tier requires MLRO sign-off).
- **Immutable audit:** every decision writes a hash-chained, tamper-evident `AuditEntry`
  (`GET /audit/verify` → chain-intact badge).
- **No claim without a source:** every alert and chat answer carries citations to the real evidence
  events; the analyst chat is **deterministic and grounded by design** (doc §4.7).

---

## 8. Real-time operation

The demo replays a frozen timeline; production runs the identical pipeline on the wall clock.
`backend/monitor.py` is a scheduled sweep — an external scheduler (cron / cloud / k8s CronJob) ticks
it, and each sweep re-checks only the clients **due** under `config.MONITORING` (default 24h; per band:
HIGH 6h · MEDIUM 24h · LOW weekly). **AMINA tunes the cadence at runtime** (env or a `/monitoring`
endpoint) with no redeploy — also the main cost lever. Idempotent (cache + event-id dedup + verdict
memoisation). Run: `python -m backend.monitor` (one sweep) or `--loop`.

---

## 9. What's real vs. mocked (honesty)

| Real & live (with keys) | Authored / simulated (by design) | Offline / demo-local |
|---|---|---|
| 10 Layer-1 connectors (SEC, Wayback, GLEIF, GDELT, Event Registry, OpenSanctions, Google News, crt.sh, funding) | **Layer-2 KYC profiles** (`data/customers/*.json`) — the brief mandates a *simulated* internal baseline | `OFFLINE_DEMO=true` (default) replays cached fixtures so the demo runs with no network/keys |
| **Apertus** LLM verdicts + narrative; arctic-embed embeddings | **Meridian Sands** — *fully fictional*; used **only** as the reconstructed-snapshot scenario that exercises the slow-structural trajectory detector. **Not a live client.** | Alert-page CTAs (open EDD / file SAR) and the monitor's notify hook **log locally** — no live downstream system |
| Hash-chained audit log + four-eyes RBAC (real `govern/` endpoints) | Slow-structural trajectory runs on reconstructed snapshots (only Meridian has them) | Analyst chat answers from grounded retrieval, not a live LLM at query time (deterministic by design) |

The HITL approval → audit flow is **never** mocked.

---

## 10. Run it

**Backend (offline demo — no keys needed):**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # OFFLINE_DEMO=true by default; live mode needs the Apertus key
uvicorn backend.api.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend && npm install
npm run dev                          # fixtures mode (default) — http://localhost:3000
NEXT_PUBLIC_DATA_MODE=live npm run dev   # hit the FastAPI backend instead
```

**Live data** (real connectors): set `OFFLINE_DEMO=false` + the keys in `.env`, then
`python -m backend.ingest.runner coinbase-global --live`.

---

## 11. Repository layout

```
backend/
  ingest/      Layer-1 connectors (one EvidenceEvent schema) + runner   → SOURCES.md
  drift/       the engine: gate · verdict · score · trajectory · alerts · monitor
  govern/      HITL + hash-chained audit + RBAC
  api/         FastAPI (serves CustomerCase to the dashboard)           → api/README.md
  network/     connected-entity graph (Network-Risk dimension)
  grain_lite/  SEC filing/10-K ingestion + cited-passage retrieval
shared/schemas/  the frozen contracts: Assertion · EvidenceEvent · DriftAlert · AuditEntry · dimensions
data/customers/  Layer-2 KYC profiles (authored)
data/fixtures/   cached public evidence (offline demo)
frontend/        Next.js analyst dashboard (app · components · lib · mock)
eval/            gate-recall, verdict-precision, and scenario tests
MECHANISM_AND_EXTENSION.md   architecture deep-dive + extension guide (root)
```

## 12. Tests
```bash
pip install pytest
PYTHONPATH=. pytest backend/drift/test_calibration.py backend/drift/test_alert_confidence.py backend/govern/test_data_policy.py -q
```
Gate-recall and verdict-precision harnesses live in `eval/`.
