# STATUS — what's built / available / missing

> Canonical build state. Last updated **2026-06-20**. Keep this honest — partners read the code.
> Detail lives in: `README.md`, `docs/HOW_IT_WORKS.md`, `backend/ingest/SOURCES.md`,
> `backend/api/README.md`, and each lane's `CLAUDE.md`.

## At a glance
| Component | Status | Owner | Notes |
|---|---|---|---|
| Schemas / contracts | ✅ done | all | assertion · evidence · alert · audit · **dimensions** (`shared/schemas/`) |
| Layer-1 connectors | ✅ **9 live** | Mira | see table below |
| Entity resolution | 🟡 at-emission | Mira | resolved when querying by the customer's ids; no separate fuzzy `resolve/` yet |
| Drift engine | ✅ done, **live Apertus** | Miguel | event + slow-structural drift, 0–100 score, cost meter |
| Cost cascade + meter | 🟡 works, not surfaced | Mira/Miguel | Stage-1 relevance gate + engine `CostMeter` (~2% escalation); no UI widget yet |
| Governance (audit/HITL/RBAC) | ✅ done | Mira | hash-chained tamper-evident log + four-eyes |
| API (keystone) | ✅ done | Mira | serves `CustomerCase` + decisions + audit + network |
| Network graph (Network dim) | ✅ done | Mira | connected entities + sanctions/PEP propagation |
| 4-dimension tagging | ✅ done | all | every signal tagged; `dimensions_drifted` per case |
| Dashboard | 🟡 substantial, not wired | Giacomo | Next.js app, twin-diff, HITL UI built; **live-wire to API + 4-lane + network viz pending** |
| Demo entities | ✅ 3 | Giacomo | Coinbase (real, listed) · Meridian (fictional drift-hero) · **HashKey** (real startup) |
| **Combination/breadth threshold** | 🔜 **the GOLD gap** | Miguel | fire on ≥3 dimensions co-moving (HashKey proves the need) |
| **Apertus "connect-the-dots" narrative** | 🔜 | Miguel | the 18-month story paragraph on the alert |
| Pitch deck | ⬜ | Giacomo | `pitch/` empty |

## Available now (you can use these)
**Run the API:** `uvicorn backend.api.main:app --reload --port 8000` (offline by default).
Endpoints:
- `GET /cases` · `GET /cases/{id}` → `CustomerCase {customer, events, alert, alerts, timeline, cost, dimensions_drifted}`
- `GET /cases/{id}/network` → connected-entity graph + network risk
- `POST /alerts/{id}/decision` (RBAC) · `GET /audit` · `GET /audit/verify` · `GET /roles`

**Live connectors** (`backend/ingest/`, all emit `EvidenceEvent`):
| # | Connector | Source | Key? | Dimension(s) |
|---|---|---|---|---|
| 1 | `sec_earnings` (L1+L2) | SEC EDGAR filings + 10-K passages | none/UA | Contextual/Network |
| 2 | `wayback` | Wayback website change over time | none | Contextual |
| 3 | `news_rss` | Google News | none | Network |
| 4 | `gdelt` | GDELT news + tone | none | Network |
| 5 | `event_registry` | Event Registry news + **sentiment** | key | Network |
| 6 | `gleif` | GLEIF LEI + ownership | none | Identity |
| 7 | `sanctions` | OpenSanctions/yente (entity + UBOs) | free key | Identity/Network |
| 8 | `funding` | funding rounds + lead investor (startup) | none | Contextual→Identity |
| 9 | `cert_transparency` | **crt.sh** new-infra subdomains (digital exhaust) | none | Contextual |
| — | `fixtures` | offline replay (frozen real/authored events) | none | — |
| stub | `registry` | ZEFIX/Companies House/ADGM | — | Identity |

**LLM / embeddings:** Apertus on CSCS (`swiss-ai/Apertus-8B/70B-Instruct-2509`) for verdict +
narrative; `swissai` embeddings (free) for Stage-1; lexical fallback. **Zero OpenAI / zero cost.**

## Missing / in progress
- **Combination/breadth-threshold engine** (Miguel) — the gold differentiator; HashKey (55 events,
  3 dimensions, score 55→63 but no alert) is the proof case.
- **Apertus connect-the-dots narrative** on the headline alert (Miguel).
- **Dashboard wiring** (Giacomo): swap mock for `NEXT_PUBLIC_DATA_MODE=live`; build the 4-lane
  convergence view; render `/network`; replace the faked `dispose()` with `POST /decision` + `/audit`.
- **Cost meter UI widget** (numbers already in `cost`).
- **Registry connector** (ZEFIX/Companies House PSC) — stub.
- **Pitch deck** (`pitch/`).

## Honest caveats
- Live sources (crt.sh, Wayback, GDELT) rate-limit; the **offline fixtures** are the deterministic
  demo path. crt.sh is live-proven but not yet in HashKey's frozen fixture (service was 503-ing).
- Real-company drift (Coinbase, HashKey) is framed **neutrally** ("material change → re-KYC"); the
  dramatic LOW→HIGH flip is the **fictional** Meridian only.
