# How it works — end-to-end walkthrough (Coinbase example)

A shared mental model of what's built and how the pieces connect. Uses Coinbase as the running
example. For status (real vs mocked) see `backend/ingest/SOURCES.md` and each lane's `CLAUDE.md`.

## The big picture (one line)
> A bank's **belief about a customer** (its KYC profile) is a set of testable assertions. Our
> **sources** fetch real public information about that customer and turn each finding into a
> uniform **evidence event**. The **engine** checks those events against the beliefs to detect drift.

```
data/customers/coinbase.json        backend/ingest/ (the sources)         backend/drift/ (engine)
┌──────────────────────────┐        ┌─────────────────────────────┐      ┌──────────────────┐
│  KYC PROFILE (beliefs)    │        │  SEC · Wayback · News ·      │      │  verdict + score │
│  CB1 business_model       │──────▶ │  GDELT · GLEIF              │────▶ │  → DriftAlert    │
│  CB5 regulatory_status    │  who   │  each → EvidenceEvent       │ feed │                  │
│  CB6 sanctions_status …   │ to look│  (cited, time-stamped)      │      │                  │
└──────────────────────────┘   up   └─────────────────────────────┘      └──────────────────┘
        Layer 2 (Giacomo)               Layer 1 — Mira's lane                engine (Miguel)
```

## Step 1 — The KYC profile (Layer 2, the "beliefs")
`data/customers/coinbase.json` holds three things:
- **`entity_profile`** — static identity (legal name, ticker `COIN`, CIK `0001679788`, domicile,
  website). NOT monitored — just who they are.
- **`assertions`** — the dated, testable beliefs the system watches, e.g. `CB1 business_model`,
  `CB5 regulatory_status`, `CB6 sanctions_status`, `CB8 digital_asset_holdings`.
- **`risk_model`** — onboarding score **60 (MEDIUM)** on a 0–100 scale, plus review cadence.

## Step 2 — Derive *who to look up* (`CustomerRef`)
`backend/ingest/base.py` reads that JSON and extracts the query keys each source needs:
`ticker=COIN · cik=0001679788 · domain=coinbase.com · name="Coinbase Global, Inc."`.
These identifiers are how every source finds *this customer specifically*.

## Step 3 — The sources fetch real info (Mira's lane)
Each connector queries one source BY those keys and returns the SAME shape (`EvidenceEvent`).

| Connector | Queries by | What it does | Real Coinbase output |
|---|---|---|---|
| **SEC EDGAR** (`sec_earnings`) | ticker `COIN` | Lists recent filings (10-K/8-K) → one event each (form, date, URL). **Level-2**: downloads the 10-K, chunks it, finds passages relevant to each assertion. | 12 real filings; 6 cited 10-K passages |
| **Wayback** (`wayback`) | domain | Historical homepage snapshots, kept where content actually changed → website-drift over time. | 8 real changes (2019→2024) |
| **Google News** (`news_rss`) | name | News search feed → one event per article. | 12 articles |
| **GDELT** (`gdelt`) | name | Global news + tone (adverse-media signal). | live (rate-limits on burst) |
| **GLEIF** (`gleif`) | LEI/name | Official legal-entity record (jurisdiction, status) + ownership links. | 1 record (US-TX, active) |
| **stubs** (sanctions/registry/funding) | — | Uniform interface, return nothing yet — ready to fill. | 0 |
| **fixtures** | customer_id | Replays authored/cached events — offline-demo backbone + the only source for fictional Meridian. | replays cache |

Every event comes out identical: `{type, summary, payload, source, source_url, published_at,
confidence, customer_id}`. `source_url` is the citation; the engine never needs to know the source.

## Step 4 — Merge into one timeline (`runner.py`)
`collect("coinbase-global")` runs all connectors, de-dupes by id, sorts by date → one clean stream
of ~30–40 real Coinbase events (2019→2026). Two modes:
- **offline** (`OFFLINE_DEMO=true`) → replay cached fixtures, deterministic, no network/keys (demo).
- **live** → hit real sources, cache each result to `data/fixtures/` for offline replay next time.

## Step 5 — Lightweight resolution (built in)
Because we query BY the customer's own identifiers, each event is stamped
`customer_id="coinbase-global"` with a `resolution_confidence` (1.0 exact SEC/ticker, ~0.75
name-only news). A dedicated fuzzy `resolve/` step isn't built yet — resolution happens at emission.

## Step 6 — The cheap relevance gate (`relevance.py`)
For Level-2 we don't send a whole 10-K to a model — the relevance filter ranks passages against an
assertion and keeps only the top few. This IS the cost cascade's **Stage 1**. Lexical/free by
default (quality is mixed; embeddings improve it — Miguel's call).

## Step 7 — Handoff to the engine (Miguel's lane)
The merged `EvidenceEvent` stream is what `backend/drift/` consumes: it checks each event against
the assertions (`confirms / contradicts / irrelevant`), aggregates, and recomputes the risk score →
a `DriftAlert`. **Mira produces the evidence; Miguel produces the verdict.** The boundary is the
`EvidenceEvent` shape.

## Honest notes
- **"Constantly fetch"** = design intent, not yet a daemon. Sources fetch **on-demand** when the
  runner is triggered (and cache what they find). Continuous monitoring = schedule the runner.
- **Relevance quality** (lexical) is mixed today (~half the 10-K passage matches are noisy);
  semantic embeddings fix it (Miguel).

## Built vs. not (so the picture is honest) — canonical: [STATUS.md](../STATUS.md)
- ✅ Built & tested: schemas (+ 4-dimension tagging), 3 demo entities (Coinbase/Meridian/HashKey),
  grain_lite, **9 live connectors** + fixtures, the relevance gate, the runner, **the drift engine
  on live Apertus**, the **API keystone**, **governance** (hash-chained audit + HITL + RBAC), the
  **network graph**, the smoke tests.
- 🟡 Partial: relevance quality (lexical → swissai embeddings available); resolution at-emission;
  cost meter works but no UI widget; dashboard built but not yet live-wired.
- 🔜 The gold gap: **combination/breadth threshold** (fire on ≥3 dimensions co-moving) + the Apertus
  **connect-the-dots narrative** (Miguel); dashboard live-wire + 4-lane + network viz (Giacomo);
  registry connector; pitch deck.

## Run it
```bash
python -m backend.ingest.runner coinbase-global            # offline (fixtures)
OFFLINE_DEMO=false SEC_USER_AGENT="amina-drift (you@email)" \
  python -m backend.ingest.runner coinbase-global --live   # live sources
python -m backend.ingest.smoke_test                        # deterministic checks
```
