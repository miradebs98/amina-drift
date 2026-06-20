"""Stage-1 gate evaluation — REAL `is_candidate` rules vs Claude's gold labels. NO API CALLS.

Scores the cost-cascade's cheap filter: for every (belief, event) pair, does the gate KEEP what a
competent analyst would re-examine (recall) without waving through junk (precision)? Recall is the
one that matters — a dropped pair is a signal that never reaches the LLM = silent risk.

  python -m eval.gate.run            # compare CURRENT gate vs IMPROVED variants
  python -m eval.gate.run --misses   # also print every recall miss (the dangerous drops)

The IMPROVED variants are defined HERE so thresholds can be tuned without touching the engine;
the winning logic is then ported into backend/drift/classify.py and re-confirmed.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from shared.schemas import Assertion, EvidenceEvent
from backend.drift.classify import is_candidate as gate_current, PREDICATE_SIGNALS

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "dataset.json").read_text())
GOLD = json.loads((HERE / "gold.json").read_text())["labels"]


def _load(dataset: str | None, gold: str | None) -> None:
    """Point the harness at a (dataset, gold) pair — e.g. the adversarial set. Passing None resets to
    the default real set (so callers can switch back and forth without state leaking between sets)."""
    global DATA, GOLD
    DATA = json.loads(Path(dataset or (HERE / "dataset.json")).read_text())
    GOLD = json.loads(Path(gold or (HERE / "gold.json")).read_text())["labels"]

CRITICAL = {"sanctions_status", "pep_status", "adverse_media_status"}

# ── build real schema objects from the frozen dataset ───────────────────────
def build(company: dict):
    cid = company["id"]
    assertions = []
    for pred, val in company["beliefs"].items():
        env = None
        if isinstance(val, dict):
            env = {"allowed_set": val.get("allowed_set"), "unit": "country"}
            val = val["value"]
        assertions.append(Assertion(
            id=f"{cid}-{pred}", customer_id=cid, predicate=pred, value=val,
            expected_envelope=env, as_of=date(2023, 1, 1), last_verified=date(2023, 1, 1),
            source="onboarding (eval)", confidence=0.9, status="valid",
        ))
    events = []
    for ev in company["events"]:
        events.append(EvidenceEvent(
            id=ev["id"], entity_ref=company["legal_name"], customer_id=cid,
            type=ev["type"], summary=ev["summary"], payload=ev.get("payload", {}),
            source=ev["source"], source_url=ev["url"], published_at=ev["date"] + "T00:00:00Z",
            confidence=0.8,
        ))
    return assertions, events

# ── IMPROVED gate logic (tuned here, then ported to classify.py) ────────────
# 1. listing_status was entirely absent from PREDICATE_SIGNALS → always dropped. Add it.
# 2. broaden a few keyword lists with the words real news actually uses (data-driven from misses).
SIGNALS2 = {k: {kk: list(vv) for kk, vv in v.items()} for k, v in PREDICATE_SIGNALS.items()}
SIGNALS2["listing_status"] = {"kw": ["ipo", "public", "listing", "listed", "nyse", "nasdaq",
                                     "stock exchange", "go public", "goes public", "s-1", "flotation", "delist"]}
SIGNALS2["operating_geographies"]["kw"] += ["expand", "expanding", "eu", "europe", "european",
                                            "international", "overseas", "abroad", "cross-border", "global", "market"]
SIGNALS2["regulatory_status"]["kw"] += ["bank", "charter", "occ", "fca", "pra", "sec", "cftc", "fcm",
                                        "approval", "supervis", "sandbox", "genius act", "mica", "emi", "trust bank"]
SIGNALS2["product_mix"]["kw"] += ["futures", "equit", "stock", "etf", "stablecoin", "treasury",
                                  "prime brok", "clearing", "deposit", "settlement", "payments"]
SIGNALS2["business_model"]["kw"] += ["bank", "acquire", "acquisition", "expand", "pivot", "multi-asset"]
SIGNALS2["adverse_media_status"]["kw"] += ["fine", "fined", "penalty", "settlement", "settle", "sued",
                                           "lawsuit", "aml", "compliance failure", "sanction", "money laundering"]
SIGNALS2["sanctions_status"]["kw"] += ["aml", "money laundering", "financial crime"]
SIGNALS2["source_of_wealth"]["kw"] += ["valuation", "profit", "revenue", "acquire", "acquisition"]
# inbound ownership: a funding round or IPO brings a new (possibly >25%) holder → re-screen UBO
SIGNALS2["ubo"]["types"] = list(set(SIGNALS2["ubo"].get("types", []) + ["funding"]))
SIGNALS2["ubo"]["kw"] += ["ipo", "goes public", "public offering", "new investor", "lead investor"]

_STOP = set("the a an and or of to in for with on at by from is are be as not no into its their our "
            "via using under over more most new only both global company group ltd inc llc plc nv sa "
            "than after before year years per up down out off it this that these those will would".split())

def _stem(w: str) -> str:
    for suf in ("ization", "isation", "ations", "ation", "ing", "ised", "ized", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w

def _content(s: str) -> set[str]:
    toks = re.sub(r"[^a-z0-9]+", " ", s.lower()).split()
    return {_stem(t) for t in toks if len(t) > 2 and t not in _STOP}

def _kw_hit(signals, a, e) -> bool:
    sig = signals.get(a.predicate.value)
    if not sig:
        return False
    text = f"{e.summary} {e.payload}".lower()
    if any(e.payload.get(f) for f in sig.get("payload_flags", [])):
        return True
    if e.type.value in sig.get("types", []):
        return True
    return any(kw in text for kw in sig.get("kw", []))

def _semantic(a, e) -> int:
    belief = _content(a.predicate.value.replace("_", " ") + " " + a.value)
    return len(belief & _content(e.summary))

def gate_improved(a, e, never_gate=("adverse_media_status",), sem_min=2) -> bool:
    pred = a.predicate.value
    if pred in never_gate:                  # critical, news-driven → never filter out
        return True
    if _kw_hit(SIGNALS2, a, e):             # broadened keyword / type / flag
        return True
    if _semantic(a, e) >= sem_min:          # generous lexical-semantic backstop (stemmed overlap)
        return True
    return False

# ── scoring ─────────────────────────────────────────────────────────────────
def score(gate):
    tp = fp = fn = passed = total = 0
    mat_total = mat_kept = 0                # MATERIAL pairs (the ones that move the risk profile)
    per_pred: dict[str, list[int]] = {}   # pred -> [tp, fn]
    misses, mat_misses = [], []
    for company in DATA["companies"]:
        assertions, events = build(company)
        for e in events:
            gold = set(GOLD[e.id]["relevant"])
            material = set(GOLD[e.id]["material"])
            for a in assertions:
                pred = a.predicate.value
                keep = gate(a, e)
                rel = pred in gold
                total += 1
                passed += int(keep)
                per_pred.setdefault(pred, [0, 0])
                if pred in material:
                    mat_total += 1
                    mat_kept += int(keep)
                    if not keep:
                        mat_misses.append((e.id, pred, e.summary))
                if keep and rel:
                    tp += 1; per_pred[pred][0] += 1
                elif keep and not rel:
                    fp += 1
                elif (not keep) and rel:
                    fn += 1; per_pred[pred][1] += 1
                    misses.append((e.id, pred, e.summary))
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    mat_recall = mat_kept / mat_total if mat_total else 1.0
    return {"recall": recall, "precision": precision, "tp": tp, "fp": fp, "fn": fn,
            "mat_recall": mat_recall, "mat_total": mat_total, "mat_kept": mat_kept,
            "mat_misses": mat_misses, "passed": passed, "total": total,
            "per_pred": per_pred, "misses": misses}

def show(name, s):
    print(f"\n{'='*70}\n{name}\n{'='*70}")
    print(f"  MATERIAL recall {s['mat_recall']*100:5.1f}%   ({s['mat_kept']}/{s['mat_total']} "
          f"risk-moving pairs kept)   ← the number that matters")
    print(f"  recall          {s['recall']*100:5.1f}%   ({s['tp']}/{s['tp']+s['fn']} relevant pairs kept)")
    print(f"  precision       {s['precision']*100:5.1f}%   ({s['tp']}/{s['tp']+s['fp']} kept pairs were relevant — "
          f"cheap LLM filters the rest)")
    print(f"  cost            {s['passed']}/{s['total']} pairs pass to the LLM "
          f"({s['passed']/s['total']*100:.0f}% — the rest filtered for $0)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--misses", action="store_true")
    ap.add_argument("--dataset", help="path to an alternate dataset.json (e.g. eval/gate/adversarial.json)")
    ap.add_argument("--gold", help="path to its matching gold.json")
    args = ap.parse_args()
    _load(args.dataset, args.gold)

    variants = {
        "CURRENT  (keyword gate, as shipped)": gate_current,
        "IMPROVED A  (+listing +broadened-kw +semantic; never-gate adverse_media)":
            lambda a, e: gate_improved(a, e, never_gate=("adverse_media_status",)),
        "IMPROVED B  (same, but never-gate ALL 3 critical: +sanctions +pep)":
            lambda a, e: gate_improved(a, e, never_gate=tuple(CRITICAL)),
    }
    results = {}
    for name, g in variants.items():
        results[name] = score(g)
        show(name, results[name])

    # recall by predicate, current vs improved-A
    print(f"\n{'='*70}\nRECALL BY PREDICATE  (current → improved-A)\n{'='*70}")
    cur, imp = results[list(variants)[0]], results[list(variants)[1]]
    preds = sorted(set(cur["per_pred"]) | set(imp["per_pred"]))
    for p in preds:
        ct, cf = cur["per_pred"].get(p, [0, 0])
        it, if_ = imp["per_pred"].get(p, [0, 0])
        cr = ct / (ct + cf) if (ct + cf) else 1.0
        ir = it / (it + if_) if (it + if_) else 1.0
        flag = "  ⚠️" if cr < 0.999 and cr <= ir else ""
        print(f"  {p:24s}  {cr*100:5.0f}%  →  {ir*100:5.0f}%   (n={ct+cf}){flag}")

    print(f"\n{'='*70}\nMATERIAL MISSES (risk-moving pairs DROPPED — the dangerous ones)\n{'='*70}")
    print(f"  CURRENT  : {len(cur['mat_misses'])} material pairs dropped")
    for eid, pred, summ in cur["mat_misses"]:
        print(f"      ✗ [{eid}] {pred}  ↳ {summ[:70]}")
    print(f"  IMPROVED-A: {len(imp['mat_misses'])} material pairs dropped")
    for eid, pred, summ in imp["mat_misses"]:
        print(f"      ✗ [{eid}] {pred}  ↳ {summ[:70]}")

    if args.misses:
        print(f"\n{'='*70}\nALL CURRENT-GATE MISSES (relevant pairs it DROPPED)\n{'='*70}")
        for eid, pred, summ in cur["misses"]:
            print(f"  [{eid}] {pred}\n      ↳ {summ[:88]}")

if __name__ == "__main__":
    main()
