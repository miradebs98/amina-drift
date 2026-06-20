"""LLM client behind one swappable interface.

The engine never imports OpenAI/Anthropic directly. It calls an `LLMClient` with two jobs:
  - classify(assertion, event)  -> the cheap Stage-2 verdict (confirms/contradicts/...)
  - synthesize(...)             -> the heavy Stage-3 deep-dive narrative

`MockLLM` is deterministic + offline (keyword rules) so the whole pipeline + tests run with no
network and no keys. `ApiLLM` is the stub you wire to gpt-4o-mini / claude-haiku (cheap) and
gpt-4o / claude-sonnet (heavy) when you have a key — same interface, drop-in.

A CostMeter counts calls + estimates tokens so the DriftAlert carries cost metadata (Mira's
cascade refines this, but the engine produces plausible numbers on its own).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from shared.schemas import Assertion, EvidenceEvent

# Load .env so DRIFT_LLM_* (Apertus/CSCS) are visible even when a drift script runs standalone
# (run_demo / smoke_apertus / tests) — not only when the ingest layer happens to be imported.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:
    pass

VERDICTS = ("confirms", "contradicts", "irrelevant", "ambiguous", "resolves")


@dataclass
class Verdict:
    verdict: str          # one of VERDICTS
    strength: float       # [0,1] how strong the (contra)diction is
    rationale: str        # human-readable, grounded in the event
    evidence_quote: str   # the span of the event that justifies it (anti-hallucination checks this)


@dataclass
class RiskJudgment:
    """Stage-3 risk interpretation of a drift episode — the LLM judging drift -> RISK (not just change).

    `risk_delta` is SIGNED in impact-units (+ raises risk; negative = de-risking, e.g. a lawsuit
    dismissed). flag/action/reasoning may be "" → the caller falls back to its static map (so the
    deterministic MockLLM path keeps today's behaviour, while ApiLLM produces the real interpretation).
    """
    risk_relevant: bool
    risk_delta: float
    flag: str
    recommended_action: str
    reasoning: str
    evidence_quote: str


@dataclass
class CostMeter:
    cheap_calls: int = 0
    heavy_calls: int = 0
    cheap_tokens: int = 0
    heavy_tokens: int = 0

    def record(self, tier: str, in_text: str, out_text: str) -> None:
        toks = max(1, (len(in_text) + len(out_text)) // 4)  # ~4 chars/token estimate
        if tier == "heavy":
            self.heavy_calls += 1
            self.heavy_tokens += toks
        else:
            self.cheap_calls += 1
            self.cheap_tokens += toks

    @property
    def total_tokens(self) -> int:
        return self.cheap_tokens + self.heavy_tokens

    @property
    def escalation_rate(self) -> float:
        total = self.cheap_calls + self.heavy_calls
        return (self.heavy_calls / total) if total else 0.0


class LLMClient:
    def __init__(self) -> None:
        self.meter = CostMeter()

    def classify(self, assertion: Assertion, event: EvidenceEvent) -> Verdict:
        raise NotImplementedError

    def synthesize(self, prompt: str) -> str:
        raise NotImplementedError

    def interpret_risk(self, drifts: list[dict], context: dict) -> "RiskJudgment":
        raise NotImplementedError


# --- drift keyword set for the offline mock verdict --------------------------------------------
_DRIFT_KW = (
    "crypto", "web3", "bitcoin", "btc", "eth", "stablecoin", "usdc", "token", "brokerage",
    "trading", "custody", "treasury", "digital asset", "offshore", "bvi", "seychelles",
    "expansion", "subsidiary", "stake", "investor", "acquire", "acquires", "round", "funding",
    "pep", "politically exposed", "fraud", "investigation", "probe", "litigation", "scandal",
    "fsra", "unlicensed", "regulated activity", "proceeds",
)
# events that RETRACT a prior concern → risk comes back DOWN (the signed down-move).
_RESOLVE_KW = (
    "dismiss", "dropped", "cleared", "resolved", "acquitted", "withdrawn", "exonerat",
    "divest", "in favour", "in favor", "ruling for", "overturned", "case closed",
)
_BREAKABLE = {
    "business_model", "product_mix", "digital_asset_policy", "digital_asset_holdings",
    "operating_geographies", "counterparty_geographies", "ubo", "source_of_funds",
    "source_of_wealth", "regulatory_status", "pep_status", "sanctions_status", "adverse_media_status",
}

# --- baseline-consistency: drift = DEVIATION from the baseline, not mere topicality ----------------
# A signal the baseline ALREADY asserts is not surprising — Coinbase onboarded as a global, regulated
# crypto exchange, so its crypto/expansion/MiCA news CONFIRMS the profile. Only a deviation contradicts.
# This is the offline stand-in for what a real LLM reasons; it holds Coinbase at MEDIUM while Meridian
# (SaaS, UAE-only, no crypto) still flips. Restrictive baselines ("no crypto", "UAE-only") assert the
# ABSENCE of a theme, so an event in that theme is a genuine deviation.
_THEMES = {
    "crypto": {"crypto", "web3", "bitcoin", "btc", "eth", "ether", "stablecoin", "usdc", "token",
               "digital asset", "digital-asset", "brokerage", "custody", "exchange", "blockchain", "defi"},
    "global": {"global", "globally", "international", "worldwide", "expansion", "expanding", "abroad",
               "multinational", "cross-border", "europe", "european"},
    "offshore": {"offshore", "bvi", "seychelles", "cayman", "mauritius"},
}
_THEME_PREDICATES = {
    "business_model", "product_mix", "industry_sector", "operating_geographies",
    "counterparty_geographies", "digital_asset_policy", "digital_asset_holdings",
}
_NEGATIONS = ("no ", "not ", "none", "without", "only", "sole", "exclusively", "prohibit", "exclud", "never", "non-")


def _event_theme(text: str) -> str | None:
    for name, words in _THEMES.items():
        if any(w in text for w in words):
            return name
    return None


def consistent_with_baseline(predicate: str, baseline: str, event_text: str) -> bool:
    """True when the event's signal is already part of the on-file baseline (→ confirms, not drift)."""
    base = f" {baseline.lower()} "
    if predicate in _THEME_PREDICATES:
        theme = _event_theme(event_text)
        if theme is None:
            return False
        if any(neg in base for neg in _NEGATIONS):          # restrictive baseline → deviation-capable
            return False
        return any(w in base for w in _THEMES[theme])
    if predicate == "regulatory_status":
        # a positive licensing event confirms an already-regulated entity; an unlicensed/adverse one drifts
        adverse = (any(w in event_text for w in ("unlicensed", "unauthor", "unregist", "violat",
                                                 "illegal", "breach", "non-compli", "revoked", "suspend"))
                   or (any(n in event_text for n in ("without", " no ", "not ", "lacks", "absent"))
                       and any(w in event_text for w in ("authoris", "licen", "fsra", "approval", "registration"))))
        if adverse:
            return False
        return any(w in base for w in ("regulated", "licen", "bitlicense", "mtl", "mica",
                                       "authoris", "registered", "nydfs"))
    return False    # adverse_media / pep / sanctions / source_of_funds / volume → always genuine


class MockLLM(LLMClient):
    """Offline, deterministic stand-in. A clean/narrow onboarding belief is 'contradicted' when a
    drift signal for that predicate appears. (Real ApiLLM returns the same Verdict via a provider.)"""

    tier = "cheap"

    def classify(self, assertion: Assertion, event: EvidenceEvent) -> Verdict:
        text = f"{event.summary} {event.payload}".lower()
        if assertion.predicate.value in _BREAKABLE and any(rk in text for rk in _RESOLVE_KW):
            v = Verdict("resolves", max(0.5, min(0.95, float(event.confidence))),
                        f"De-risking event — retracts a prior concern on {assertion.predicate.value}.",
                        event.summary[:120])
            self.meter.record("cheap", str(assertion.value) + text, v.verdict)
            return v
        hit = next((kw for kw in _DRIFT_KW if kw in text), None)
        if hit and assertion.predicate.value in _BREAKABLE:
            if consistent_with_baseline(assertion.predicate.value, str(assertion.value), text):
                v = Verdict("confirms", 0.0,
                            f"Consistent with the on-file baseline ({assertion.predicate.value} = "
                            f"{assertion.value}) — no drift.", "")
            else:
                strength = max(0.5, min(0.95, float(event.confidence)))
                v = Verdict("contradicts", strength,
                            f"Event indicates '{hit}', contradicting the on-file belief "
                            f"({assertion.predicate.value} = {assertion.value}).", hit)
        else:
            v = Verdict("irrelevant", 0.0, "No bearing on this assertion.", "")
        self.meter.record("cheap", str(assertion.value) + text, v.verdict + v.rationale)
        return v

    def synthesize(self, prompt: str) -> str:
        # Deterministic template stand-in for the heavy deep-dive narrative.
        out = "[deep-dive] " + prompt.strip().split("\n")[0][:200]
        self.meter.record("heavy", prompt, out)
        return out

    def interpret_risk(self, drifts: list[dict], context: dict) -> RiskJudgment:
        """Deterministic stand-in: risk_delta = the static surprise×weight×direction; flag/action/
        reasoning left empty so the caller keeps its static map (today's numbers + flags preserved).
        ApiLLM does the real contextual judgement."""
        from backend.drift import config
        delta = 0.0
        for d in drifts:
            pred = d.get("predicate", "")
            w = config.RISK_WEIGHT.get(pred, config.DEFAULT_RISK_WEIGHT)
            sign = config.RISK_DIRECTION.get(pred, config.DEFAULT_RISK_DIRECTION)
            delta += float(d.get("surprise", 0.0)) * w * sign
        quote = (drifts[0].get("evidence") or [""])[0] if drifts else ""
        j = RiskJudgment(risk_relevant=delta > 0.02, risk_delta=round(delta, 3),
                         flag="", recommended_action="", reasoning="", evidence_quote=str(quote)[:160])
        self.meter.record("heavy", str(context) + str(drifts), "risk")
        return j


class ApiLLM(LLMClient):
    """OpenAI-compatible client — works with OpenAI, Azure, a local vLLM, or **Apertus** (Swiss-
    sovereign) once you have its endpoint. Cheap tier = the sensitive Layer-2 path (run it on
    Apertus so KYC data never leaves Swiss jurisdiction); heavy tier = the deep-dive.

    Resilient by design: if the endpoint errors or is unreachable, it falls back to MockLLM for
    that one call, so the offline demo never breaks (the team's 'fixtures must run with no network').
    """

    def __init__(self, base_url: str, api_key: str, cheap_model: str, heavy_model: str, timeout: float = 20.0):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.cheap_model = cheap_model
        self.heavy_model = heavy_model
        self.timeout = timeout
        self._fallback = MockLLM()

    def _chat(self, model: str, system: str, user: str, tier: str) -> str:
        import httpx  # lazy import — only needed when actually calling out
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": model, "temperature": 0,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        toks = (data.get("usage") or {}).get("total_tokens") or max(1, (len(system) + len(user) + len(content)) // 4)
        if tier == "heavy":
            self.meter.heavy_calls += 1; self.meter.heavy_tokens += toks
        else:
            self.meter.cheap_calls += 1; self.meter.cheap_tokens += toks
        return content

    def classify(self, assertion: Assertion, event: EvidenceEvent) -> Verdict:
        system = ('You are a KYC drift detector for a regulated bank. Compare the EVIDENCE against the '
                  'on-file BELIEF (a specific KYC value) and classify their relationship. Judge against '
                  'the SPECIFIC belief value, NOT the topic in general — the SAME crypto news '
                  'CONTRADICTS a "SaaS, no crypto" belief but CONFIRMS a "crypto exchange" belief.\n'
                  '- contradicts: the evidence shows something the belief does NOT already state and '
                  'that materially deviates — a NEW activity/product, a new owner with a significant '
                  'stake, a new jurisdiction, or a compliance violation. E.g. belief "B2B SaaS, no '
                  'crypto" + "launches a crypto brokerage" -> contradicts; "licensed/compliant" + '
                  '"unlicensed or unauthorised activity" -> contradicts; UBO = the founders + "a fund '
                  'takes a 30% stake" -> contradicts; "UAE-only" + "opens an offshore BVI entity" -> '
                  'contradicts.\n'
                  '- confirms: the evidence is consistent with what the belief ALREADY states (e.g. '
                  '"crypto exchange" + "launches a crypto product").\n'
                  '- irrelevant: no bearing on this belief. ambiguous: genuinely unclear.\n'
                  '- resolves: a DE-RISKING event that retracts a prior concern (lawsuit dismissed, '
                  'investigation closed, risky unit divested) — lowers risk.\n'
                  'Reply with ONLY one JSON object and nothing else: '
                  '{"verdict":"confirms|contradicts|irrelevant|ambiguous|resolves","strength":0.0-1.0,'
                  '"evidence_quote":"<short phrase copied WORD-FOR-WORD from the EVIDENCE text only>",'
                  '"rationale":"<1-2 sentences; do NOT put the quote here>"}. '
                  'If verdict is "contradicts", evidence_quote MUST be a non-empty phrase taken '
                  'verbatim from the EVIDENCE summary or payload.')
        user = (f"BELIEF: predicate={assertion.predicate.value}; value={assertion.value}\n"
                f"EVIDENCE: type={event.type.value}; summary={event.summary}; payload={event.payload}")
        try:
            obj = _parse_json(self._chat(self.cheap_model, system, user, "cheap"))
            return Verdict(str(obj.get("verdict", "ambiguous")), float(obj.get("strength") or 0.0),
                           str(obj.get("rationale", "")), str(obj.get("evidence_quote", "")))
        except Exception:
            return self._fallback.classify(assertion, event)  # demo never breaks

    def synthesize(self, prompt: str) -> str:
        system = ("You are a senior compliance analyst. Write a concise, evidence-grounded deep-dive: "
                  "what drifted, what it means for risk, and the recommended action. Plain prose.")
        try:
            return self._chat(self.heavy_model, system, prompt, "heavy")
        except Exception:
            out = "[deep-dive] " + prompt.strip().split("\n")[0][:200]
            self.meter.record("heavy", prompt, out)
            return out

    def interpret_risk(self, drifts: list[dict], context: dict) -> RiskJudgment:
        system = (
            "You are a KYC risk officer at a regulated bank (AMINA). You receive a set of DRIFTS — "
            "on-file beliefs about a client that recent public evidence has challenged — plus the client "
            "CONTEXT. Judge the episode for RISK (not mere change): is it risk-relevant, which risk FLAG "
            "it raises, the recommended ACTION, and HOW risk moves. risk_delta is SIGNED in [-1,1] on a "
            "risk-contribution scale (+ raises risk; NEGATIVE for de-risking/resolving events, e.g. a "
            "lawsuit dismissed). CONNECT THE DOTS across the drifts/dimensions — the danger is the "
            "combination, even when each change is individually minor. Reply with ONLY one JSON object: "
            '{"risk_relevant":true|false,"risk_delta":-1.0..1.0,'
            '"flag":"<short risk category, e.g. Ownership Change - KYC Drift>",'
            '"recommended_action":"<concise compliance action>",'
            '"reasoning":"<2-4 sentences citing the dated drifts + their dimensions; why risk moved or held>",'
            '"evidence_quote":"<short phrase copied verbatim from one drift\'s evidence>"}'
        )
        user = ("CONTEXT: " + str(context) + "\nDRIFTS:\n" + "\n".join(
            f"- [{d.get('dimension', '')}] {d.get('predicate')}: on file '{d.get('belief')}'"
            f" ; evidence: {'; '.join(d.get('evidence', [])[:2])}" for d in drifts))
        try:
            obj = _parse_json(self._chat(self.heavy_model, system, user, "heavy"))
            return RiskJudgment(
                bool(obj.get("risk_relevant", True)), float(obj.get("risk_delta") or 0.0),
                str(obj.get("flag", "")), str(obj.get("recommended_action", "")),
                str(obj.get("reasoning", "")), str(obj.get("evidence_quote", "")),
            )
        except Exception:
            return self._fallback.interpret_risk(drifts, context)


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    return json.loads(m.group(0) if m else text)


def get_llm(offline: bool | None = None) -> LLMClient:
    """Factory. REAL Apertus is the DEFAULT whenever DRIFT_LLM_* keys are present — the product IS the
    Swiss-sovereign LLM cascade, so we run it, not a mock. ApiLLM auto-falls-back to MockLLM *per call*
    on any endpoint error, so a flaky CSCS degrades gracefully instead of crashing the demo — that's
    resilience, NOT faking the headline.

    MockLLM is used only when there are NO keys (CI/tests — deterministic, network-free) or you
    explicitly force it (DRIFT_LLM_MOCK=1 / offline=True) for a fast local dev loop. For a snappy stage
    demo, PRE-WARM the cache (build each case once) — Apertus reasons them, then the stage serves from
    cache instantly. NOTE: OFFLINE_DEMO is for the INGEST layer (cached fixtures vs live sources); it
    no longer forces the LLM to mock — real reasoning runs regardless of where the events come from.

        DRIFT_LLM_BASE_URL=https://api.swissai.svc.cscs.ch/v1
        DRIFT_LLM_API_KEY=sk-rc-...
        DRIFT_LLM_CHEAP_MODEL=swiss-ai/Apertus-8B-Instruct-2509   # Stage-2 verdict
        DRIFT_LLM_HEAVY_MODEL=swiss-ai/Apertus-70B-Instruct-2509  # Stage-3 deep-dive
    """
    if offline is None:
        offline = os.environ.get("DRIFT_LLM_MOCK", "").strip().lower() in ("1", "true", "yes", "on")
    base, key = os.environ.get("DRIFT_LLM_BASE_URL"), os.environ.get("DRIFT_LLM_API_KEY")
    if not offline and base and key:
        return ApiLLM(base, key,
                      os.environ.get("DRIFT_LLM_CHEAP_MODEL", "swiss-ai/Apertus-8B-Instruct-2509"),
                      os.environ.get("DRIFT_LLM_HEAVY_MODEL", "swiss-ai/Apertus-70B-Instruct-2509"))
    return MockLLM()
