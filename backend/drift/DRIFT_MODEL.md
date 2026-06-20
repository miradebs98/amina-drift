# Drift Model — engine spec & how it's built (`backend/drift/`, owner: Miguel)

> This is the **implemented** engine (not a pre-build sketch). It reads a `ClientState` and produces
> `DriftAlert`s, runs fully offline against the fixtures, and stays inside the frozen `shared.schemas`.
> Hero case: **Meridian Sands** silently re-scores **28/LOW → 80/HIGH** across 8 events.
> `python backend/drift/run_demo.py` · `python -m pytest backend/drift/test_meridian.py -q`

## 0. Frame (sponsor-confirmed)
`drift = the gap between the bank's belief (assertions, from internal KYC) and what public data now says.`
Two **decoupled** axes (this is the key idea):
- **SURPRISE** = how far the posterior moved from the prior (drift magnitude, risk-agnostic).
- **RISK_IMPACT** = `surprise × risk_weight(predicate) × direction` (signed; can be ~0 / positive).

→ three situations, surfaced on every tick:
- **(a) gentle** — small surprise, score drifts slightly, *no flag* (`a:gentle`).
- **(b) flag** — big surprise *and* the 0–100 `risk_score` crosses a tier → `DriftAlert` (`b:flag`).
- **(c) notable** — big surprise but ~no risk move (e.g. a clean funding round) → logged, *no flag* (`c:notable`).

## 1. State / inputs (the contracts)
- `Assertion[]` — the bank's belief (RM-grade predicates: business_model, ubo, pep_status,
  sanctions_status, adverse_media_status, digital_asset_policy, regulatory_status, source_of_funds,
  operating_geographies, expected_monthly_volume envelope, …). `risk_score`/`risk_tier` are OUTPUTS, skipped.
- `EvidenceEvent[]` — Layer-1 signals (Mira). `Snapshot[]` — profile trajectory (mocked until Mira's Wayback).
- `ClientState` (`client_state.py`) — the proposed read-model assembling the above + `baseline_risk_score`
  (the prior, e.g. Meridian 28). **Propose at kickoff → move to `shared/schemas`.**

## 2. Detection — two regimes, one scorer
- **Event drift** (`classify.py`): Stage-0 `is_candidate` (rules/keywords, no LLM) → `check_envelope_breach`
  (deterministic: VG ∉ {AE}; 6M AED > envelope) → cheap-LLM `classify_event` verdict + **anti-hallucination
  gate** (drop any contradiction whose cited span isn't in the evidence).
- **Slow structural drift** (`trajectory.py`): embed each `Snapshot` onto interpretable concept axes
  (SaaS→crypto, UAE→offshore), track distance / velocity / change-point → fires *before* a hard
  contradiction; the moved axes map back to the implicated predicate.

## 3. Scoring → 0–100 risk_score (`score.py`, transparent weighted sum)
```
surprise(A)     = W·contra + W·staleness + W·envelope_breach + W·trajectory      # risk-agnostic, [0,1]
risk_impact(A)  = surprise(A) × risk_weight(predicate) × direction(predicate)     # signed
risk_score      = baseline + (100 − baseline) · saturate(Σ risk_impact)           # the prior climbs
tier            = band(risk_score)   # LOW 0–33 / MED 34–66 / HIGH 67–100
```
Detector says *what moved*; `risk_weight`/`direction` (a small taxonomy) say *whether it's risky & which way*.
`direction(source_of_wealth)=0.4` is the seam for case (c) — a funding round is a *question*, not a hit.

## 4. Output — `DriftAlert` (the frozen UI contract)
One per re-tier "episode": `old/new_risk_score` (0–100), `old/new_risk_tier`, `drift_score` (this tick's
surprise), `flag`, `severity`, `contradicted_assertion_id`, `evidence_ids` (+source_url), `rationale`,
`what_would_flip`, `recommended_action`, `confidence`, `stage_reached`, `tokens_used`. → HITL → audit.

## 5. Cost flow (`engine.replay` + `llm.CostMeter`)
Stage-0 `is_candidate` kills most pairs for ~$0 → cheap-LLM verdict on plausible pairs → heavy synth only
on a re-tier. Meter tracks cheap/heavy calls, tokens, escalation rate (Meridian: ~2%).

## 6. LLM — swappable (`llm.py`)
`get_llm()` returns **`MockLLM`** (offline, deterministic — default, what the tests use) or **`ApiLLM`**
(OpenAI-compatible) when `DRIFT_LLM_BASE_URL` + `DRIFT_LLM_API_KEY` are set. `ApiLLM` falls back to the
mock per-call on any error, so the demo never breaks offline.
**Apertus (Swiss-sovereign) for the cheap/sensitive tier** — sensitive Layer-2 KYC data never leaves CH
(a real Compliance-axis argument): set `DRIFT_LLM_CHEAP_MODEL=apertus-8b-instruct` once you have the
endpoint (Sat 10:00 onboarding). Heavy tier can stay Apertus-70B or a frontier model.

## 7. The Meridian arc (verified)
`28 🟢 → 41 🟡(pivot) → 45/57/65 🟡(offshore, UBO+PEP, funding) → 71 🔴(crypto brokerage) → 75/80 🔴(volume, adverse-media)`.
The `kyc_review` block makes the point: the static 3-year clock (next review 2026) would miss all of it;
our engine collapses it to "now."

## 8. Files
`config.py` (knobs) · `clock.py` (Real/SimClock) · `client_state.py` (loader + Meridian snapshots) ·
`embeddings.py` (concept-axis embedder) · `classify.py` (event drift) · `trajectory.py` (slow drift) ·
`llm.py` (Mock/ApiLLM + `get_llm`) · `score.py` (0–100 scorer) · `engine.py` (alerts + replay) ·
`run_demo.py` · `test_meridian.py`.

## 9. Kickoff asks / open
- Propose **`ClientState`** → `shared/schemas`. **Q2.1:** I own slow drift via trajectory+decay and *mock*
  `Snapshot`s, so Mira isn't blocked.
- **`diagnosis`** (temporal_drift / stale_record / possible_misrepresentation) isn't in `DriftAlert` yet —
  still a *proposed* field; encoded in the rationale for now (don't diverge from the frozen schema).
- Next: per-archetype predicate templates; the case-(c) "notable, low-risk" UI lane; real Wayback snapshots.
