# CLAUDE.md — `backend/drift/` · OWNER: Miguel (Drift Modelling)

> Read the root `/CLAUDE.md` first. This is **Miguel's lane** — the engine, the "wow." You own
> the **AI Intelligence Quality (25%)** axis. Mira's `cascade/` calls into you; Giacomo's UI
> renders your `DriftAlert`. Don't edit connectors (`ingest/`) or the cascade orchestration —
> consume `EvidenceEvent`/`Snapshot`, produce `DriftAlert`.

## ✅ Schema decisions already locked (2026-06-20) — build to these
- **`risk_score` is a DERIVED OUTPUT, not a monitored assertion.** Your engine *computes* it. The
  onboarding baseline is `customer.risk_model.onboarding_score`; `CB10`/`MS13` are baseline anchors
  only — never diff them against evidence. Drift = the movement of this computed number.
- **`DriftAlert` now has `also_contradicts: list[str]`** (the secondary assertions a drift episode
  breaks) alongside the primary `contradicted_assertion_id`. Both example alerts use it.
- **Alert granularity = ONE alert per customer drift-episode** (aggregating contradictions), not one
  per assertion.
- **Demo numbers are fixed:** Meridian flips **LOW 28 → HIGH 82** (the wow); Coinbase stays
  **MEDIUM 60 → 66** (within-band upward pressure, deliberate contrast — do NOT make it flip).

## 📝 Note from Mira's lane — optional FREE shared embedder
We're running zero-cost: cascade LLM → **Apertus** (free, Swiss-sovereign), and Mira's Stage-1
relevance filter → **lexical** (free, default). Your `ConceptAxisEmbedder` is already free/offline —
keep it for the explainability pitch. **Optional:** one free local `sentence-transformers` model
(all-MiniLM-L6-v2, CPU) could serve BOTH your trajectory (you noted it's swappable) AND Mira's
retrieval (`RELEVANCE_EMBEDDINGS=local`). Not wired yet — only worth it if semantic quality beats
keyword/concept-axis matching for the demo. No OpenAI anywhere (avoids paid embeddings).

## 🚩 YOUR OPEN CALL — decide this, it sets Mira's scope (Q2.1, the big one)
**Can you detect Meridian's silent re-tiering from the EVENT SEQUENCE alone, or do you need
periodic `Snapshot`s (+ embedding trajectory)?** Both fixtures are currently events-only and
`evidence.py` has no Snapshot in use. This is the single most important architectural decision on
your side:
- If **events-only** works → Mira builds less, you detect drift by accumulating contradictions over
  the event timeline. Simpler, faster to demo.
- If you need **snapshots** → tell Mira NOW so she emits them; this is what powers the
  embedding-trajectory "wow," but it's more to build.
Decide early and tell the team — everything downstream depends on it. Also confirm **Q3.2** (do you
want a per-factor score breakdown in the alert for explainability?) and **Q1.4** (`last_verified`
is present for confidence decay).

## Your mission
Turn "the bank's beliefs vs. reality" into measurable, explainable drift. Build the thing nobody
else has: **evidence-driven invalidation of specific KYC assertions** + **slow structural drift**.

## What you build
1. **Assertion-diff (event drift)** — given an `Assertion` and a candidate `EvidenceEvent`,
   classify `{confirms, contradicts, irrelevant, ambiguous}` with a **cited rationale**. This is
   the Stage-2 LLM verdict prompt (Mira's cascade decides *which* pairs reach it — keep it cheap).
2. **Slow structural drift (the headline)** — single events are noise; detect the *trajectory*
   over the `Snapshot` timeline. Pick a lead mechanism (discuss with team):
   - **Assertion confidence decay** (Bayesian-ish): confidence drops as time + weak contradicting
     signals accumulate → fires "business model uncertain → re-verify" *before* a smoking gun.
     **Most explainable — best for a compliance jury.**
   - **Embedding trajectory**: embed each snapshot's public description; track the vector
     migrating between semantic regions (SaaS → crypto). **Most visually striking.**
   - **Change-point detection** (CUSUM / online Bayesian) to pin *when* drift became significant
     (good for the audit trail).
3. **Drift score + re-tiering** — keep it a **transparent weighted model**, not a black box (the
   compliance audience rewards attributability, and it *is* the explainability):
   `per-assertion drift = f(contradiction weight, staleness, envelope breach, trajectory velocity)`
   `risk_now = baseline_tier + Σ assertion_drift` → re-tier on threshold crossing.
4. **Explainability payload** on every `DriftAlert`: `drift_score`, `contradicted_assertion`,
   `evidence[]` (with source URLs), `rationale`, `what_would_flip`, `confidence`.
5. **Grounding / hallucination check**: never emit a flag whose evidence doesn't actually support
   it — validate that cited evidence contains the claim (anti-hallucination gate).
6. **`eval/scenarios/`** (with Giacomo): turn each business scenario into a runnable test that
   asserts the right flag fires (and wrong ones don't).

## 🎯 The bar — what "done" looks like (you own AI Intelligence, 25%)
This is the heart of the project; the demo lives or dies on it. "Done" =
1. **Both base cases produce their correct `DriftAlert`** from the seeded data:
   **Meridian** re-tiers LOW 28 → HIGH 82 (the trajectory wow); **Coinbase** rises MEDIUM 60 → 66
   with the SEC-suit-then-dismissed `what_would_flip` arc.
2. **Event drift works**: an `(Assertion, EvidenceEvent)` pair → `{confirms/contradicts/irrelevant/
   ambiguous}` + cited rationale.
3. **Slow structural drift works** on Meridian (your Q2.1 mechanism) — the signal is the
   *trajectory*, not any single event.
4. **The score is transparent & attributable** — `risk_now` is a weighted sum you can explain
   line-by-line to a compliance officer (no black box).
5. **Cost-aware**: assume you DON'T see every signal — the cheap filter gates which pairs reach the
   LLM. (Filter logic is yours; the metered LLM wrapper + token counting is Mira's.)
6. **Grounded**: NEVER emit a flag whose evidence doesn't support the rationale (anti-hallucination
   gate). This is non-negotiable — general LLMs are disqualified as final compliance deciders, so
   citation-grounded "why" is the whole point.
7. **Measurable**: it fires the right flags on the two cases AND stays quiet on noise events (so we
   can show precision, not just recall).

## 🥇 GOLD task — connect the dots across 4 dimensions (current focus)
The product's "wow" is catching drift that **no single signal crosses** — the combination of quiet
changes over time. Two things to build on top of your engine (see root `/CLAUDE.md` §1.5):

1. **Dimension-aware combination scoring.** Every assertion now maps to one of 4 dimensions via
   `shared/schemas/dimension_for_predicate()` (Identity / Network / Behavioural / Contextual).
   **Boost the risk when contradictions span ≥3 dimensions simultaneously** — that co-movement is
   the real signal, even when each assertion's individual surprise is sub-threshold. (An interaction
   term, not just a sum.) The API already returns `dimensions_drifted` per case; make the engine
   *escalate on breadth*, not only magnitude.
2. **Narrative synthesis (Apertus-70B).** Add a "connect-the-dots" paragraph to the headline alert:
   *"Onboarded 2021 as X. Over 18 months: funding from an offshore fund (Identity) → PEP-adjacent
   director (Network) → website pivot to trading (Contextual) → volume spike (Behavioural).
   Individually innocent; together a materially different risk."* This narrative IS the demo — make
   it cite the dimensions + the dated events. (You already call Apertus for `synthesize`; extend it.)

Startups are the wedge (AMINA's hardest case) — Mira is adding funding/investor signals; a new lead
investor = a likely NEW beneficial owner → that should light the Identity dimension and feed the
combination.

## 🎯 SCORING — exactly what you build (you REUSE grain_lite, don't rebuild it)
We vendored Sablier's GRAIN scorer into `backend/grain_lite/`. It already gives you the hard
infra. **Your job is the drift-specific scoring on top.** Read `backend/grain_lite/README.md`.

### What you REUSE as-is (do NOT rebuild)
- `grain_lite/llm_client.py::score_source_holistically(...)` — reads ALL passages from a source,
  JSON-mode output, prompt-injection sanitization, caching. Returns `{tier, direction_score,
  key_quote, reasoning}`. **This is your Stage-2 starting point.**
- `grain_lite/llm_client.py::_validate_key_quote(quote, passages)` — the **anti-hallucination
  gate**: guarantees the cited quote actually exists in the source (fuzzy-matches or replaces a
  fabricated one). **Call this on every verdict. This is your grounding guarantee (Compliance 20%).**
- `score_passages_batch()` + the file cache — your cost levers (batch + cache = cheap repeat runs).
- Provider = OpenAI (`gpt-4.1-mini`) via the existing client, for now (Mira's call to keep as-is).

### What you BUILD (the scoring work — this is yours)
1. **The verdict prompt** — fork `score_source_holistically` into
   `score_assertion_drift(assertion, passages, source_type)` and **rewrite the prompt** from
   "theme exposure tier" → the **drift verdict**. Input: one `Assertion` (predicate + onboarding
   value) + the retrieved passages. Output JSON:
   `{verdict: confirms|contradicts|irrelevant|ambiguous, contradiction_strength: 0..1,
     key_quote: <verbatim>, rationale: <1-3 sentences>}`.
   Keep the "copy the quote VERBATIM" instruction + sanitization so the grounding gate works.
2. **Ground every verdict** — run `_validate_key_quote(result["key_quote"], passages)`. No flag
   ships with an ungrounded quote.
3. **Per-assertion aggregation** — combine verdicts across sources/events for one assertion →
   contribution `= contradiction_strength × source_confidence × recency_weight`. Flip the
   assertion `valid → contradicted` past a threshold.
4. **Re-score the customer (DERIVED OUTPUT)** — `risk_now = onboarding_score + Σ (assertion
   contribution × predicate_severity)`. Transparent weighted sum you can read line-by-line; map to
   band (LOW/MED/HIGH). This produces `old_/new_risk_score`.
5. **Slow structural drift** — accumulate contradictions across the event timeline (your Q2.1
   mechanism) so Meridian climbs 28→82; the signal is the trajectory, not one event.
6. **Emit `DriftAlert`** — `contradicted_assertion_id` (primary) + `also_contradicts[]` +
   `evidence_ids` + `rationale` + `what_would_flip` + `recommended_action` + old/new score + confidence.

### The handoff (so you never block)
- **Mira gives you**: per `(customer, source)` the **retrieved relevant passages** + the
  `EvidenceEvent`s. She owns fetch → chunk → embed → Stage-1 cosine relevance filter.
- **You give back**: the verdict + the re-score + the `DriftAlert`. You do NOT fetch data.
- Stage boundary: Mira's cosine filter decides WHICH `(assertion, passages)` reach your scorer
  (Stage-1, cheap); your `score_assertion_drift` is Stage-2 (LLM).

## Contracts (read `shared/schemas/`)
- **Consume** `Assertion` (from `data/customers/`) + `EvidenceEvent`/`Snapshot` (from Mira).
- **Produce** `DriftAlert`. Don't change its shape without pinging Giacomo (UI) + Mira.

## Design constraints
- **Cost-aware**: your Stage-2 prompt runs only on gated pairs — assume you DON'T see every signal.
  Make the cheap-tier-friendly features (rules/embeddings) do as much as possible before the LLM.
- **Explainable > clever**: a transparent weighted sum that a compliance officer can audit beats
  an opaque ML score. Resist the urge to over-model.
- **Demo reality**: slow drift is shown via the pre-built snapshot timeline (Mira) — your engine
  must produce a believable green→amber→red progression across it.
