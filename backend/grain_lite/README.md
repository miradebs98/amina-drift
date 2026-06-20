# grain_lite — vendored SEC + earnings ingestion & grounded LLM scoring

Reused from **Sablier's GRAIN** (our own production code — `sablier-backend/services/grain`).
A lean slice: the SEC/earnings ingestion + embeddings + the grounded LLM scorer, **OpenAI as-is**.
Stripped of GRAIN's GCS vector store, Postgres, portfolio/theme product layer. The Postgres LLM
cache was swapped for a **file-based cache** (`cache.py`) so the demo runs offline & reproducibly.

## What's here (and who uses it)
| File | What it does | Lane |
|---|---|---|
| `sources/edgar.py` | SEC EDGAR: ticker→CIK→filing list→download→clean HTML/XBRL→text (10-K/10-Q/8-K/DEF-14A) | **Mira** (ingest) |
| `sources/transcript.py` | **Earnings-call transcripts** via Alpha Vantage (+ Motley Fool fallback), with sentiment | **Mira** (ingest) |
| `sources/earnings_calendar.py` | when calls happen | Mira |
| `sources/base.py` | `DocumentSource` / `Document` / `SourceType` — connector interface pattern | Mira |
| `chunker.py` | section-aware chunking of long filings → passages | Mira |
| `embedder.py` | OpenAI embeddings + `cosine_similarity` → the **Stage-1 relevance filter** | Mira |
| `llm_client.py` | `complete()` (JSON, retry, cache) · `score_source_holistically()` · **`_validate_key_quote()` grounding gate** · `score_passages_batch()` (cost) | **Miguel** (scoring) + Mira (cascade) |
| `cache.py` | file-based LLM cache (replaces GRAIN's Postgres) | Mira |
| `config.py` | env-driven config (OpenAI model + embedding + cache) | both |

## Provider = OpenAI (as-is, for now)
`config.py` defaults: LLM `gpt-4.1-mini`, embeddings `text-embedding-3-small`. Set in `.env`:
```
OPENAI_API_KEY=...
ALPHAVANTAGE_API_KEY=...        # free tier; for earnings-call transcripts
SEC_USER_AGENT="amina-drift <you@email>"   # SEC requires a UA string
```
(We can swap the verdict tier to Claude later; not now.)

## How it plugs into amina-drift
- **Mira (Layer 1 / ingest):** use `edgar.py` + `transcript.py` to fetch a customer's filings &
  earnings calls → `chunker` → `embedder` → cosine-filter passages relevant to each `Assertion`
  (Stage-1). Wrap the output as `EvidenceEvent`s (schema in `shared/schemas/evidence.py`).
  → Best for **Coinbase** (real, listed). Meridian is fictional → stays fixture-based.
- **Miguel (drift / scoring):** reuse `score_source_holistically()` as the Stage-2 starting point
  — **rewrite its prompt** from "theme exposure" to "assertion contradiction." Keep
  `_validate_key_quote()` as the anti-hallucination gate. See `backend/drift/CLAUDE.md`.

## ⚠️ Note
- `llm_client.load_prompt()` (score/aggregate/theme_expand) needs prompt files that we did NOT
  vendor — those paths will fail. We only use `score_source_holistically()` (inline prompt) and
  `complete()`. Ignore the rest.
- This is our own IP; safe to keep in this repo. Provenance noted here for the AMINA reviewers.
