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
SEMANTIC_MIN = 2  # lexical backstop (offline fallback): >= 2 shared stemmed content tokens belief↔event

# --- Stage-1 SEMANTIC backstop: free Swiss-sovereign embeddings (CSCS arctic-embed) ----------------
# Keyword/type/flag hits stay FIRST (precision, $0, fully auditable). When they're silent, we fall
# back to embedding cosine between a RICH belief query (predicate + on-file value + the predicate's
# drift signals) and the event text. This catches paraphrase/synonymy the keywords structurally
# cannot — "Cayman"≈offshore, "cabinet minister"≈PEP, "perpetual contracts"≈derivatives — the exact
# gap proven in eval/gate/adversarial.json (keyword-only: 40% material recall). Calibrated in
# eval/gate/calibrate.py. If the endpoint is unreachable, we degrade to the lexical overlap above
# (so CI / offline still runs) — that's resilience, not a silent downgrade of the headline.
# τ=0.24 chosen on the calibration curve: REAL set holds 100% material recall (42% pass-rate, vs 37%
# keyword-only); ADVERSARIAL set rises 40% → 87% material recall. Lowering to 0.22 reaches 93% (also
# catches an undisclosed-derivatives case) at a modestly higher cheap-call rate — move it if desired.
SEMANTIC_COSINE_MIN = 0.24

_EMB = None                                  # lazy singleton: SwissAIEmbedder | False(=unavailable)
_EMB_CACHE: dict[str, list[float]] = {}      # text -> vector (embed each unique string once per run)


def _embedder():
    global _EMB
    if _EMB is None:
        try:
            from backend.drift.swissai_embed import SwissAIEmbedder
            _EMB = SwissAIEmbedder()
        except Exception:
            _EMB = False
    return _EMB or None


def _embed(text: str) -> Optional[list[float]]:
    v = _EMB_CACHE.get(text)
    if v is not None:
        return v
    emb = _embedder()
    if emb is None:
        return None
    try:
        v = emb.embed_text(text)
    except Exception:
        global _EMB
        _EMB = False                         # endpoint died mid-run → stop retrying, lexical fallback
        return None
    _EMB_CACHE[text] = v
    return v


def _cosine(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# Natural-language drift descriptions per predicate — the semantic "bridge" that lets the embedder
# connect real-world phrasings to the predicate WITHOUT the literal keyword ("cabinet minister"→PEP,
# "Cayman"→offshore, "perpetual contracts"→derivatives). This is GRAIN's build_rich_query idea done
# properly: a query needs a description + examples, not a terse keyword list. Calibrated in
# eval/gate/calibrate.py — these directly drive Stage-1 recall on paraphrased / unseen-vocab events.
SEMANTIC_HINTS = {
    "business_model": "a pivot or material change of core business — moving into crypto, web3, trading, brokerage, banking, payments, or a new line of activity",
    "product_mix": "new or changed products and services — trading, derivatives, futures, perpetuals, custody, lending, deposits, payments, stablecoins, prime brokerage, clearing",
    "operating_geographies": "expansion into or relocation to a new jurisdiction — offshore centres such as the Cayman Islands, BVI or Seychelles, new countries, foreign subsidiaries, re-domiciliation of the holding company",
    "counterparty_geographies": "dealing with counterparties in new or higher-risk jurisdictions, offshore corridors, or new cross-border flows",
    "ubo": "a change of beneficial ownership or control — a new shareholder, controlling owner, family office or consortium acquiring a stake, or a newly disclosed ultimate beneficial owner, founders stepping back",
    "pep_status": "a politically exposed person — a government minister, cabinet member, politician, member of parliament, senior public official, head of state or ambassador, or a close family member or associate of one — appointed as a director, owner or board member",
    "digital_asset_policy": "adopting or expanding digital-asset activity — holding crypto, bitcoin or stablecoins, tokenised instruments, a corporate crypto treasury, or providing custody",
    "digital_asset_holdings": "holdings of crypto, bitcoin, stablecoins or tokenised assets on the balance sheet or in treasury reserves",
    "source_of_funds": "a change in where operating funds or proceeds come from",
    "source_of_wealth": "new wealth or capital — a funding round, capital raise, large investment, IPO proceeds, or a sudden change in revenue or valuation",
    "regulatory_status": "a change in regulatory standing — a new licence or authorisation, an enforcement action, a cease-and-desist or warning, unregistered or unlicensed activity, or becoming or ceasing to be a regulated or bank entity",
    "adverse_media_status": "negative news — an investigation, probe, fraud, fine, penalty, lawsuit, settlement, sanctions, money laundering, an executive departure amid a review, or a scandal",
    "sanctions_status": "sanctions exposure — an OFAC, EU or UN designation, an SDN listing, dealing with a sanctioned entity, or money-laundering / financial-crime links",
    "listing_status": "going public or a change in listing — an IPO, an S-1 filing, listing on the NYSE or Nasdaq, becoming a public company, or a delisting",
    "expected_monthly_volume": "transaction volumes or values inconsistent with the expected profile — sudden spikes, dormancy breaks, or large cross-border transfers",
}


def _rich_belief(assertion: Assertion) -> str:
    """Expand the belief into an embedding QUERY (GRAIN's build_rich_query trick). The bare on-file
    value is too short and often a negation ('no crypto') that adds noise, so we lead with a
    natural-language description of what drift looks like for this predicate. The 'query:' prefix is
    what arctic-embed-v2 is trained to expect on the query side (sharply improves weak matches)."""
    pred = assertion.predicate.value
    hint = SEMANTIC_HINTS.get(pred) or ", ".join(PREDICATE_SIGNALS.get(pred, {}).get("kw", [])[:12])
    return f"query: {pred.replace('_', ' ')} — {hint}. current on-file value: {assertion.value}"


def _semantic_relevant(assertion: Assertion, event: EvidenceEvent) -> bool:
    """Embedding cosine (rich belief ↔ event); lexical token-overlap if embeddings are unavailable."""
    qv = _embed(_rich_belief(assertion))
    ev = _embed(event.summary)
    if qv is None or ev is None:
        return _semantic_overlap(assertion, event) >= SEMANTIC_MIN
    return _cosine(qv, ev) >= SEMANTIC_COSINE_MIN

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
    """Stage-1 relevance gate (no verdict LLM). RECALL-FIRST hybrid: cheap keyword/type/flag hits
    first (precision, $0, auditable), then a free Swiss-sovereign EMBEDDING backstop for paraphrase /
    unseen vocabulary; the cheap Stage-2 LLM is the precision backstop downstream. Validated in
    eval/gate/: REAL set 100% material recall; ADVERSARIAL (paraphrase/synonym) set 87% — vs 40% for
    the keyword-only gate on the same adversarial events."""
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
    return _semantic_relevant(assertion, event)   # semantic (embedding) backstop, lexical if offline


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
