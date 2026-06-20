"""Stage-2 prompt prototype — does a WIDENED verdict prompt close the recall gap (5/7 -> ?) WITHOUT
breaking precision (5/5) or de-risking (2/2)?

Runs the REAL Apertus-8B on the same 14 cases with BOTH the current prompt (classify_event) and a
widened prompt that adds two missing concepts: (1) EXPANSION beyond the on-file scope and
(2) DETERIORATION (licence lost/refused, banned, sanctioned) — while keeping RESOLVING events as
confirms and wrong-entity / product-references as irrelevant. Does NOT edit backend/drift/llm.py.

  DRIFT_LLM_MOCK=  PYTHONPATH=. python -m eval.stage2.widened
"""
from __future__ import annotations
import os
os.environ.pop("DRIFT_LLM_MOCK", None)

from backend.drift.llm import get_llm, Verdict, _parse_json
from backend.drift.classify import classify_event, anti_hallucination_gate
from eval.stage2.run import CASES, mk

WIDENED_SYSTEM = (
    "You are a KYC drift detector for a regulated bank. Compare the EVIDENCE against the on-file "
    "BELIEF (a specific KYC value about THIS entity) and classify their relationship. Judge against "
    "the SPECIFIC belief value and THIS entity — not the topic in general.\n"
    "contradicts — the entity's reality now DEVIATES FROM or EXCEEDS the on-file belief in a "
    "risk-relevant way. This INCLUDES:\n"
    "  • EXPANSION beyond the listed scope: the belief is a CLOSED scope and the evidence shows a NEW "
    "activity/product/market NOT in it — e.g. belief 'crypto spot exchange; no futures, no equities' + "
    "'rolls out US stocks and ETFs' or 'enters US futures' -> contradicts (the business now exceeds "
    "its KYC profile), and 'B2B SaaS, no crypto' + 'launches a crypto brokerage' -> contradicts;\n"
    "  • DETERIORATION: loses or is REFUSED a licence, is banned/forced out of a market, is fined or "
    "sanctioned, or faces a new investigation/violation — e.g. 'EU-registered' OR EVEN 'under "
    "regulatory scrutiny' + 'MiCA licence rejected / loses permission to operate in the EU' -> "
    "contradicts (the situation MATERIALLY WORSENED);\n"
    "  • a new owner with a significant stake, a new jurisdiction, an ownership/control change.\n"
    "confirms — the evidence is FULLY within what the belief already states AND adds no new risk: a "
    "product squarely inside the listed scope, OR a RESOLVING / IMPROVING event (lawsuit dismissed, "
    "charges dropped, licence GRANTED, cleared). GOOD NEWS must NOT be flagged as a contradiction.\n"
    "irrelevant — no bearing on THIS belief or THIS entity: news about a DIFFERENT company (even if "
    "this entity merely offers a product referencing it — e.g. 'launches futures on SpaceX's IPO' does "
    "NOT change THIS entity's ownership), wrong-entity name matches, generic market commentary, or "
    "price/analyst notes. ambiguous — genuinely unclear.\n"
    "Reply with ONLY one JSON object and nothing else: "
    '{"verdict":"confirms|contradicts|irrelevant|ambiguous","strength":0.0-1.0,'
    '"evidence_quote":"<short phrase copied WORD-FOR-WORD from the EVIDENCE text only>",'
    '"rationale":"<1-2 sentences; do NOT put the quote here>"}. '
    'If verdict is "contradicts", evidence_quote MUST be a non-empty phrase taken verbatim from the '
    "EVIDENCE summary or payload."
)


def classify_widened(a, e, llm) -> Verdict:
    user = (f"BELIEF: predicate={a.predicate.value}; value={a.value}\n"
            f"EVIDENCE: type={e.type.value}; summary={e.summary}; payload={e.payload}")
    try:
        obj = _parse_json(llm._chat(llm.cheap_model, WIDENED_SYSTEM, user, "cheap"))
        v = Verdict(str(obj.get("verdict", "ambiguous")), float(obj.get("strength") or 0.0),
                    str(obj.get("rationale", "")), str(obj.get("evidence_quote", "")))
    except Exception:
        v = llm.classify(a, e)
    return anti_hallucination_gate(v, e)


def tally(label, verdicts):
    catch = miss = fp = overflag = nc = ni = nd = 0
    for (pred, val, summ, gold, note), v in zip(CASES, verdicts):
        vv = v.verdict
        if gold == "contradicts":
            nc += 1; catch += (vv == "contradicts"); miss += (vv != "contradicts")
        elif gold == "irrelevant":
            ni += 1; fp += (vv == "contradicts")
        else:
            nd += 1; overflag += (vv == "contradicts")
    print(f"\n{label}:  recall {catch}/{nc}   precision {ni-fp}/{ni} (false-pos {fp})   "
          f"de-risk {nd-overflag}/{nd} ok (over-flag {overflag})")
    return catch, nc


def main():
    llm = get_llm()
    print(f"LLM: {type(llm).__name__}  (current prompt vs WIDENED prompt, same 14 cases)\n" + "=" * 96)
    cur, wid = [], []
    for pred, val, summ, gold, note in CASES:
        a, e = mk(pred, val, summ)
        c = classify_event(a, e, llm)
        w = classify_widened(a, e, llm)
        cur.append(c); wid.append(w)
        flag = "  <-- CHANGED" if c.verdict != w.verdict else ""
        mark = {"contradicts": "C", "confirms": "=", "irrelevant": "·", "ambiguous": "?"}
        print(f"gold={gold:15s} cur={mark.get(c.verdict,'?')}={c.verdict:11s} "
              f"wid={mark.get(w.verdict,'?')}={w.verdict:11s}{flag}")
        print(f"   {pred}: {summ[:78]}")
    print("=" * 96)
    tally("CURRENT", cur)
    tally("WIDENED", wid)


if __name__ == "__main__":
    main()
