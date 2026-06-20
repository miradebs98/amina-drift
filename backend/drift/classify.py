"""Event drift — does a single EvidenceEvent break a single Assertion?

  - check_envelope_breach: deterministic, NO LLM (jurisdiction outside the allowed set; volume > envelope).
  - classify_event: the cheap-LLM verdict, guarded by an anti-hallucination gate.

Stage-0 `is_candidate` (rules/keywords) decides which (assertion, event) pairs are worth a verdict —
most pairs die here for ~$0.
"""
from __future__ import annotations

from typing import Optional

from shared.schemas import Assertion, EvidenceEvent
from backend.drift import config
from backend.drift.llm import LLMClient, Verdict

# predicate -> signals that make an event RELEVANT to it (keywords / event types / payload flags)
PREDICATE_SIGNALS = {
    "business_model": {"kw": ["web3", "crypto", "trading", "pivot", "brokerage", "business-model"]},
    "product_mix": {"kw": ["crypto", "brokerage", "trading", "custody", "product"]},
    "operating_geographies": {"kw": ["offshore", "bvi", "seychelles", "expansion", "subsidiary", "corridor"],
                              "types": ["registry_change", "ownership_change"]},
    "counterparty_geographies": {"kw": ["offshore", "expansion", "corridor", "international"],
                                 "types": ["registry_change", "ownership_change"]},
    "ubo": {"kw": ["stake", "investor", "acquire", "acquires", "ownership", "shareholder"],
            "types": ["ownership_change"]},
    "pep_status": {"kw": ["pep", "politically exposed"], "payload_flags": ["pep_adjacent"]},
    "digital_asset_policy": {"kw": ["crypto", "treasury", "btc", "eth", "stablecoin", "digital asset", "custody"]},
    "digital_asset_holdings": {"kw": ["btc", "eth", "stablecoin", "usdc", "treasury", "holdings"]},
    "source_of_funds": {"kw": ["funds", "proceeds", "flows", "revenue"], "types": ["transaction"]},
    "source_of_wealth": {"kw": ["round", "funding", "investor", "raise", "series"], "types": ["funding"]},
    "regulatory_status": {"kw": ["fsra", "regulated", "licence", "license", "authoris", "unlicensed", "brokerage"]},
    "adverse_media_status": {"kw": ["investigation", "fraud", "probe", "litigation", "scandal", "charged", "named in"]},
    "sanctions_status": {"kw": ["sanction", "designat", "ofac", "sdn"], "types": ["sanctions_hit"]},
    "expected_monthly_volume": {"types": ["transaction"]},
}


def is_candidate(assertion: Assertion, event: EvidenceEvent) -> bool:
    """Stage-0 cheap relevance gate (no LLM)."""
    sig = PREDICATE_SIGNALS.get(assertion.predicate.value)
    if not sig:
        return False
    text = f"{event.summary} {event.payload}".lower()
    if any(event.payload.get(f) for f in sig.get("payload_flags", [])):
        return True
    if event.type.value in sig.get("types", []):
        return True
    return any(kw in text for kw in sig.get("kw", []))


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
    """Never let a 'contradicts' through unless the cited span actually appears in the evidence."""
    if verdict.verdict != "contradicts":
        return verdict
    text = f"{event.summary} {event.payload}".lower()
    if verdict.evidence_quote and verdict.evidence_quote.lower() in text:
        return verdict
    return Verdict("ambiguous", 0.0,
                   "Downgraded: cited evidence not found in the source (anti-hallucination gate).", "")


def classify_event(assertion: Assertion, event: EvidenceEvent, llm: LLMClient) -> Verdict:
    return anti_hallucination_gate(llm.classify(assertion, event), event)
