# CLAUDE.md — amina-drift (SwissHacks 2026 · Challenge 4 · AMINA Bank)

> **This file is the team's shared brain.** Every founder's Claude agent/chat loads it.
> Read it before doing anything. Per-lane `CLAUDE.md` files in `frontend/`, `backend/`, and
> `backend/drift/` give each owner their scoped context. **Stay in your lane; respect the
> contracts in `shared/schemas/`.**

---

## 1. What we are building (the goal — keep this fixed)

A **Dynamic Risk Profiling System** that catches **KYC Drift**: the slow, structural divergence
between what the bank believes about a customer (their onboarding KYC profile) and what's
actually true now — detected by fusing **real-time public intelligence** with a **simulated
internal KYC profile**, cheaply, with auditable evidence and a human in the loop.

**The wedge (say this on stage):** *Everyone else makes onboarding faster or rescreens more
often. We catch the moment a **specific on-file KYC assertion** (UBO = X · business = SaaS ·
domicile = CH) is **contradicted by public events** — with the evidence, cheaply, routed to the
right team.*

**AMINA's own framing — echo it:** *"Banks are looking in the rearview mirror."* · *"Can AI be
an early-warning system that notices the signals before humans do?"* · *"The moment perception
and reality separate, risk begins."*

### The core idea, technically
A KYC profile is **not a document — it's a set of dated, sourced, testable assertions.** Drift
detection = continuously re-validating each assertion against an evidence stream.
- **Event drift** (discrete, high-precision, cheap): one public event contradicts one assertion
  (new director in ZEFIX → UBO assertion false; sanctions hit → risk_tier false).
- **Slow structural drift** (the *headline*, the hard part): no single event invalidates anything;
  the company's public profile *trajectory* migrates over months (SaaS → crypto). Detected by
  **snapshot-and-diff over time** + confidence decay / embedding trajectory / change-point.

## 2. How we're judged (build to these weights)
| Criterion | Weight | Primary owner |
|---|---|---|
| AI Intelligence Quality (accurate flags, strong reasoning) | **25%** | **Miguel** (drift engine) |
| Cost Efficiency (staged pipeline, token/$ instrumentation) | **20%** | **Mira** (cascade) |
| UX & Explainability (clear alerts, intuitive UI, readable why) | **20%** | **Giacomo** (UI) |
| Compliance & Safety (HITL, audit, citations, data separation) | **20%** | **Mira** + **Giacomo** |
| Engineering & Architecture (modular, scalable, robust) | **15%** | **Mira** |

> Cost + UX + Compliance = **60%** and are mostly *engineering discipline + presentation*, not
> AI magic. That's where a focused team wins. **Cost Efficiency (20%) is the one most teams skip.**

## 3. Hard requirements (from the official brief — all must be visible in the demo)
1. **Two layers, in order.** Layer 1 = public intelligence (PRIMARY). Layer 2 = *simulated*
   internal KYC for **one real public company/startup** we pick and author ourselves.
2. **KYC Drift Detection** is the headline — show a customer that onboarded LOW and silently
   drifted to HIGH via a chain of public events.
3. **Cost-aware cascade.** Stage 1 cheap filter (rules/embeddings/small model) → Stage 2 LLM
   reasoning for high-risk only → Stage 3 deep analysis on escalation. **Track tokens/workflow,
   estimate cost per 1,000 alerts, show where light vs. heavy models run.**
4. **3-layer governance — graded, not garnish:**
   - Data Security: public/internal separation, RBAC, masking, **audit log**.
   - Model Guardrails: **HITL**, explainability, confidence scores, **source citations**,
     hallucination checks.
   - Decision Governance: approval workflow, escalation, checkpoints.

> **NEVER fake the audit log or the human-in-the-loop step.** Fake other things if time-pressed,
> and **mark anything mocked in the README** (partners read the code; honesty scores, fake
> completeness doesn't).

## 4. Ownership map — stay in your lane

| Lane | Owner | Directories | Builds |
|---|---|---|---|
| **Domain & Product** | **Giacomo** (ex-KYC RM) | `frontend/` · `data/customers/` · `pitch/` · `eval/scenarios/`* | Authored KYC profile, analyst dashboard, deck, demo script, real compliance language. **Primary presenter.** |
| **Data & Integration** | **Mira** (data science, full-stack glue) | `backend/ingest/` · `backend/resolve/` · `backend/cascade/` · `backend/govern/` · `backend/api/` · `data/snapshots/` · `data/fixtures/` | Layer-1 connectors, entity resolution, cost cascade + token meter, audit log + RBAC + data separation, FastAPI. |
| **Drift Modelling** | **Miguel** (modelling) | `backend/drift/` · `eval/scenarios/`* | The assertion-diff engine, slow-structural drift detection, drift score + re-tiering, Stage-2 LLM verdict prompt. **The "wow."** |
| **Shared contract** | **ALL THREE** | `shared/schemas/` | The 3 data contracts. Changing one **requires a heads-up to the other two** — it can break everyone. |

\* `eval/scenarios/` is co-owned: Giacomo writes the business scenario (signal→flag→action),
Miguel turns it into a runnable test.

**Rule of thumb:** if a file isn't in your lane, don't edit it without a ping. Touching
`shared/schemas/` = announce it first.

## 5. The 3 contracts (lock Friday night, then everyone parallelizes)
Defined in `shared/schemas/`. After these are frozen, each person mocks the others' outputs and
builds independently:
1. **`Assertion`** — what the bank believes. *Giacomo defines fields from real KYC; Miguel/Mira
   freeze the format.* The spine of the system.
2. **`EvidenceEvent`** / **`Snapshot`** — what a connector emits. *Mira produces → Miguel consumes.*
3. **`DriftAlert`** — a detected drift. *Miguel produces → Giacomo's UI renders.*
4. **`AuditEntry`** — append-only decision log. *Mira owns; everyone writes through it.*

## 6. The pipeline (data flow — how the lanes connect)
```
[Layer 1: ingest/]  GDELT · News RSS · GLEIF · ZEFIX · yente/OpenSanctions · Wayback
        │ EvidenceEvent / Snapshot
        ▼
[resolve/]  entity resolution: is this event actually our customer?  (confidence-gated)
        │
        ▼
[Layer 2: data/customers/]  authored KYC profile = set of Assertions  (Giacomo)
        │  fuse
        ▼
[drift/]  assertion-diff (event drift) + snapshot trajectory (slow drift) → DriftAlert  (Miguel)
        │
        ▼
[cascade/]  Stage 1 cheap gate → Stage 2 LLM verdict → Stage 3 deep; token/$ meter  (Mira)
        │
        ▼
[govern/]  HITL approve/override/escalate → AuditEntry (immutable)  (Mira)
        │
        ▼
[frontend/]  analyst dashboard: alerts, onboarding-twin vs live-twin diff, evidence timeline,
             "what would flip this," cost meter, approval queue  (Giacomo)
```

## 7. Stack (standalone build — no external code dependency)
- **Backend:** Python 3.11 + FastAPI; SQLite (customers + audit log = append-only table).
- **LLM cascade:** cheap tier (small/fast model) → heavy tier (frontier model) on escalation.
  Instrument the **escalation rate** — a drifting verifier silently pushes it toward 100% and you
  pay for both tiers. Hand-rolled confidence threshold is fine and *easier to explain on stage*.
  (Optional Swiss-sovereignty angle: **Apertus** as the cheap tier — verify access Sat 10:00.)
- **Frontend:** Giacomo's call (keep it simple + clean; the dashboard *is* the demo).
- **Data:** prefer free/no-auth first — GDELT, Google News RSS, GLEIF, ZEFIX, Wayback CDX,
  OpenSanctions/yente. **Cache responses into `data/fixtures/` so the demo runs offline.**

## 8. Demo discipline
- **One real company** with a *demonstrable drift story* (business-model pivot or ownership/
  jurisdiction move). Author its baseline KYC profile in `data/customers/`.
- Slow drift needs time → pre-build a **time-compressed snapshot timeline** in `data/snapshots/`
  so months of drift replay in ~30 seconds.
- The graded guardrails (audit log, HITL, citations, data separation) must be **shown live**.
- **Integrate end-to-end on ONE scenario by Saturday evening** — not Sunday morning.

## 9. Pitch guardrails — do NOT over-claim (these were adversarially refuted)
- ❌ Don't say incumbents (Fenergo etc.) *can't* do role-based delivery (reframe as the *silo
  problem* + our delivery quality).
- ❌ Don't call FINMA "purely reactive." ❌ Don't cite "pKYC cuts workload 90%."
- ⚠️ The 85–95% false-positive band and "70% FP reduction" are **vendor figures** — attribute
  them, don't state as fact.
- ✅ Do lean on verified facts: KYC reviews take 61–150 days for 52% of cases; general-purpose
  LLMs are disqualified as final compliance deciders (hallucination) → grounded, cited evidence +
  HITL is a *necessity*, not a nice-to-have.

## 10. Submission (Sunday 21 June, 12:00 noon — ONE shot)
- Short description · team photo · **pitch deck `.pptx` 16:9, fonts embedded** (problem / solution
  / work done) · **code repo + clean README** (state what's real vs mocked) · check Amina GitHub
  for partner extras · demo link.
- **13:30: 3-min pitch + 3-min Q&A** — slides AND live demo. Giacomo presents; Miguel fields
  "how does the model work"; Mira fields architecture/cost.
- Pre-submission: `main` runnable, README honest, demo works on a phone hotspot, deck exports
  cleanly. **Submit once, well before noon.**

## 11. Working rules (48h, 3 people)
- `main` stays runnable. Short-lived branches, small PRs, **integrate often** — no 2-day branches.
- Secrets in `.env` (git-ignored); never commit keys. Keep `data/fixtures/` for offline demo.
- Daily sync points: **Sat 09:00** (kickoff/contracts check), **Sat 18:00** (first integration),
  **Sun 09:00** (freeze plan).
- When you finish a lane milestone, update this file's status or ping the others — don't let the
  shared picture drift.
