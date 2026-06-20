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
