# grain_lite — SEC filing & earnings ingestion with grounded passage scoring

A self-contained module that turns SEC filings and earnings calls into **cited, assertion-relevant
evidence**. It powers the optional Level-2 enhancement of the `sec_earnings` connector: fetch a
customer's 10-K/10-Q/8-K/DEF-14A, chunk the long filings into passages, embed them, and keep only the
passages relevant to each on-file `Assertion` — each with a verbatim quote + source URL for grounding.

## What's here
| File | What it does |
|---|---|
| `sources/edgar.py` | SEC EDGAR: ticker→CIK→filing list→download→clean HTML/XBRL→text (10-K/10-Q/8-K/DEF-14A) |
| `sources/transcript.py` | Earnings-call transcripts via Alpha Vantage (+ Motley Fool fallback), with sentiment |
| `sources/earnings_calendar.py` | when calls happen |
| `sources/base.py` | `DocumentSource` / `Document` / `SourceType` — the document-source interface |
| `chunker.py` | section-aware chunking of long filings → passages |
| `embedder.py` | embeddings + `cosine_similarity` → the relevance filter over passages |
| `llm_client.py` | `complete()` (JSON, retry, cache) · `score_source_holistically()` · `_validate_key_quote()` grounding gate · `score_passages_batch()` |
| `cache.py` | file-based LLM/embedding cache, so runs are offline & reproducible |
| `config.py` | env-driven config (model + embedding + cache) |

## Provider
This optional SEC deep-read path uses an OpenAI-compatible endpoint, **independent of the core Apertus
cascade**. Defaults in `config.py`: LLM `gpt-4.1-mini`, embeddings `text-embedding-3-small`. Keys:
```
OPENAI_API_KEY=...
ALPHAVANTAGE_API_KEY=...        # free tier; enables earnings-call transcripts
SEC_USER_AGENT="amina-drift <you@email>"   # SEC requires a contact UA string
```
It is **off by default** (`SEC_LEVEL2=false`); the core pipeline runs on Apertus without it.

## How it plugs into the pipeline
- **Ingest:** `edgar.py` + `transcript.py` fetch a customer's filings & earnings calls → `chunker`
  → `embedder` → cosine-filter the passages relevant to each `Assertion`, wrapped as `EvidenceEvent`s
  (`shared/schemas/evidence.py`). Best for listed entities (e.g. Coinbase).
- **Scoring:** `score_source_holistically()` is the grounded scorer; `_validate_key_quote()` is the
  anti-hallucination gate — it rejects any quote not found verbatim in the source.

## Note
Only `score_source_holistically()` (inline prompt) and `complete()` are exercised by the demo; the
other `load_prompt()`-based helpers expect prompt files that are not included and are not used here.
