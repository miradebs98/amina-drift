# CLAUDE.md — `backend/` (except `drift/`) · OWNER: Mira (Data & Integration)

> Read the root `/CLAUDE.md` first. This is **Mira's lane**: `ingest/`, `resolve/`, `cascade/`,
> `govern/`, `api/`. **`backend/drift/` is Miguel's** — don't edit it; consume/expose it via the API.

## Your mission
You're the integration spine that lets Giacomo and Miguel move fast, and you own the two
under-contested axes: **Cost Efficiency (20%)** and **Engineering (15%)**, plus the **Compliance
(20%)** plumbing (audit, RBAC, data separation).

## What you build
1. **`ingest/` — Layer 1 connectors** (emit `EvidenceEvent` / `Snapshot`): GDELT, Google News
   RSS, GLEIF (LEI/ownership), **ZEFIX** (Swiss registry), **yente/OpenSanctions** (sanctions+PEP),
   Wayback CDX (website diff). Cache every response into `data/fixtures/` → **offline-safe demo.**
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
