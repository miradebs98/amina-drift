# 🚩 schemas — the team's FIRST and MOST IMPORTANT decision

> **Read this before writing any feature code.** The three schemas here are the *contracts* that
> let three people build three pieces in parallel and have them snap together. Get them right →
> smooth handoffs. Get them wrong → everyone reworks on Sunday. So we **reason them through
> together first** (~1 hour, all three founders), using the GenTwo worked example as the test case.

## What's here
- `assertion.py` / `evidence.py` / `alert.py` / `audit.py` — a **DRAFT proposal** to react to, not gospel.
- The GenTwo example is already filled in against this draft, split across the three lanes:
  - **Assertions** (Giacomo's input):   `data/customers/gentwo-ag.json`
  - **EvidenceEvents** (Mira's output): `data/fixtures/gentwo-events.example.json`
  - **DriftAlert** (Miguel's output):   `eval/scenarios/gentwo-drift.example.json`
- Open the three files side by side — that *is* the whole product in three steps.

## The one principle
A schema is just **the agreed shape of the data passed between people.** It is NOT real logic —
it's a handshake. Once agreed, each of you mocks the others' data in that shape and builds alone.
**The point of doing it first is parallelism.** Don't over-design it; design just enough that the
GenTwo example flows cleanly from belief → evidence → alert → screen.

---

## The kickoff session: decide these, write the answers in the Decision Log below

Each schema has a few real design choices. For each: the question, the options, and a recommended
default to argue against. **Make GenTwo concrete as you go** — if a choice doesn't change how the
GenTwo example looks, it doesn't matter yet; skip it.

### 1. `Assertion` (Giacomo's lane — what the bank believes)
- **Q1.1 — Granularity of a multi-part fact.** Is `UBO` one assertion holding a structure
  (`{Alice: 55%, Bob: 45%}`), or one assertion per owner? → *Default: one assertion, structured
  value (simpler to author; Miguel diffs inside it).*
- **Q1.2 — Categorical facts vs behavioural envelopes.** `business_model = "SaaS"` is a value that
  gets *contradicted*; `monthly_volume ∈ [50k,2M]` is a range that gets *breached*. Same schema
  (with optional `expected_envelope`) or two schemas? → *Default: one schema, optional envelope.*
- **Q1.3 — Predicate list.** Which attributes do we actually monitor? (business_model, domicile,
  ubo, geographies, product_mix, risk_tier…) Do we need `operating_geographies` separate from
  `counterparty_geographies`? → *Default: a small fixed enum; add only what the demo needs.*
- **Q1.4 — The "belief clock".** Keep both `as_of` and `last_verified`? (Miguel needs
  `last_verified` for staleness/confidence-decay.) → *Default: keep both.*
- **Q1.5 — Importance weight?** Do some assertions matter more for the risk score (sanctions ≫
  domain)? → *Default: skip a weight field for now; Miguel can hardcode per-predicate weights.*

### 2. `EvidenceEvent` / `Snapshot` (Mira's lane — public signals)
- **Q2.1 — ⭐ THE BIG ONE: how is SLOW drift detected?** Two models:
  - **(a) Events only** — slow drift = a *sequence of `EvidenceEvent`s* accumulating over time.
  - **(b) Events + Snapshots** — connectors also emit periodic `Snapshot`s (the entity's full
    public profile at time T), and Miguel diffs consecutive snapshots / tracks an embedding
    trajectory.
  → *This decides whether `Snapshot` is a core schema. Default: support both, but the DEMO can run
  on events alone if time is short. Decide how much Snapshot we commit to.*
- **Q2.2 — Heterogeneous payloads.** A news article, a registry diff, and a sanctions hit look
  nothing alike. Keep a free-form `payload: dict` + a few typed common fields? → *Default: yes,
  thin typed envelope + free `payload`.*
- **Q2.3 — Who links evidence → assertion?** Does Mira's connector guess which assertion an event
  bears on, or does Miguel's engine decide? → *Default: connectors stay DUMB (just emit facts);
  Miguel's engine owns the matching. Keeps lanes clean.*
- **Q2.4 — Two timestamps.** `published_at` (when the world changed) vs `ingested_at` (when we
  fetched it). Both? → *Default: keep `published_at` (drives drift timing); add `ingested_at` only
  if needed.*
- **Q2.5 — Entity resolution fields.** How do we mark "we think this is customer X, confidence Y"
  and handle unresolved events? → *Default: `customer_id` nullable + `resolution_confidence`.*

### 3. `DriftAlert` (Miguel's lane — the mismatch the screen shows)
- **Q3.1 — ⭐ Alert granularity.** One alert per contradicted assertion, or ONE alert per customer
  aggregating several contradictions? (UX vs precision — Giacomo's screen depends on this.) →
  *Default: one alert per customer "drift episode," listing the contradicted assertions + evidence.*
- **Q3.2 — Score: single number vs breakdown.** Explainability wants per-factor contributions, not
  just `0.62`. Embed a `factors[]` breakdown? → *Default: keep `drift_score` + a short factor list.*
- **Q3.3 — Required explainability fields.** Lock that NO alert ships without `rationale`,
  `evidence_ids` (each with a source_url), and `recommended_action`. → *Default: required, enforced.*
- **Q3.4 — Where does governance state live?** Current state (`pending/approved/…`) on the alert,
  full history in `AuditEntry`? → *Default: current state on alert, immutable history in audit log.*

---

## Definition of done for the kickoff
✅ The 3 shapes are agreed and the open questions above have answers in the Decision Log.
✅ The GenTwo example files validate against the agreed shapes (belief → evidence → alert flows).
✅ Everyone can now go to their own lane and build against mocked data in these shapes.

After this, **don't change a schema without pinging the other two** — it's the one thing that
breaks all three lanes at once.

---

## Decision Log (fill in at kickoff — keep it short)
> Date: ____   Present: Giacomo / Mira / Miguel

- Q1.1 UBO granularity: ____
- Q1.2 envelope approach: ____
- Q1.3 predicate enum (final list): ____
- Q2.1 **slow-drift model (events only / + snapshots)**: ____
- Q2.3 evidence→assertion matching owner: ____
- Q3.1 **alert granularity (per-assertion / per-customer)**: ____
- Other: ____
