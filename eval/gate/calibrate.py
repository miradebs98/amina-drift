"""Calibrate the hybrid gate's semantic threshold τ (SEMANTIC_COSINE_MIN).

Sweeps τ over BOTH eval sets (real = must stay ~100% material recall; adversarial = the paraphrase/
unseen-vocab set the keyword gate scores 40% on) and prints material-recall / recall / precision /
pass-rate at each τ, so the threshold is CHOSEN from a curve, not a magic number.

    python -m eval.gate.calibrate

Embeddings are cached in-process (each unique text embedded once), so the whole sweep is a handful
of CSCS calls. Requires DRIFT_LLM_* in .env; with no endpoint it degrades to the lexical backstop.
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import eval.gate.run as R
from backend.drift import classify

SETS = {
    "REAL (must hold ~100% material)": (None, None),
    "ADVERSARIAL (keyword-only = 40%)": ("eval/gate/adversarial.json", "eval/gate/adversarial_gold.json"),
}
TAUS = [0.28, 0.30, 0.32, 0.34, 0.36, 0.38, 0.40, 0.42]


def main():
    for label, (ds, gold) in SETS.items():
        R._load(ds, gold)
        print(f"\n{'='*78}\n{label}\n{'='*78}")
        print(f"  {'τ':>5} | {'mat_recall':>10} | {'recall':>7} | {'precision':>9} | {'pass-rate':>9}")
        print(f"  {'-'*5}-+-{'-'*10}-+-{'-'*7}-+-{'-'*9}-+-{'-'*9}")
        for tau in TAUS:
            classify.SEMANTIC_COSINE_MIN = tau
            s = R.score(classify.is_candidate)
            print(f"  {tau:>5.2f} | {s['mat_recall']*100:>9.1f}% | {s['recall']*100:>6.1f}% "
                  f"| {s['precision']*100:>8.1f}% | {s['passed']/s['total']*100:>8.0f}%")


if __name__ == "__main__":
    main()
