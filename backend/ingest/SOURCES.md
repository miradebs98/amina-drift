# Layer-1 sources — connector roster & status

Every source is a `Connector` that emits the same `EvidenceEvent` shape (schema in
`shared/schemas/evidence.py`). The drift engine consumes the merged stream — it doesn't
care which source an event came from. **Add a source = subclass `Connector`, add one line to
`runner.LIVE_CONNECTORS`.**

## Status
| Connector | Source | Key needed | Status | Emits | Cases |
|---|---|---|---|---|---|
| `sec_earnings.py` (L1) | **SEC EDGAR** filing list | none (UA) | ✅ **live, tested** (12 real Coinbase filings) | NEWS, OWNERSHIP_CHANGE | Coinbase |
| `sec_earnings.py` (L2) | **SEC 10-K full text → cited passages** vs assertions | none (lexical) / OpenAI (embeddings) | ✅ **live, tested** (6 cited 10-K passages, incl. the real OFAC-program text) | NEWS (+ `quote`, `related_assertion_hint`) | Coinbase |
| `wayback.py` | **Wayback Machine** CDX (website change over time) | none | ✅ **live, tested** (8 real homepage changes 2019→2024) | WEBSITE_CHANGE | Coinbase |
| `news_rss.py` | **Google News RSS** | none | ✅ **live, tested** (12 articles) | NEWS | both |
| `gleif.py` | **GLEIF** LEI + ownership graph | none | ✅ **live, tested** (real LEI record) | REGISTRY_CHANGE, OWNERSHIP_CHANGE | Coinbase |
| `gdelt.py` | **GDELT** adverse media + tone | none | ✅ live (rate-limited on burst → degrades gracefully) | NEWS | both |
| `event_registry.py` | **Event Registry** news + sentiment + concepts | partner key | ✅ **live, tested** (8 sentiment-tagged Coinbase articles) | NEWS (+ `sentiment`, `concepts`) | both |
| `sanctions.py` | **OpenSanctions / yente** — entity + UBO/director screening | free key or self-host | ✅ **live, tested** (flagged a NAME-ONLY UBO match → needs human verify) | SANCTIONS_HIT, PEP_HIT | both |
| `funding.py` | **Funding rounds + lead investor** (news-derived; new investor → UBO re-screen) | none | ✅ **live, tested** (HashKey: unicorn round, Gaorong $30M, $207M IPO) | FUNDING | startups |
| `cert_transparency.py` | **crt.sh** new-infra subdomains (digital exhaust, pre-announcement) | none | ✅ **live-tested** (HashKey: api-bank-mena, exchange., pro., global.) | WEBSITE_CHANGE | any domain |
| `fixtures.py` | authored/cached events | none | ✅ tested (Meridian 8, Coinbase 55, HashKey 55) | all | offline replay |
| `stubs.py::RegistryConnector` | ZEFIX / Companies House / ADGM | varies | ⬜ stub | REGISTRY_CHANGE | both |

**Network graph** (`backend/network/graph.py`, `GET /cases/{id}/network`): assembles connected
entities (UBOs/investors/partners) + sanctions/PEP flags from the above signals — the Network Risk
dimension. **Demo entities**: Coinbase (real listed), Meridian (fictional drift-hero), HashKey
(real startup).

**Meridian Sands is fictional** → it has no live data; its 8 events come from the authored
fixture and that's correct. **Coinbase is real** → it gets real, cited evidence from the live
connectors. The `evidence_quote`/`source_url` on each event is the citation the engine grounds on.

## Run it
```bash
# offline (default): replay fixtures, no network, no keys — deterministic demo
python -m backend.ingest.runner meridian-sands
python -m backend.ingest.runner coinbase-global

# live: hit the real sources (each caches to data/fixtures/*.cache.json for offline reuse)
export SEC_USER_AGENT="amina-drift (you@email)"
OFFLINE_DEMO=false python -m backend.ingest.runner coinbase-global --live
```

## Design notes
- **Connectors stay dumb**: they emit facts + a `source_url`. They do NOT decide relevance or
  drift — that's the engine. (Connectors emit facts; the engine decides what they mean.)
- **Resolution**: events are stamped `customer_id` at emission because each connector queries the
  source BY the customer's identifiers (ticker/LEI/domain/name) and attaches a `resolution_confidence`.
  Borderline (name-only) matches carry a lower confidence and are surfaced for human verification
  rather than auto-attributed.
- **Offline-safe**: every live fetch caches to `data/fixtures/`; on any error the connector falls
  back to cache → 0 events, never a crash. The stage demo runs with `OFFLINE_DEMO=true`.
- **Cost**: these connectors are ~free HTTP (no LLM). The optional Level-2 SEC enhancement
  (filing text → embed → relevance-filter) is where grain_lite's embedder = the Stage-1 gate.

## Level-2 SEC — how to run it
```bash
# adds 10-K full-text → cited passages relevant to each assertion (lexical without a key)
SEC_LEVEL2=true OFFLINE_DEMO=false SEC_USER_AGENT="amina-drift (you@email)" \
  python -m backend.ingest.runner coinbase-global --live
```
Relevance filter = **FREE lexical by default** (`RELEVANCE_EMBEDDINGS=lexical`). It is NOT
auto-switched to OpenAI even if a key exists (no surprise charges). Opt-in modes: `local` (free
sentence-transformers — not wired yet) or `openai` (paid). `payload.relevance_mode` shows which
ran. The relevance filter (`relevance.py`) IS the cost cascade's **Stage-1 cheap gate** — reusable
for any source. Whole project runs at **zero API cost**: cascade LLM → Apertus, relevance → lexical.

## Sanctions/PEP screening — the false-positive lesson (demo-gold)
The screen matches on **name**, so a 1.00 score is a *potential* match, NOT a confirmed identity
(e.g. "Brian Armstrong" hit a debarment list — almost certainly a DIFFERENT person). Events are
emitted with `match_basis="name-only"`, `needs_human_verification=true`, and **capped confidence** —
so the engine/UI treats them as "review required," never auto-escalate. This is exactly why HITL is
graded. **To improve precision:** add DOB / nationality to the person assertions so the screen can
disambiguate; pass them as match properties here.

## Next
1. Add a **registry** for non-US entities (ZEFIX/ADGM) so future non-listed customers work live.
2. Wire the **cost meter** around any LLM use (Level-2 embeddings) for the Cost-Efficiency axis.
3. De-dupe near-identical Event Registry articles (same story across outlets) by normalised title.
