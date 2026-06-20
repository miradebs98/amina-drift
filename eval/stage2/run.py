"""Stage-2 evaluation — the cheap-LLM verdict (Apertus-8B `classify_event` + grounding gate).

Stage 1 is recall-first (loose on purpose). Stage 2 is where PRECISION must happen: the cheap LLM
has to (a) catch real contradictions [recall = don't miss risk] and (b) reject the noise Stage 1
over-kept [precision = no false alarms], INCLUDING entity-confusion (another firm's IPO, wrong-entity
news). This runs the REAL classify_event on Apertus-8B over curated (belief,event) pairs with known
gold verdicts.  ~16 cheap calls.

  DRIFT_LLM_MOCK=  PYTHONPATH=. python -m eval.stage2.run
"""
from __future__ import annotations
import os
os.environ.pop("DRIFT_LLM_MOCK", None)   # REAL Apertus-8B

from datetime import date
from shared.schemas import Assertion, EvidenceEvent
from backend.drift.classify import classify_event
from backend.drift.llm import get_llm

# (predicate, belief value) | event summary | gold | note
#   gold = "contradicts"     → must be caught (recall; missing = silent risk)
#   gold = "irrelevant"      → must NOT be called contradicts (precision; the Stage-1 noise to clean up)
#   gold = "not_contradicts" → de-risking/resolving event; should NOT raise risk (known direction gap)
CASES = [
    # ── clear contradictions (recall) ──────────────────────────────────────
    ("regulatory_status", "US state money-transmitter licences; NOT a bank",
     "Circle receives OCC conditional approval to establish First National Digital Currency Bank, a national trust bank",
     "contradicts", "becoming a bank"),
    ("adverse_media_status", "No adverse media, investigation or litigation",
     "Revolut pays a EUR 3.5M fine to Lithuania's central bank for anti-money-laundering compliance failures",
     "contradicts", "AML fine"),
    ("product_mix", "Payments and settlement via XRP; no stablecoin, no banking",
     "Ripple launches RLUSD, a US dollar-pegged stablecoin, entering the stablecoin market",
     "contradicts", "new stablecoin product"),
    ("product_mix", "Crypto spot trading, staking and custody; no futures, no equities",
     "Kraken agrees to acquire US retail futures platform NinjaTrader for $1.5B, entering US futures",
     "contradicts", "enters futures"),
    ("listing_status", "Private company",
     "Circle goes public on the NYSE at $31 per share under ticker CRCL in a $5B IPO",
     "contradicts", "now public"),
    ("regulatory_status", "Patchwork registrations; not bank-chartered; under regulatory scrutiny",
     "Binance set to lose permission to operate in the EU as its MiCA licence application is rejected",
     "contradicts", "loses EU permission"),
    ("business_model", "Crypto spot exchange and custody",
     "Kraken rolls out commission-free trading of over 11,000 US-listed stocks and ETFs, moving into equities",
     "contradicts", "now multi-asset broker"),

    # ── irrelevant / entity-confusion (precision — clean up Stage-1 over-keeps) ──
    ("ubo", "Founder Changpeng Zhao (CZ), majority owner",
     "Binance launches futures tied to SpaceX's anticipated IPO valuation",
     "irrelevant", "SpaceX's IPO, not Binance ownership"),
    ("ubo", "Founders Vlad Tenev and Baiju Bhatt; publicly listed",
     "Another analyst raises Robinhood stock price target",
     "irrelevant", "analyst note, not ownership change"),
    ("business_model", "Global crypto exchange and trading platform",
     "Bitcoin is trading more like a macro asset, Binance India says",
     "irrelevant", "generic market commentary"),
    ("product_mix", "Stocks, options and crypto trading; no banking",
     "Major Oak: Ancient 'Robin Hood' tree is dead, experts say",
     "irrelevant", "WRONG ENTITY (a tree)"),
    ("source_of_wealth", "Exchange trading fees",
     "Binance will list RE (RE) token with Seed Tag applied",
     "irrelevant", "token listing, not Binance's funding"),

    # ── de-risking / resolving (should NOT increase risk; known direction gap) ──
    ("adverse_media_status", "SEC staking matter pending; no other adverse media",
     "SEC drops its lawsuit against Kraken, ending the case over its staking operations",
     "not_contradicts", "RESOLVES the matter — de-risking"),
    ("regulatory_status", "Under SEC securities litigation; not a chartered bank",
     "SEC lawsuit against Ripple ends; both sides drop appeals",
     "not_contradicts", "litigation resolved — de-risking"),
]


def mk(pred, val, summary):
    a = Assertion(id=f"x-{pred}", customer_id="x", predicate=pred, value=val,
                  as_of=date(2023, 1, 1), last_verified=date(2023, 1, 1),
                  source="eval", confidence=0.9, status="valid")
    e = EvidenceEvent(id="e", entity_ref="X", customer_id="x", type="news", summary=summary,
                      payload={}, source="eval", source_url="http://x", published_at="2025-01-01T00:00:00Z",
                      confidence=0.8)
    return a, e


def main():
    llm = get_llm()
    print(f"LLM: {type(llm).__name__}\n" + "=" * 92)
    catch = miss = false_pos = derisk_overflag = 0
    n_contra = n_irrel = n_derisk = 0
    for pred, val, summ, gold, note in CASES:
        a, e = mk(pred, val, summ)
        v = classify_event(a, e, llm)
        verdict = v.verdict
        ok = "?"
        if gold == "contradicts":
            n_contra += 1
            if verdict == "contradicts": catch += 1; ok = "✓"
            else: miss += 1; ok = "✗ MISS"
        elif gold == "irrelevant":
            n_irrel += 1
            if verdict == "contradicts": false_pos += 1; ok = "✗ FALSE-POS"
            else: ok = "✓"
        else:  # not_contradicts (de-risk)
            n_derisk += 1
            if verdict == "contradicts": derisk_overflag += 1; ok = "✗ OVER-FLAG"
            else: ok = "✓"
        print(f"[{ok:12s}] gold={gold:15s} model={verdict:11s} str={v.strength:.2f}  {pred}")
        print(f"               ev: {summ[:74]}")
        print(f"               quote: {(v.evidence_quote or '(none)')[:74]}\n")

    print("=" * 92)
    print(f"CONTRADICTION RECALL : {catch}/{n_contra}  (missed {miss} real contradictions = silent risk)")
    print(f"IRRELEVANT PRECISION : {n_irrel-false_pos}/{n_irrel}  (false-contradictions on noise = {false_pos})")
    print(f"DE-RISK handling     : {n_derisk-derisk_overflag}/{n_derisk} not over-flagged  "
          f"(over-flagged {derisk_overflag} good-news events as risk)")
    cost = llm.cost if hasattr(llm, "cost") else None
    if cost:
        print(f"cost: cheap={cost.cheap_calls} heavy={cost.heavy_calls} tokens={cost.total_tokens}")


if __name__ == "__main__":
    main()
