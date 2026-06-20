# Drift Engine — Architecture & Extension Guide

This document describes how the KYC-drift engine works end-to-end, the data contracts that make it
modular, and the procedures to add a new public source or a new risk signal.

A KYC profile is modelled as a set of dated, testable assertions. Public sources are converted into a
uniform evidence stream. The engine re-validates each assertion against that stream and scores the
divergence (drift) over time — the score rises when an assumption is contradicted and falls when it is
restored.

---

## 1. Pipeline

```
 Layer 2 (internal)          Layer 1 (public)              Engine (backend/drift/)
 data/customers/*.json       backend/ingest/*              ┌───────────────────────────────────────┐
 ┌────────────────────┐      ┌───────────────────┐         │ ① GATE  → ② VERDICT → ③ SCORE → ④ ALERT │
 │ KYC profile =      │      │ N connectors,     │         │  relevance   confirms/   0–100   drift- │
 │ Assertion[]        │─────▶│ each → Evidence   │────────▶│  (no LLM)    contradicts level   based  │
 │ (testable beliefs) │ who  │ Event (uniform)   │  feed   │              /resolves          alerts  │
 └────────────────────┘ to   └───────────────────┘         └───────────────────────────────────────┘
                         look up                                              │
                                                                              ▼
                                                            ⑤ GOVERN (HITL approve/escalate + audit)
                                                                              ▼
                                                            ⑥ API (FastAPI) → dashboard
```

### Layer 2 — beliefs (`data/customers/<id>.json`)
The KYC profile is authored as `assertions`, each `(predicate, value, as_of, last_verified, source,
confidence)`. `predicate` is one of 28 fields (`business_model`, `ubo`, `sanctions_status`,
`operating_geographies`, …). `risk_score`/`risk_tier` are outputs, not monitored beliefs.

### Layer 1 — sources (`backend/ingest/`)
Each connector subclasses `Connector` and returns the same `EvidenceEvent` shape, so the engine is
independent of the source. Nine connectors are live (SEC, Wayback, Google News, GDELT, Event Registry,
GLEIF, OpenSanctions, funding, crt.sh). `runner.collect(customer_id)` merges, de-dupes and sorts them
into one timeline. Default mode is offline (cached fixtures); no network or keys are required to run.

`EvidenceEvent` = `{id, customer_id, type, summary, payload, source, source_url, published_at,
confidence}`. `type` ∈ `{news, registry_change, ownership_change, sanctions_hit, pep_hit,
website_change, funding, transaction}`. `source_url` is the citation rendered by the UI.

### ① Stage 1 — gate (`backend/drift/classify.py::is_candidate`) — no generative LLM
Decides, per `(belief, event)` pair, whether it is worth a verdict. Order of checks:
1. **Authoritative-only routing** (`AUTHORITATIVE_ONLY`): structured beliefs such as
   `sanctions_status` are moved only by their authoritative source (a `sanctions_hit`), never by news.
2. **Keyword / type / payload-flag** match.
3. **Embedding backstop** (`arctic-embed` on CSCS) against a rich belief query built from
   `SEMANTIC_HINTS`; catches paraphrase the keywords miss. Falls back to lexical overlap offline.

Measured in `eval/gate/`: 100% material recall on real events; 87% on an adversarial paraphrase set
(40% for keyword-only).

Two belief classes are scored deterministically (no LLM):
- `check_screen_match` — sanctions/PEP screen hits, scored from match quality (confirmed designation
  vs. name-only "needs verification" match).
- `check_envelope_breach` — quantitative beliefs (volume/geography) by arithmetic.

### ② Stage 2 — verdict (`backend/drift/llm.py::ApiLLM.classify`) — cheap LLM (Apertus-8B)
Returns `{verdict ∈ confirms|contradicts|resolves|irrelevant|ambiguous, strength 0–1, evidence_quote,
rationale}`, judged against the specific belief value. `resolves` marks de-risking events (suit
dismissed, licence granted). An anti-hallucination gate drops any `contradicts`/`resolves` whose cited
quote is not present in the evidence.

### ③ Scoring (`backend/drift/score.py::assess`)
Per belief, `surprise` (drift magnitude 0–1) = weighted sum of `contra` (graded contradiction
strength, scaled by `EVIDENCE_WEIGHT` source reliability), `envelope` breach, and `trajectory`. The
contribution is `d × risk_weight(predicate)`. The customer level uses two channels:
- **Accumulation** — a diminishing-returns drift index over contributions (the strongest drift counts
  fully; each additional co-moving dimension adds less). It climbs as drift accumulates and asymptotes
  toward `ACCUMULATION_CAP` (88), so it does not saturate to 100 from many moderate signals.
- **Critical** — an actual sanctions designation (authoritative-only) maps to its ceiling (~100).

`resolves` verdicts subtract, so a score can fall when a concern is retracted. Staleness is computed
but excluded from the level (it is a data-freshness / re-KYC signal, surfaced via assertion status).

### ④ Alerting (`backend/drift/engine.py::replay`)
Tier bands (LOW/MEDIUM/HIGH) are a label and review-cadence input, not the alert trigger. An alert
fires on the drift itself: a newly invalidated assumption, breadth (≥`BREADTH_MIN_DIMS` dimensions
co-moving), a critical hit, or a one-tick velocity jump ≥ `VELOCITY_ALERT_POINTS`. Each `DriftAlert`
carries the contradicted assertion(s), cited `evidence_ids`, old/new score, recommended action,
confidence, and token cost.

### ⑤ Governance (`backend/govern/`) and ⑥ API/UI (`backend/api/`, `frontend/`)
Each alert is `PENDING` until a human acts; RBAC enforces four-eyes (closing a HIGH re-tier requires
MLRO); decisions are written to a hash-chained, tamper-evident audit log. The API serves the
`CustomerCase` (customer + events + alerts + timeline + cost) to the dashboard.

### Cost cascade
Stage 0/1 (rules + free embeddings) filter most pairs at zero LLM cost. Stage 2 (Apertus-8B) runs
only on surviving pairs, each classified once (memoised). Stage 3 (Apertus-70B) runs only when an
alert fires. Models are Swiss-hosted (CSCS); Layer-2 data is not sent off-jurisdiction.

---

## 2. Contracts

Three shapes in `shared/schemas/` decouple the lanes; extensions conform to a contract and do not
modify the engine.

| Contract | Produced by | Consumed by | To extend |
|---|---|---|---|
| `Assertion` | authored KYC profile | scorer | add a belief (a new predicate) |
| `EvidenceEvent` | every connector | gate + verdict | add a source that emits this shape |
| `DriftAlert` | engine | governance + UI | rarely; coordinate a field with the UI |

Stage boundaries: the gate decides which pairs, the verdict decides the relationship, the scorer
decides the number, the engine decides when to alert. Each stage is a pure function of the previous
stage's contract.

---

## 3. Robustness & scalability

- **Offline operation:** every connector caches to `data/fixtures/`; `OFFLINE_DEMO=true` replays them
  with no network or keys; `ApiLLM` falls back to a deterministic `MockLLM` per call on endpoint error.
- **Cost scaling:** the cascade runs the frontier model ~twice per customer, not per event; verdicts
  are memoised so each `(belief, event)` pair is classified once.
- **Swappable components:** `get_llm()` selects Mock/Apertus/any OpenAI-compatible endpoint behind one
  interface; the embedder is swappable behind `embed_texts`; the gate's semantic backstop degrades to
  lexical with no configuration.
- **Deterministic high-stakes paths:** sanctions/PEP and quantitative beliefs are scored by code
  (`check_screen_match`, `check_envelope_breach`), not by an LLM; an unverified name-only screen match
  elevates modestly and routes to a human rather than auto-condemning.
- **Tests:** `eval/gate/` (relevance recall), `eval/stage2/` (verdict precision), and an offline
  regression suite (`backend/drift/test_calibration.py`).

---

## 4. Extension procedures

### 4.1 Add a source (connector)
Implement one `fetch` method returning `EvidenceEvent`s. Caching, offline replay, merging, de-dup and
id-stamping are handled by the base class.

```python
# backend/ingest/courtlistener.py   (example: litigation, free CourtListener API)
from backend.ingest.base import Connector, CustomerRef, make_event
from shared.schemas import EvidenceEvent, EvidenceType

class CourtListenerConnector(Connector):
    name = "courtlistener"            # event-id prefix + cache filename
    source_label = "CourtListener"

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        # query the source BY the customer's identifiers (name/domain/lei/ticker on `customer`)
        dockets = _search_courtlistener(customer.legal_name)
        return [
            make_event(
                connector=self.name, customer=customer,
                type=EvidenceType.news,                 # litigation → adverse-media lane
                summary=f"{customer.legal_name} named in {d['case']} ({d['court']})",
                source=self.source_label, source_url=d["url"], published_at=d["date_filed"],
                payload={"court": d["court"], "nature": d["nature_of_suit"]},
            )
            for d in dockets
        ]
```

Register it:
```python
# backend/ingest/runner.py
LIVE_CONNECTORS = [ ..., CourtListenerConnector() ]
```

The gate, verdict, scorer, alerts, governance and UI consume it automatically. Choose the
`EvidenceType` deliberately — it sets the default dimension and the evidence-reliability weight
(`website_change` is soft; `registry_change`/`sanctions_hit` are authoritative).

### 4.2 Add a belief (predicate)
1. Add the value to the `Predicate` enum (`shared/schemas/`).
2. Map its dimension in `shared/schemas/dimensions.py::PREDICATE_DIMENSION` (Identity / Network /
   Behavioural / Contextual).
3. Set its severity: `config.RISK_WEIGHT["litigation_status"] = 0.85` (ceiling = `100 × weight`).
4. Add gate hints: `classify.PREDICATE_SIGNALS` (keywords) and `classify.SEMANTIC_HINTS` (a one-line
   description for the embedding backstop).
5. Author the assertion in `data/customers/<id>.json`.

The scorer iterates predicates generically; no engine code changes.

### 4.3 Map a signal to a flag and action
```python
# backend/drift/engine.py :: _FLAGS
"litigation_status": ("Adverse Litigation — EDD", "Trigger enhanced due diligence; assess SAR need."),
```
The heavy-tier model writes a contextual narrative on the headline alert; this map is the deterministic
fallback and the canonical flag label.

### 4.4 Add a structured / authoritative belief (sanctions-like)
For binary, list-driven beliefs that must not be inferred from news:
- Route them: `classify.AUTHORITATIVE_ONLY["my_status"] = {"types": {"my_hit"}, "flags": {...}}`.
- Score them in `classify.check_screen_match` by match quality (confirmed → full strength → critical
  channel; unverified/name-only → capped potential + HITL alert).

### 4.5 Add a quantitative belief (transactions / volume / geography)
- Give the assertion an `expected_envelope` (`{low, high}` for volume; `{allowed_set}` for geography).
- Emit `EvidenceType.transaction` events whose `payload` carries the number/country.
- `check_envelope_breach` flags the deviation deterministically (magnitude 0–1), feeding `surprise`.

### 4.6 Configuration knobs (`backend/drift/config.py`)
| Knob | Meaning |
|---|---|
| `RISK_WEIGHT[predicate]` | severity of breaking this belief (ceiling = `100×weight`) |
| `RISK_DIRECTION[predicate]` | sign (+ raises risk; funding is a question, weighted lower) |
| `EVIDENCE_WEIGHT[type]` | source reliability (website diff 0.45; registry/screen 1.0) |
| `ACCUMULATION_CAP` | non-designation drift maximum (88); 88–100 reserved for sanctions |
| `BREADTH_DECAY` | weight of each additional co-moving dimension |
| `DRIFT_SATURATION` | accumulated drift that maps ~63% toward the cap |
| `VELOCITY_ALERT_POINTS`, `BREADTH_MIN_DIMS` | drift-alert triggers |

---

## 5. Brief signals — current coverage

Each signal decomposes into (source) + (belief) + (flag/action). The rows marked "needs source"
require a transaction data source; the consuming mechanism (`expected_envelope` +
`check_envelope_breach` + the `transaction` `EvidenceType`) already exists.

| # | Signal | Status | Wired (source · belief · flag) | To complete |
|---|---|---|---|---|
| 1 | Negative-news spike → Reputational | implemented | GDELT/EventRegistry/News · `adverse_media_status` · *Adverse Media* | — |
| 6 | Public pivot → Business-Model Change | implemented | Wayback/news · `business_model` · *Material Business-Model Change* | — |
| 7 | Jurisdiction/legal-form move → Structural | implemented | registry/embedding · `operating_geographies` + envelope | — |
| 8 | New UBO → Ownership Change | implemented | funding/GLEIF · `ubo` · *Ownership Change – KYC Drift* | — |
| 5 | Domain/website change → Business Activity | implemented | Wayback/crt.sh · `business_model` (soft-weighted) | — |
| 9 | Funding/expansion → Scale Risk | partial | funding connector → `source_of_wealth` | add a *Scale Risk Change* flag (§4.3) |
| 4 | Legal-entity name change → Re-KYC | partial | GLEIF supplies the name | add a monitored `legal_name` predicate (§4.2) |
| 2 | Cross-border transfers → Money Mule | needs source | envelope mechanism present | add a transaction connector (§4.1) + volume envelope (§4.5) |
| 3 | Linked entities + flows → Structuring | needs source | network graph (linked entities) | add transactions + a layering rule over the graph |
| 10 | Dormant → high volume → Dormancy Break | needs source | `activity_level` weight present | add transactions + a dormancy→spike rule (§4.5) |

---

## 6. Worked example — money-mule / dormancy capability

Touching no engine code:

1. **Source (§4.1):** a `TransactionConnector` emitting `EvidenceType.transaction` events with
   `payload={"amount_usd": ..., "counterparty_country": ..., "month": ...}`. Register it in
   `LIVE_CONNECTORS`.
2. **Belief (§4.5):** an `expected_monthly_volume` assertion with
   `expected_envelope={"low": 0, "high": 2_000_000}`, and a `counterparty_geographies` assertion with
   `expected_envelope={"allowed_set": ["CH","DE","FR"]}`.
3. **Detection:** `check_envelope_breach` flags an out-of-range transfer or out-of-set country; the
   magnitude feeds `surprise`.
4. **Flag (§4.3):** `"expected_monthly_volume": ("Behavioural Anomaly – Potential Money Mule", "Monitor; AML analyst review.")`.

The same envelope plus a dormant-period-then-spike check gives Dormancy Break; the same transactions
over the network graph give Structuring.

---

## 7. Validation

Real companies with authored KYC baselines, real public events, scored on Apertus:

| Company | case | result | property exercised |
|---|---|---|---|
| Geberit (Swiss industrial) | benign control | 22 / LOW, 0 alerts | no false positives on routine news; staleness excluded from level |
| Coinbase | rise then resolution | 60 → 82 → 67 | rises on the SEC suit, falls on the dismissal (signed drift) |
| Binance | multi-year deterioration | 58 → 84 / HIGH | sustained drift detected and ranked severe |
| HashKey | multi-dimension drift | 55 → 68 → 75 → 82 (gradual) | accumulation across the timeline, not a single-event jump |

Additional: `eval/gate/` (Stage-1 relevance recall), `eval/stage2/` (verdict precision), and the
offline regression suite (`backend/drift/test_calibration.py`).

---

## 8. Cost model

`replay()` returns a `cost` block (`backend/drift/llm.py::cost_report`) that reports token usage per
workflow, the cascade funnel, and dollar figures. Measured on Coinbase (Apertus), per customer-run:

```
63 (belief × event) pairs
  → Stage-1 gate filtered 28 (44%)        no LLM, $0
  → Stage-2 cheap model    35 calls       35,284 tokens
  → Stage-3 heavy model     2 calls        2,151 tokens   (5.4% escalation)
```

The fields:
- `cost_usd` — this run's cost; `cost_per_1000_analyses` and `cost_per_1000_alerts` — extrapolated
  figures (one "analysis" = monitoring one customer once across its timeline).
- `stage1_filtered_pct`, `stage2_cheap_calls`, `stage3_heavy_calls` — the funnel: where light vs.
  heavy models run.
- `savings_vs_all_heavy_pct` — saving vs. routing every Stage-2 pair through the heavy model (≈ 88%).

### Model choice

The default model is **Apertus** (`swiss-ai/Apertus-8B/70B-Instruct`, hosted on CSCS): Swiss-built,
open-weights, and run within Swiss jurisdiction, so Layer-2 KYC data is not sent off-jurisdiction —
the driver was data sovereignty and compliance, not price (it is also $0 for us on CSCS access).

The cascade is **model-agnostic**. Both tiers are configured at runtime —
`DRIFT_LLM_CHEAP_MODEL` / `DRIFT_LLM_HEAVY_MODEL` select any OpenAI-compatible endpoint, and
`PRICE_USD_PER_MTOK_CHEAP` / `PRICE_USD_PER_MTOK_HEAVY` in `config.py` set the prices the report uses.
Any "small model → frontier sibling" pair works; the cost figures recompute automatically.

### Estimated cost across model pairs

Using the measured per-analysis volume (≈ **35.3M** cheap + **2.15M** heavy tokens **per 1,000
analyses**), at approximate early-2026 blended rates (verify current provider pricing):

| Cheap tier → Heavy tier | ~$/Mtok (cheap / heavy) | Cost / 1,000 analyses |
|---|---|---|
| **Apertus-8B → 70B (CSCS, ours)** | 0 / 0 | **$0** (sovereign access) |
| Apertus / open 8B→70B, self-hosted (config default) | 0.20 / 3.00 | ~$13.5 |
| Open small→large (e.g. Llama/Mistral via Groq/Together) | 0.10 / 0.80 | ~$5 |
| Google Gemini Flash → Pro | 0.10 / 2.50 | ~$9 |
| OpenAI GPT-4o-mini → GPT-4o | 0.25 / 5.00 | ~$20 |
| Anthropic Claude Haiku → Sonnet | 0.80 / 6.00 | ~$41 |

Two points hold across every row: the **Stage-1 gate** removes ~40–60% of pairs before any model
runs, and the **cheap→heavy cascade** keeps cost ~88% below running everything on the heavy model —
so the absolute price scales with the chosen models, but the cascade's efficiency does not depend on
them. (Cost per 1,000 *alerts* is the same figure divided by the alerts-per-customer rate.)
