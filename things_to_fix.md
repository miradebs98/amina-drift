# things_to_fix — amina-drift

> Review of the drift model + cost pipeline (compiled 2026-06-20). Each item: what's wrong,
> where, why it matters, and **how to fix it**. Ordered by leverage (grade impact ÷ effort).
> File refs are clickable: `path:line`.

## Priority ranking (do these in order)

| # | Fix | Effort | Axis it moves |
|---|---|---|---|
| ~~1~~ | ~~Memoize `classify_event` across ticks (kill quadratic LLM cost)~~ → **✅ FIXED** (see below) | ~1h | Cost (20%) |
| 2 | Add $/1k-alerts cost accounting + populate `cost_usd` | ~½ day | Cost (20%) |
| 3 | Derive `signal_mix` from real event text (real trajectory) | ~½ day | AI (25%) |
| 4 | Disk-cache `ApiLLM` (honor the "pre-warm" claim) | ~1h | Cost (20%) |
| 5 | Negative/noise corpus + precision/recall numbers | ~½ day | AI (25%) |
| 6 | Negative `RISK_DIRECTION` for resolving/de-risking events | ~1h | AI (25%) |
| 7 | Per-customer concept axes (not Meridian-hardcoded) | ~½ day | AI (25%) |
| 8 | Harden the `classify` prompt — **validated widened prompt ready** (`eval/stage2/`, 5–6/7→7/7 recall) | ~30m | AI (25%) |
| 9 | Build a thin `cascade/` module (make Stage-1/2/3 legible) | ~½ day | Cost (20%) + Eng (15%) |
| 10 | Enforce an escalation-rate cap | ~30m | Cost (20%) |
| 11 | Batch the verdict calls (one call per event, not per pair) | ~2h | Cost (20%) |
| 12 | Don't hardcode `RISK_SCORE_FULL_DRIFT`; calibrate it | ~2h | AI (25%) |
| 13 | Scope or fill the behavioral signals (money-mule/structuring/dormancy) | ~½ day | AI (25%) |
| 14 | Surface the cost meter in the UI | ~½ day | UX (20%) + Cost |
| 15 | **Stage-1 gate recall = 35% material** — broaden gate + never-gate adverse media; re-calibrate scorer (eval DONE in `eval/gate/`) | ~3h | Cost (20%) + AI (25%) |

---

## ✅ FIXED

### SCORING REDESIGN — "re-derive the risk LEVEL from the belief-state" `[2026-06-20, validate on Apertus + real companies]`
> Meridian was fabricated and the old score was reverse-fit to it. We rebuilt scoring on REAL companies
> (Coinbase, HashKey, Binance=drift-hero, Geberit=noise-control). Decisions, all landed in `score.py`/
> `engine.py`/`classify.py`/`config.py`:
> - **Level = re-derive from state, two channels** ([score.py](backend/drift/score.py)): *accumulation* (non-designation drift, severity-weighted `d×risk_weight`, breadth via noisy-OR) **capped at `ACCUMULATION_CAP=88`**, and *critical* (a confirmed sanctions designation → its ceiling ~100). Kills the noisy-OR→100 saturation (Binance 100→88).
> - **Staleness OUT of the level** — "not re-verified in N years" is a data-freshness / re-KYC signal, NOT inherent risk. Was silently climbing clean clients across band edges (**Geberit 35/MED→22/LOW, 0 alerts**).
> - **`resolves` (signed, down-moves)** — de-risking events (suit dismissed, licence granted) subtract from `contra`; `final_tier` follows the current score (de-ratcheted). **Coinbase: 60→97/88→65/68 rise-then-fall** on the real SEC-suit→dismissal. Grounded both directions (a fabricated "dismissed" can't lower risk).
> - **Alerts DECOUPLED from band-crossing** ([engine.py](backend/drift/engine.py)) — fire on the DRIFT (a NEW assumption invalidated, breadth ≥N, a critical hit, or a one-tick velocity ≥`VELOCITY_ALERT_POINTS`), never on a tier crossing. Catches within-band drift; kills band-edge false alerts. **Bands are now a LABEL/cadence only.**
> - **Sanctions/PEP scored DETERMINISTICALLY from match quality** (`check_screen_match`, not the LLM): confirmed designation → critical→~100; **name-only/`needs_human_verification` → capped POTENTIAL hit + HITL alert, NOT auto-100** (HashKey's "Xiao Feng"≈"FENG XIAO" wanted-list match was pinning it at 100).
> - **Why 100:** reserved for a *confirmed* sanctions designation (categorically prohibited/exit), NOT "lots of drift" — even Binance's $4.3B settlement tops at 88 (EDD/consider-exit).
> **Still open (next):** Stage-2 STRENGTH GRADATION + selective-70B verification — HashKey's accumulation still ~86 because 8B over-contradicts at scale (256 pairs, flat strength 1.0). Coinbase final 68 is 1pt into HIGH (minor). Tests are Meridian-based → rewrite around the real roster.

### 1. Quadratic LLM cost in replay — classify every event on every tick `[fixed 2026-06-20]`
**Was:** `replay` called `assess` once per date and `assess` re-classified every event `≤ as_of` on every tick, so each `(assertion, event)` pair was re-sent to the LLM at every subsequent tick — pure waste (verdicts are date-independent).
**Fix shipped:** a `verdict_cache` keyed by `(assertion_id, event_id)`, threaded through:
- [score.py:86-95](backend/drift/score.py#L86-L95) — `assess` takes an optional `verdict_cache`; `None` → fresh dict, so every one-shot caller is byte-for-byte unchanged.
- [score.py:114-120](backend/drift/score.py#L114-L120) — cache lookup before `classify_event`; `llm_used` still set on hits (so `stage_reached` is unchanged).
- [engine.py:144-153](backend/drift/engine.py#L144-L153), [:163](backend/drift/engine.py#L163) — `replay` builds one cache for the whole timeline and passes it to every tick.
- [cases.py:101-117](backend/api/cases.py#L101-L117) — shares replay's cache with the decomposition pass, making the existing "≈ free, cache hits" comment actually true.
**Measured (identical scores/tiers/alerts):** Coinbase cheap calls **51 → 13** (3.9×), tokens **4722 → 1229**; Meridian cheap calls **91 → 20** (4.5×), tokens **11051 → 4126**. `escalation_rate` rises (Meridian 0.05 → 0.20) — that's the *true* rate now that redundant cheap calls no longer pad the denominator; still passes the `<0.5` cheap-dominant test.
**Verified:** all 11 drift tests pass with this change against pristine `classify.py`. (The 4 currently-red tests are item #15's WIP gate-broadening needing scorer re-calibration, not this fix.)

---

## COST EFFECTIVENESS

### 2. 🔴 No dollar figures anywhere — the brief explicitly grades "cost per 1,000 alerts"
**Where:** tokens + escalation are counted ([backend/drift/llm.py:60-82](backend/drift/llm.py#L60-L82)) but never priced. `cost_usd` exists in the schema and is never set — [shared/schemas/audit.py:37](shared/schemas/audit.py#L37). The `cost` dict has no `$` — [backend/drift/engine.py:191-193](backend/drift/engine.py#L191-L193).
**Problem:** "estimate cost per 1,000 analyses/alerts" is a *named deliverable* for 20% of the grade, and it's missing.
**How to fix:**
- Add a price table to `config.py` (Apertus is free, but show the methodology with realistic frontier prices so the cascade savings are legible):
  ```python
  # USD per 1k tokens — set to your provider; Apertus on CSCS = 0.0 (the Swiss-sovereign cost story)
  PRICE_PER_1K_CHEAP = 0.0     # Apertus-8B
  PRICE_PER_1K_HEAVY = 0.0     # Apertus-70B
  # Comparison column for the slide: what a frontier-only pipeline WOULD cost
  PRICE_PER_1K_CHEAP_REF = 0.15   # e.g. gpt-4o-mini-class
  PRICE_PER_1K_HEAVY_REF = 5.00   # e.g. gpt-4o-class
  ```
- Add cost methods to `CostMeter` ([llm.py:59](backend/drift/llm.py#L59)):
  ```python
  def cost_usd(self, cheap_price, heavy_price):
      return (self.cheap_tokens/1000)*cheap_price + (self.heavy_tokens/1000)*heavy_price
  ```
- In `replay`'s `cost` dict add: `cost_usd`, `cost_per_1000_alerts = cost_usd / max(1,len(alerts)) * 1000`, plus the *reference* (frontier-only) cost so the slide reads "$X with our cascade vs $Y frontier-only → Z% saved."
- Populate `DriftAlert.cost_usd` / the audit entry from the per-alert `heavy_tokens` already tracked in `build_alert` ([engine.py:102-104](backend/drift/engine.py#L102-L104)).
**Verify:** `GET /cases/{id}` `cost` block shows `cost_usd` + `cost_per_1000_alerts` + `savings_vs_frontier_pct`.

### 4. 🟡 `ApiLLM` has no cache, but `get_llm` tells you to "pre-warm the cache"
**Where:** the docstring promises a warm cache — [backend/drift/llm.py:329-332](backend/drift/llm.py#L329-L332) — but only `grain_lite` has one; `ApiLLM._chat` ([llm.py:229-246](backend/drift/llm.py#L229-L246)) calls out every time.
**Problem:** doc/impl mismatch; re-runs and the stage demo pay full price (and latency) every time.
**How to fix:**
- Add a disk cache in `_chat` keyed by `hashlib.sha256((model+system+user).encode()).hexdigest()` → JSON file under `data/llm_cache/`. On hit, return cached content and **still record metered tokens** (so the cost story is real) but optionally flag `cached=True`.
- This makes the "pre-warm then serve instantly on stage" claim true and removes live-Apertus flakiness from the demo path.
**Verify:** second `run_demo.py` run makes zero network calls; tokens still reported.

### 9. 🟡 `cascade/` is an empty `.gitkeep` — the staged pipeline isn't a legible module
**Where:** `backend/cascade/` contains only `.gitkeep`. Stage-1/2/3 logic is folded into the engine + the ingest relevance filter.
**Problem:** "cost-aware staged pipeline" is the thing you *present*; partners open the dir and find nothing. Functionally fine, narratively weak.
**How to fix:** add a thin `cascade/pipeline.py` that orchestrates and labels the three stages explicitly, even if it just delegates:
- Stage-0/1: `is_candidate` ([classify.py:60](backend/drift/classify.py#L60)) + the relevance filter ([backend/ingest/relevance.py:81](backend/ingest/relevance.py#L81)) → report "% killed before any LLM."
- Stage-2: `classify_event` (cheap LLM).
- Stage-3: `interpret_risk` / `synthesize` (heavy LLM) only on a re-tier/breadth/critical alert.
- Return a `StageReport {stage0_killed, stage2_calls, stage3_calls, tokens, cost}` that the API surfaces. This is mostly wiring around existing functions; it makes the cascade demonstrable.
**Verify:** one object on screen shows the funnel: N pairs → M reach Stage-2 → K reach Stage-3.

### 10. 🟡 Escalation rate is measured but never capped
**Where:** `escalation_rate` computed ([llm.py:79-82](backend/drift/llm.py#L79-L82)); the team's own `backend/CLAUDE.md` says "hard-cap/alert on escalation %" — not implemented.
**Problem:** a drifting verifier silently pushes heavy-tier usage toward 100% and you pay for both tiers. A cap is a strong cost-governance talking point.
**How to fix:** add `MAX_ESCALATION_RATE = 0.10` to config; in `replay`'s cost block emit a boolean `escalation_breach = escalation_rate > MAX_ESCALATION_RATE` and log a warning. Optionally short-circuit Stage-3 (fall back to the static narrative) once the cap is hit within a run.
**Verify:** force-trip it with a synthetic all-heavy run; the flag flips and a warning prints.

### 11. 🟡 One LLM call per `(assertion, event)` pair repays the system prompt every time
**Where:** `classify_event` is called per pair inside the assertion×event loops — [score.py:114](backend/drift/score.py#L114).
**Problem:** the long classify system prompt ([llm.py:248-268](backend/drift/llm.py#L248-L268)) is re-sent on every pair → input-token waste and many round trips.
**How to fix:** batch — for one event, score all candidate assertions in a single call (or for one assertion, all candidate events), returning a JSON array. Mirror `grain_lite/llm_client.py::score_passages_batch`. Combine with #1 (memoize) so batches are computed once.
**Verify:** total `cheap_calls` drops to ~#events (or #assertions) instead of #pairs; verdicts unchanged.

### 14. 🟡 Cost meter has no UI widget
**Where:** numbers exist in the `cost` dict + API ([backend/api/cases.py:156](backend/api/cases.py#L156), [:183](backend/api/cases.py#L183)); STATUS.md admits "no UI widget."
**Problem:** 20% of the grade is invisible in the demo.
**How to fix:** add a small dashboard widget reading the `cost` block: cheap/heavy split (a 2-bar or donut), tokens, escalation %, and the new `cost_per_1000_alerts` + `savings_vs_frontier_pct` from #2. One component in `frontend/components/viz/`.
**Verify:** the cost numbers are on screen during the live demo.

---

## THE MODEL

### 3. 🔴 Slow structural drift is hand-authored, not real — only Meridian has a trajectory
**Where:** `compute_trajectory` only calls `embedder.from_signal_mix` — [backend/drift/trajectory.py:36-38](backend/drift/trajectory.py#L36-L38) — reading pre-authored `signal_mix` coordinates that **only Meridian's fixture has**. The `from_text` method that would embed *real* text is never called — [backend/drift/embeddings.py:37-45](backend/drift/embeddings.py#L37-L45).
**Problem:** the "embedding-trajectory wow" is, today, reading numbers a human typed. Coinbase/HashKey get no trajectory and silently fall back to event-drift only. The headline capability is demo-only.
**How to fix:**
- Derive `signal_mix` per time-window from the real event stream: bucket `EvidenceEvent`s by quarter, concatenate their `summary`/`payload` text, run `embedder.from_text(window_text)` to get per-axis density, feed that as each period's `signal_mix`.
- Build these synthetic `Snapshot`s in `client_state.py` from `state.evidence` when a customer has no authored snapshots (Coinbase/HashKey), so `compute_trajectory` works for everyone.
- Keep Meridian's authored snapshots as the clean hero case; real entities now get a *computed* trajectory.
**Verify:** Coinbase/HashKey produce a non-zero `trajectory.distance` and `moved_axes` from real events.

### 6. 🟡 Resolving/de-risking events can't move the score down
**Where:** `RISK_DIRECTION` is `+1` for everything except `source_of_wealth` — [backend/drift/config.py:50-53](backend/drift/config.py#L50-L53).
**Problem:** Coinbase's "SEC suit dismissed" lives only in the narrative; `what_would_flip` can't actually flip the number. A real risk model de-risks on resolving events.
**How to fix:**
- Let `classify_event` / `interpret_risk` emit a signed `direction` (the `RiskJudgment.risk_delta` is already signed — [llm.py:288-301](backend/drift/llm.py#L288-L301) — wire it through to the score instead of only the narrative).
- Add a small set of "resolving" event cues (dismissed, cleared, settled, withdrawn, licence granted) → negative direction for `adverse_media_status`/`regulatory_status`.
**Verify:** add a "suit dismissed" event after a "suit filed" event → Coinbase score ticks back down; `what_would_flip` text matches the score move.

### 7. 🟡 Concept axes are hardcoded to Meridian's storyline
**Where:** `CONCEPT_AXES` + `AXIS_SEEDS` are fixed to SaaS→crypto / UAE→offshore — [backend/drift/config.py:9-16](backend/drift/config.py#L9-L16).
**Problem:** the embedder can't represent drift for a customer whose story isn't Meridian's; it won't generalize on stage if asked about a 4th entity.
**How to fix:** make axes per-customer — derive seed terms from the onboarding assertions (business_model value, operating_geographies, digital_asset_policy) so each customer gets axes describing *their* baseline vs. plausible drift directions. Store on `ClientState`; `ConceptAxisEmbedder` takes them as a param instead of reading the global.
**Verify:** Coinbase axes reflect "regulated-exchange vs. unlicensed/offshore," not SaaS.

### 8. 🟡 Offline path is keyword matching; AI-quality depends on Apertus actually running
**Where:** `MockLLM.classify` is "does a drift keyword appear" — [backend/drift/llm.py:169-185](backend/drift/llm.py#L169-L185); `consistent_with_baseline` is a brittle stand-in — [llm.py:140-160](backend/drift/llm.py#L140-L160).
**Problem:** if the demo runs on the mock, the 25% AI story is keyword presence.
**How to fix:**
- Confirm `DRIFT_LLM_*` env is set so `get_llm` returns `ApiLLM` ([llm.py:339-346](backend/drift/llm.py#L339-L346)); pre-warm the cache (after #4) so it's instant + offline-safe on stage.
- Add 2-3 few-shot examples to the `classify` system prompt ([llm.py:248-268](backend/drift/llm.py#L248-L268)) to harden the real verdict (one confirms, one contradicts, one irrelevant) — improves precision on real news.
- Keep `MockLLM` strictly as the network-free CI/test fallback.
**Verify:** `smoke_apertus.py` runs the real model; tests still default to mock.

> **✅ VALIDATED prompt fix ready (Mira, Stage-2 eval — `eval/stage2/`).** Tested the REAL Apertus-8B
> `classify` on 14 curated (belief,event) pairs with gold verdicts. The SHIPPED prompt
> ([llm.py:248-268](backend/drift/llm.py#L248-L268)) is **precise but under-recalls**: recall **5–6/7**
> (wavers across runs), precision **5/5**, de-risk **2/2**. The 2 misses share one failure mode — it
> says **"confirms"** on a material *change* that doesn't *flatly* contradict the belief:
> (1) **expansion beyond scope** ("crypto spot exchange" + "rolls out equities/futures" → it said
> confirms, "still a crypto exchange"); (2) **deterioration** ("loses EU permission / MiCA rejected" →
> confirms, since the belief already said "under scrutiny"). These are exactly the silent-drift cases
> the product exists to catch. A **widened prompt** (in [eval/stage2/widened.py](eval/stage2/widened.py),
> const `WIDENED_SYSTEM`) adds three concepts — *expansion-beyond-listed-scope*, *deterioration*
> (licence lost/refused, banned, sanctioned), and an *entity/product-reference guard* (a product
> ON another firm's IPO ≠ this firm's ownership) while explicitly keeping *resolving* events
> (suit dismissed, licence granted) as `confirms`. Result over 3 runs: recall **7/7 (stable)**,
> precision **5/5**, de-risk **2/2** — a strict win, no regression. **Action:** fold `WIDENED_SYSTEM`
> into `ApiLLM.classify`. Caveat: 14 curated cases — directionally strong, small set; widen later.

### 5. 🟡 The score is calibrated to one magic number; no precision/recall proof
**Where:** `RISK_SCORE_FULL_DRIFT = 10.0` ([backend/drift/config.py:56](backend/drift/config.py#L56)) is tuned so Meridian lands ~82. `test_calibration.py` exists but there's no negative corpus.
**Problem:** you claim "stays quiet on noise" but nothing measures it; the headline number is fitted to one case.
**How to fix:**
- Build a small **labeled noise set**: benign events that should NOT move the score (Coinbase routine product launches, a clean funding round, irrelevant industry news). Assert the score stays in-band and no alert fires.
- Report precision/recall over {Meridian drift events (should fire) + noise set (should not)} in `test_calibration.py`; put the number on a slide.
- Treat `RISK_SCORE_FULL_DRIFT` as a calibration output: pick it so the noise set stays LOW *and* Meridian reaches HIGH, rather than hand-fitting to Meridian alone.
**Verify:** `pytest backend/drift/test_calibration.py` prints precision/recall; noise events fire 0 alerts.

### 12. 🟡 `RISK_SCORE_FULL_DRIFT` (and weights) hand-fitted — see #5
Covered by #5 — fold the saturation constant into the calibration so it's derived, not asserted.

### 13. 🟡 Coverage is ~6 of the brief's 10 signals — behavioral signals are thin
**Where:** only the volume envelope touches behavior — [backend/drift/classify.py:73-92](backend/drift/classify.py#L73-L92). Money-mule, structuring/layering, and dormancy-break (brief rows 2, 3, 10) need transaction data that doesn't exist.
**Problem:** a judge scanning the 10-signal table will notice the gaps.
**How to fix (pick one):**
- **Scope down honestly on stage:** "we go deep on *structural* KYC drift; transaction-pattern monitoring (mule/structuring) is the adjacent Layer-2 module" — saying it pre-empts the question.
- **Or** author a thin simulated transaction stream for one entity (Meridian) with a dormancy→spike and a structuring pattern, plus 2-3 rules in `classify.py` (velocity spike vs. dormancy baseline; many-small-inflows pattern) → covers rows 2/3/10 cheaply without real banking data.
**Verify:** either the deck explicitly scopes it, or `eval/scenarios/` has a dormancy-break test that fires.

---

### 15. 🟢 Stage-1 gate — now a KEYWORD+EMBEDDING HYBRID (gate ADOPTED); scorer re-tune is the open follow-up
**Where:** `is_candidate` — [backend/drift/classify.py:110+](backend/drift/classify.py#L110). Evals in [eval/gate/](eval/gate/): `python -m eval.gate.run` (real), `--dataset eval/gate/adversarial.json --gold eval/gate/adversarial_gold.json` (adversarial), `python -m eval.gate.calibrate` (τ curve).
**Problem:** measured against Claude-labelled real events for 4 firms (Circle/Ripple/Kraken/Revolut), the ORIGINAL keyword gate kept only **35% of MATERIAL** pairs; broadening keywords got the real set to 100% — BUT a purpose-built **adversarial set** (paraphrase / unseen-vocab / hard negatives, [eval/gate/adversarial.json](eval/gate/adversarial.json)) proved keyword-only collapses to **40% material recall**: it structurally cannot link "Cayman"→offshore, "cabinet minister"→PEP, "perpetual contracts"→derivatives (no shared token — more keywords can't fix synonymy).
**Fix (ADOPTED in classify.py):** hybrid gate — keyword/type/flag hits first (precision, $0, auditable) + never-gate `adverse_media_status`, then a **free Swiss-sovereign embedding backstop** (`SwissAIEmbedder`, arctic-embed-v2 on CSCS, same key as the LLM) when keywords are silent. Belief is expanded into a rich **`query:`-prefixed** embedding query (GRAIN's `build_rich_query` trick) via per-predicate `SEMANTIC_HINTS` natural-language drift descriptions; cosine ≥ `SEMANTIC_COSINE_MIN=0.24` (calibrated on the curve). Degrades to the lexical overlap if the endpoint is down (CI/offline still runs).
**Hybrid gate eval (shipped, τ=0.24):**

| set | keyword-only material recall | **hybrid material recall** | pass-rate |
|---|---|---|---|
| REAL (4 firms) | 100% | **100%** | 42% |
| ADVERSARIAL (paraphrase/synonym) | **40%** | **87%** | 34% |

Recovered the offshore-re-domicile, PEP-by-title, tokenised-treasury and business-pivot misses; the `query:`+`SEMANTIC_HINTS` bridge lifted PEP 0.21→0.32 and UBO 0.22→0.45 while hard negatives stayed ~0.03–0.12. Remaining adversarial miss: an undisclosed-derivatives event (product_mix cosine 0.237 — caught at τ=0.22; its 2-hop regulatory angle is below any safe threshold and left to Stage-2). Embedding adds ~2 marginal hard-negative FPs vs keyword-only — the bulk of FPs are pre-existing keyword over-triggers + the `adverse_media` never-gate (both cheap-LLM-filtered).
**Real-model validation (Apertus, before→after gate, memoized engine):**

| | Apertus old gate | Apertus new gate | |
|---|---|---|---|
| Meridian | 97 HIGH | 98 HIGH | ✅ safe |
| Coinbase | 62 MEDIUM | 65 MEDIUM | ✅ safe |
| HashKey | 65 MEDIUM | **75 HIGH** | ❌ flips — feeds ~3× more of its 55 events to the scorer |

NB: Meridian is **97 on Apertus vs its "designed" 82** even with the OLD gate → the demo's fixed numbers are **MockLLM-calibrated; Apertus runs hotter**. (Coinbase/HashKey old-gate ≈ designed, so they were closer.)
**Follow-up = scorer re-calibration (this item, Miguel's lane):** the filter is the product goal and is adopted; the band is a downstream knob. Re-tune so **HashKey returns to MEDIUM on Apertus** while Meridian stays HIGH / Coinbase MEDIUM. Targets (Apertus, improved gate): **HashKey 75 → ≤66**, **Meridian keep ≥67** (currently 98 — lots of room), **Coinbase keep ≤66** (65). Likely `RISK_SCORE_FULL_DRIFT` up ~15–20% (watch the Meridian floor) and/or per-predicate weights; couples with #5/#12. **Validate on Apertus, NOT MockLLM** — the mock over-escalates (it also reds 4 drift tests: `test_coinbase_stays_medium`, `test_coinbase_fires_within_band_alert`, `test_meridian_flips_coinbase_does_not`, `test_no_premature_adverse_media`) until calibrated.
**⤷ UPDATE (hybrid embedding gate now shipped):** the recall-first hybrid feeds even MORE signal to the scorer, so the mismatch grew — MockLLM now scores **Coinbase 83/HIGH** (target ≤66) and **Meridian 100/HIGH** (saturated). Same 4 tests red, **no new failures** vs the keyword-broadening state — confirming this is purely the scorer-calibration gap, not a gate regression. Re-calibration (couples with #5/#12) is now the single thing standing between "best-in-class gate" and a green, on-band demo. Re-measure the Apertus bands with the hybrid gate before tuning.
**Verify:** `python -m eval.gate.run` = 100% material recall; the 3 demo cases keep their designed bands **on Apertus**; the 4 drift tests green.

---

## Suggested execution order (48h-aware)
1. **Cost quick wins first** (~~#1 memoize ✅~~, #4 cache, #2 $/1k) — low risk, directly buys the 20% Cost axis and makes every later real-Apertus run cheap.
2. **Real trajectory** (#3) + **per-customer axes** (#7) — turns the headline from scripted to real.
3. **Calibration + noise corpus** (#5/#12) and **signed direction** (#6) — proves discipline, not just drama.
4. **Cascade module** (#9) + **cost UI** (#14) + **escalation cap** (#10) — makes the cost story visible and presentable.
5. **Prompt hardening** (#8), **batching** (#11), **signal coverage** (#13) — polish.

> Honesty rule (from CLAUDE.md): mark anything still mocked in the README. These fixes mostly
> *remove* mocks (real trajectory, real $) — keep STATUS.md updated as each lands.
