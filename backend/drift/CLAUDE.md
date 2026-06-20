# CLAUDE.md — `backend/drift/` · OWNER: Miguel (Drift Modelling)

> Read the root `/CLAUDE.md` first. This is **Miguel's lane** — the engine, the "wow." You own
> the **AI Intelligence Quality (25%)** axis. Mira's `cascade/` calls into you; Giacomo's UI
> renders your `DriftAlert`. Don't edit connectors (`ingest/`) or the cascade orchestration —
> consume `EvidenceEvent`/`Snapshot`, produce `DriftAlert`.

## 🚩 FIRST TASK (before building the engine)
Help decide the schemas (see root `/CLAUDE.md` §0 + `shared/schemas/README.md`). **Your angle:**
- You consume `Assertion` + `EvidenceEvent` and produce `DriftAlert` — so you have the biggest
  stake. Open the two base-case sets — esp. the drift hero **Meridian Sands**
  (`data/customers/meridian-sands.json`, `data/fixtures/meridian-events.example.json`,
  `eval/scenarios/meridian-drift.example.json`) plus **Coinbase** (`*coinbase*`).
- Drive **Q2.1**: can you detect Meridian's silent re-tiering (LOW 28 → HIGH 82; SaaS→crypto
  pivot + offshore + new UBO) from events alone, or do you need `Snapshot`s + an embedding
  trajectory? Your answer sets Mira's scope.
- **Q3.2**: does `DriftAlert` need a per-factor score breakdown for explainability? **Q1.4**:
  confirm you get `last_verified` for confidence decay.
Bring these to the kickoff. Don't build the engine until the three shapes are agreed.

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
