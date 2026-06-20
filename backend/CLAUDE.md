# CLAUDE.md — `backend/` (except `drift/`) · OWNER: Mira (Data & Integration)

> Read the root `/CLAUDE.md` first. This is **Mira's lane**: `ingest/`, `resolve/`, `cascade/`,
> `govern/`, `api/`. **`backend/drift/` is Miguel's** — don't edit it; consume/expose it via the API.

## 🚩 FIRST TASK (before building connectors)
Help decide the schemas (see root `/CLAUDE.md` §0 + `shared/schemas/README.md`). **Your angle:**
- Open the base-case fixtures — `data/fixtures/coinbase-events.example.json` (real/citable) and
  `data/fixtures/meridian-events.example.json` (simulated) — can every connector (news, registry,
  sanctions, Wayback) realistically fill this `EvidenceEvent` shape? Is the `payload` flexible enough?
- Own the call on **Q2.1 (the big one)**: do we detect slow drift from *events only*, or do you
  also emit periodic `Snapshot`s? This decides how much you build — weigh it.
- **Q2.3**: confirm connectors stay dumb (just emit facts) and Miguel's engine does evidence→
  assertion matching. **Q2.5**: agree how unresolved events are marked.
Bring these to the kickoff. Don't build connectors until the `EvidenceEvent` shape is agreed.

## Your mission
You're the integration spine that lets Giacomo and Miguel move fast, and you own the two
under-contested axes: **Cost Efficiency (20%)** and **Engineering (15%)**, plus the **Compliance
(20%)** plumbing (audit, RBAC, data separation).

## ♻️ Reuse first: `grain_lite/` (our own GRAIN code — SEC + earnings ingestion)
Vendored slice of Sablier's GRAIN, **OpenAI as-is**. Read `backend/grain_lite/README.md`. It gives
you, ready-made:
- `grain_lite/sources/edgar.py` — **SEC filings** (10-K/10-Q/8-K/DEF-14A) fetch + clean text.
- `grain_lite/sources/transcript.py` — **earnings-call transcripts** (Alpha Vantage + sentiment).
- `grain_lite/chunker.py` + `grain_lite/embedder.py` (`cosine_similarity`) — chunk filings → embed
  → **your Stage-1 relevance filter** (passages vs an `Assertion`).
- `grain_lite/llm_client.py` + `cache.py` — the metered/cached LLM client + batch scoring (cost).
→ Best for **Coinbase** (real, listed): turn its filings + earnings calls into cited
`EvidenceEvent`s. **Wrap grain_lite output into our `EvidenceEvent` schema** (that's your bridge).
Meridian is fictional → stays fixture-based. Env needed: `OPENAI_API_KEY`, `ALPHAVANTAGE_API_KEY`
(free), `SEC_USER_AGENT`. The grounded SCORING on top is Miguel's (`backend/drift/CLAUDE.md`).

## 🥇 GOLD sources — connect the dots across 4 dimensions (current focus)
See root `/CLAUDE.md` §1.5. We're moving from "more alerts" to **catching drift no single signal
crosses** — startups are the wedge (mine public "digital exhaust"). Source roadmap by dimension
(`shared/schemas/dimensions.py`):
- **Contextual** — ✅ `funding.py` live (funding rounds + lead investor → UBO re-screen). Next:
  litigation (CourtListener, free API).
- **Identity & Ownership** — Companies House PSC + OpenCorporates (officer/UBO changes over time).
- **Network Risk** — ⭐ the **network graph** (entity → UBOs → directors → connected entities →
  sanctions) from GLEIF + registry + OpenSanctions. The missing dimension; nobody builds it.
- **Creative "digital exhaust"** (one, done well, is a stage moment): **crt.sh** (cert transparency
  → new infra/subdomains before any announcement) or **GitHub org activity** (a SaaS→crypto pivot
  shows in the code first).
Each is just one `Connector` subclass + one line in `runner.LIVE_CONNECTORS`. **Don't add 10 shallow
feeds** — funding + network graph + one digital-exhaust source is the gold set.

## What you build
1. **`ingest/` — Layer 1 connectors** (emit `EvidenceEvent`). ✅ **Framework + 5 live connectors
   already built & tested** — see `backend/ingest/SOURCES.md`. `Connector` base + `runner.py`
   merge stream; LIVE: SEC/earnings (grain_lite), Wayback, Google News, GLEIF, GDELT; FixtureConnector
   for Meridian + offline demo. **Add a source = subclass `Connector`, add one line to
   `runner.LIVE_CONNECTORS`.** Still STUBS to fill: `sanctions` (OpenSanctions/yente), `registry`
   (ZEFIX/ADGM), `funding`. Every live fetch caches to `data/fixtures/` → **offline-safe demo.**
2. **`resolve/` — entity resolution** (the silent demo-killer): match a public event to one of our
   customers with exact + fuzzy matching behind a **confidence gate**. Keep the customer set small.
3. **`cascade/` — the cost-aware staged pipeline**:
   - Stage 1: cheap gate (rules + embeddings/small model) — most signals die here for ~$0.
   - Stage 2: LLM verdict (calls Miguel's prompt) only on plausibly-relevant `(assertion, event)`.
   - Stage 3: deep analysis only on escalation.
   - **Instrument: tokens per workflow, cost per 1,000 alerts, light-vs-heavy split, escalation
     rate.** This feeds Giacomo's cost meter. Hard-cap/alert on escalation %.
4. **`govern/` — graded guardrails (never fake these)**: immutable `AuditEntry` append-only log
   (inputs hashed, model+version, decision chain, human action + reviewer + timestamp); RBAC;
   public/internal **data separation** (Layer 1 vs Layer 2 must be visibly partitioned); masking.
5. **`api/` — FastAPI**: expose alerts, customers, cost metrics, and the approval endpoints the
   frontend calls.
6. **`data/snapshots/`**: build the **time-compressed snapshot timeline** for the demo entity so
   slow drift replays in ~30s. **`data/fixtures/`**: cached API payloads.

## Contracts (own/produce — read `shared/schemas/`)
- You **produce** `EvidenceEvent` / `Snapshot` → consumed by Miguel's `drift/`.
- You **own** `AuditEntry` — everyone writes decisions through your `govern/` interface.
- You **expose** `DriftAlert` + cost metrics via the API for Giacomo's UI.

## Don't
- Don't put drift/scoring logic here — that's `drift/` (Miguel). You orchestrate and instrument it.
- Don't let live-API flakiness reach the stage — fixtures must let the full demo run with no network.
