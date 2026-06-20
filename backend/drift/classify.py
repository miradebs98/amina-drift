"""Event drift — does a single EvidenceEvent break a single Assertion?

  - check_envelope_breach: deterministic, NO LLM (jurisdiction outside the allowed set; volume > envelope).
  - classify_event: the cheap-LLM verdict, guarded by an anti-hallucination gate.

Stage-0 `is_candidate` (rules/keywords) decides which (assertion, event) pairs are worth a verdict —
most pairs die here for ~$0.
"""
from __future__ import annotations

import re
from typing import Optional

from shared.schemas import Assertion, EvidenceEvent
from backend.drift import config
from backend.drift.llm import LLMClient, Verdict

_NONWORD = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace; pad with spaces for substring tests."""
    return " " + " ".join(_NONWORD.sub(" ", s.lower()).split()) + " "


def _token_overlap(quote_norm: str, text_norm: str) -> float:
    """Fraction of the quote's content tokens present in the evidence text."""
    qt = [t for t in quote_norm.split() if len(t) > 2]
    if not qt:
        return 0.0
    tset = set(text_norm.split())
    return sum(1 for t in qt if t in tset) / len(qt)

# predicate -> signals that make an event RELEVANT to it (keywords / event types / payload flags).
# Keyword lists are broadened to the vocabulary REAL news actually uses — validated in `eval/gate/`
# against Claude-labelled events for 4 real firms: the ORIGINAL lists gave only 35% MATERIAL recall
# (the words "fine/penalty/IPO/bank charter/futures/EU" simply never appeared). Stage-1 is
# RECALL-FIRST; the cheap LLM (Stage-2) is the precision backstop, so over-inclusion costs a cheap
# call, but a miss here is a signal that never reaches the LLM = silent risk.
PREDICATE_SIGNALS = {
    "business_model": {"kw": ["web3", "crypto", "trading", "pivot", "brokerage", "business-model",
                              "bank", "acquire", "acquisition", "expand", "multi-asset"]},
    "product_mix": {"kw": ["crypto", "brokerage", "trading", "custody", "product", "futures", "equit",
                           "stock", "etf", "stablecoin", "treasury", "prime brok", "clearing",
                           "deposit", "settlement", "payments"]},
    "operating_geographies": {"kw": ["offshore", "bvi", "seychelles", "expansion", "expand", "subsidiary",
                                     "corridor", "eu", "europe", "european", "international", "overseas",
                                     "abroad", "cross-border", "jurisdiction"],
                              "types": ["registry_change", "ownership_change"]},
    "counterparty_geographies": {"kw": ["offshore", "expansion", "corridor", "international"],
                                 "types": ["registry_change", "ownership_change"]},
    # INBOUND ownership change: an ownership_change event, a stake-in-the-customer payload, OR a funding
    # round / IPO (a new lead investor can become a >25% UBO → re-screen). Deliberately NOT bare
    # "acquire/stake": those also match the customer acquiring OTHERS (Coinbase→Deribit), which doesn't
    # change Coinbase's own UBO.
    "ubo": {"kw": ["new shareholder", "new owner", "takes a stake", "acquires a stake", "stake in",
                   "ipo", "goes public", "public offering", "new investor", "lead investor"],
            "types": ["ownership_change", "funding"],
            "payload_flags": ["pep_adjacent", "new_owner", "stake_pct"]},
    "pep_status": {"kw": ["pep", "politically exposed"], "payload_flags": ["pep_adjacent"]},
    "digital_asset_policy": {"kw": ["crypto", "treasury", "btc", "eth", "stablecoin", "digital asset", "custody"]},
    "digital_asset_holdings": {"kw": ["btc", "eth", "stablecoin", "usdc", "treasury", "holdings"]},
    "source_of_funds": {"kw": ["funds", "proceeds", "flows", "revenue"], "types": ["transaction"]},
    "source_of_wealth": {"kw": ["round", "funding", "investor", "raise", "series", "valuation", "profit",
                                "revenue", "acquire", "acquisition"], "types": ["funding"]},
    "regulatory_status": {"kw": ["fsra", "regulated", "licence", "license", "authoris", "unlicensed",
                                 "brokerage", "bank", "charter", "occ", "fca", "pra", "sec", "cftc", "fcm",
                                 "approval", "supervis", "sandbox", "genius act", "mica", "emi"]},
    "adverse_media_status": {"kw": ["investigation", "fraud", "probe", "litigation", "scandal", "charged",
                                    "named in", "fine", "fined", "penalty", "settlement", "settle", "sued",
                                    "lawsuit", "aml", "compliance failure", "sanction", "money laundering"]},
    "sanctions_status": {"kw": ["sanction", "designat", "ofac", "sdn", "aml", "money laundering",
                                "financial crime"], "types": ["sanctions_hit"]},
    "listing_status": {"kw": ["ipo", "public", "listing", "listed", "nyse", "nasdaq", "stock exchange",
                              "go public", "goes public", "s-1", "flotation", "delist"]},
    "expected_monthly_volume": {"types": ["transaction"]},
}

# Critical, news-driven category that is NEVER filtered out: every public event is a candidate for
# "is this adverse media?" (eval/gate/: the keyword gate missed 100% of adverse media — AML fines, SEC
# penalties — because they don't say "investigation/fraud"). Sanctions/PEP are deliberately NOT here:
# they're covered by the always-on dedicated screen (SanctionsConnector), so blanket-passing every
# event for them is pure cost with zero recall gain (eval: 56% vs 38% pass-rate, identical recall).
NEVER_GATE = {"adverse_media_status"}
SEMANTIC_MIN = 2  # generous lexical backstop: >= 2 shared (stemmed) content tokens between belief & event

_STOP = set("the a an and or of to in for with on at by from is are be as not no into its their our via "
            "using under over more most new only both global company group ltd inc llc plc nv sa than "
            "after before year years per up down out off it this that these those will would".split())


def _stem(w: str) -> str:
    for suf in ("ization", "isation", "ations", "ation", "ing", "ised", "ized", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _content_tokens(s: str) -> set:
    return {_stem(t) for t in _NONWORD.sub(" ", s.lower()).split() if len(t) > 2 and t not in _STOP}


def _semantic_overlap(assertion: Assertion, event: EvidenceEvent) -> int:
    """Free lexical proxy for semantic relevance: shared (stemmed) content tokens between the belief
    (predicate + on-file value) and the event summary. Catches phrasings the fixed keywords miss."""
    belief = _content_tokens(assertion.predicate.value.replace("_", " ") + " " + assertion.value)
    return len(belief & _content_tokens(event.summary))


def is_candidate(assertion: Assertion, event: EvidenceEvent) -> bool:
    """Stage-1 cheap relevance gate (no LLM). RECALL-FIRST: keep anything plausibly relevant; the cheap
    LLM is the precision backstop. Validated in eval/gate/ — 100% MATERIAL recall on a real-event set
    (vs 35% for the original keyword-only gate), at ~38% pass-rate."""
    pred = assertion.predicate.value
    if pred in NEVER_GATE:                                  # critical news-driven category → never filter
        return True
    sig = PREDICATE_SIGNALS.get(pred)
    if sig:
        text = f"{event.summary} {event.payload}".lower()
        if any(event.payload.get(f) for f in sig.get("payload_flags", [])):
            return True
        if event.type.value in sig.get("types", []):
            return True
        if any(kw in text for kw in sig.get("kw", [])):
            return True
    return _semantic_overlap(assertion, event) >= SEMANTIC_MIN   # generous lexical backstop


def check_envelope_breach(assertion: Assertion, event: EvidenceEvent) -> Optional[float]:
    """Deterministic breach of an expected_envelope. Returns breach magnitude in [0,1] or None."""
    env = assertion.expected_envelope
    if env is None:
        return None
    if env.allowed_set is not None:
        allowed = {s.upper() for s in env.allowed_set}
        for key, val in event.payload.items():
            if isinstance(val, str) and any(k in key.lower() for k in ("jurisdiction", "country", "geo", "domicile", "city")):
                code = {"UNITED KINGDOM": "GB"}.get(val.strip().upper(), val.strip().upper())
                if code and code not in allowed and len(code) <= 3:
                    return config.ENVELOPE_NEW_JURISDICTION
    if env.low is not None or env.high is not None:
        for key, val in event.payload.items():
            if isinstance(val, (int, float)) and "envelope" not in key.lower() and "high" not in key.lower() and "low" not in key.lower():
                if env.high is not None and val > env.high:
                    return min(1.0, (val - env.high) / max(env.high, 1.0))
                if env.low is not None and val < env.low:
                    return min(1.0, (env.low - val) / max(env.low, 1.0))
    return None


def anti_hallucination_gate(verdict: Verdict, event: EvidenceEvent) -> Verdict:
    """Never let a 'contradicts' through unless the cited span is supported by the evidence.
    Fuzzy (normalized substring OR token-overlap >= 0.6), so a real model that paraphrases its quote
    isn't falsely rejected — while a fabricated quote (low overlap) still gets downgraded."""
    if verdict.verdict != "contradicts":
        return verdict
    text = _norm(f"{event.summary} {event.payload}")
    quote = _norm(verdict.evidence_quote or "")
    if quote.strip():
        if quote in text or _token_overlap(quote, text) >= 0.6:
            return verdict                       # the model's quote IS in the evidence — keep it
        return Verdict("ambiguous", 0.0,         # the model FABRICATED a quote not in the evidence → kill
                       "Downgraded: cited quote not supported by the source (anti-hallucination gate).", "")
    # No quote supplied: the verdict still rests on a REAL evidence event (has a source_url) — there's
    # nothing fabricated to reject. Ground the flag with the event's own (verbatim, sourced) summary.
    return Verdict("contradicts", verdict.strength, verdict.rationale, event.summary[:200])


def classify_event(assertion: Assertion, event: EvidenceEvent, llm: LLMClient) -> Verdict:
    return anti_hallucination_gate(llm.classify(assertion, event), event)
