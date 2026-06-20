# CLAUDE.md — `frontend/` · OWNER: Giacomo (Domain & Product)

> Read the root `/CLAUDE.md` first. This is **Giacomo's lane.** Don't edit `backend/drift/`
> (Miguel) or `backend/` services (Mira) — consume their outputs via the API + `shared/schemas/`.

## 🚩 FIRST TASK (before building the UI)
Help decide the schemas (see root `/CLAUDE.md` §0 + `shared/schemas/README.md`). **Your angle:**
- The two base-case profiles are authored: `data/customers/coinbase.json` (real, citable) and
  `data/customers/meridian-sands.json` (the drift hero). The `Assertion` shape now carries the
  full RM field set (source-of-wealth/funds, PEP/sanctions/adverse-media, digital-asset policy,
  0–100 `risk_score`).
- `eval/scenarios/{coinbase,meridian}-drift.example.json` answer **Q3.1** with ONE alert per
  customer aggregating contradictions (the cleaner screen) — confirm at kickoff.
- Verify the Coinbase facts flagged VERIFY (CIK/LEI/licences); Meridian is fully simulated.
Bring these to the kickoff. Don't build screens until the `DriftAlert` shape is agreed.

## Your mission
You're the ex-KYC relationship manager — your edge is **authenticity**. Make the system look and
feel like a tool a real bank compliance/AML analyst would trust. You own the **20% UX &
Explainability** axis and co-own **20% Compliance** (the human-facing governance surface).

## What you build
1. **Analyst dashboard** (the demo *is* this screen):
   - Customer list ranked by drift / risk-tier change (green→amber→red).
   - **Onboarding-twin vs. live-twin diff** — the authored KYC profile vs. what public data says
     now, with contradicted assertions lit red.
   - **Evidence timeline** per alert — the chain of public events, each with a **clickable source
     citation** (no claim without a source).
   - **"What would flip this decision"** panel (contestability).
   - **HITL approval queue** — approve / override / escalate → writes to the audit log.
   - **Cost meter** widget (consume the cascade's token/$ + escalation-rate numbers from Mira).
2. **Layer 2 data** (`data/customers/`): author the **baseline KYC profile** for our demo
   company as a set of `Assertion`s — expected business model, activity/volumes, ownership,
   domicile, risk tier. Make it *believably real* (your KYC experience is the moat here).
3. **`pitch/`**: the `.pptx` deck (problem / solution / work-done), the 3-min script, Q&A prep.
4. **`eval/scenarios/`** (with Miguel): write each of the 10 use cases as a business scenario
   (signal → expected flag → recommended action) in real compliance language.

## Contracts you depend on (don't redefine — read `shared/schemas/`)
- You **render** `DriftAlert` (from Miguel) and read `Assertion` + `AuditEntry`.
- You **author** `Assertion` instances for `data/customers/` (Giacomo is the source of truth on
  what fields a real KYC profile has — flag Miguel/Mira if the schema needs a field).

## Don't
- Don't invent risk scores in the UI — display what the engine returns + its rationale/citations.
- Don't fake the audit log or HITL in the demo — wire them to the real `govern/` endpoints.

## 🏛️ Governance backend contract (wire your HITL to this — it's now REAL)
`backend/govern/` + the API now provide a real, immutable, hash-chained audit log. **The HITL in
`components/profile/client-section.tsx` is currently FAKED** (`dispose()` = local state + a toast).
That's the one thing the brief says never to fake — swap it to the real endpoints:

1. **Replace `dispose(label)`** with a POST:
   `POST /alerts/{alert_id}/decision` body `{ action, reviewer, note }`
   - your buttons → `action`: **Approve→`approve`** · **Override→`override`** · **Escalate → Re-KYC→`escalate`**
   - send `reviewer` (e.g. "G. Cozzio"); the server stamps model/policy version + timestamp + hashes
   - response = the updated `DriftAlert` (its `governance_state` now persists across refreshes)
2. **Render the real trail** from `GET /audit?customer_id=…&alert_id=…` (instead of the toast text).
   Optional: `GET /audit/verify` → show a ✅ "tamper-evident / chain intact" badge (compliance flourish).
3. **RBAC is server-side**: the API may reject an action for the role (e.g. closing a HIGH re-tier
   needs MLRO — four-eyes). Surface the 403 reason ("requires MLRO sign-off") rather than failing silently.

Until the backend is running you can keep the local mock, but **the demo must hit the real endpoints**
(fixtures mode = local mock; `NEXT_PUBLIC_DATA_MODE=live` = real govern). Audit shape = `AuditEntry`
in `shared/schemas/audit.py`.

## Pitch lines that are yours to deliver
"Banks look in the rearview mirror." · "The moment perception and reality separate, risk begins."
· Lead with the *contradicted-assertion* story, not a generic news alert.
