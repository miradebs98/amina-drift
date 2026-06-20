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

VERDICTS = ("confirms", "contradicts", "irrelevant", "ambiguous")


@dataclass
class Verdict:
    verdict: str          # one of VERDICTS
    strength: float       # [0,1] how strong the (contra)diction is
    rationale: str        # human-readable, grounded in the event
    evidence_quote: str   # the span of the event that justifies it (anti-hallucination checks this)


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


# --- drift keyword set for the offline mock verdict --------------------------------------------
_DRIFT_KW = (
    "crypto", "web3", "bitcoin", "btc", "eth", "stablecoin", "usdc", "token", "brokerage",
    "trading", "custody", "treasury", "digital asset", "offshore", "bvi", "seychelles",
    "expansion", "subsidiary", "stake", "investor", "acquire", "acquires", "round", "funding",
    "pep", "politically exposed", "fraud", "investigation", "probe", "litigation", "scandal",
    "fsra", "unlicensed", "regulated activity", "proceeds",
)
_BREAKABLE = {
    "business_model", "product_mix", "digital_asset_policy", "digital_asset_holdings",
    "operating_geographies", "counterparty_geographies", "ubo", "source_of_funds",
    "source_of_wealth", "regulatory_status", "pep_status", "sanctions_status", "adverse_media_status",
}


class MockLLM(LLMClient):
    """Offline, deterministic stand-in. A clean/narrow onboarding belief is 'contradicted' when a
    drift signal for that predicate appears. (Real ApiLLM returns the same Verdict via a provider.)"""

    tier = "cheap"

    def classify(self, assertion: Assertion, event: EvidenceEvent) -> Verdict:
        text = f"{event.summary} {event.payload}".lower()
        hit = next((kw for kw in _DRIFT_KW if kw in text), None)
        if hit and assertion.predicate.value in _BREAKABLE:
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
        system = ('You are a KYC drift detector for a regulated bank. Decide whether the EVIDENCE '
                  'confirms, contradicts, is irrelevant to, or is ambiguous about the BELIEF. '
                  'Reply with ONLY one JSON object and nothing else: '
                  '{"verdict":"confirms|contradicts|irrelevant|ambiguous","strength":0.0-1.0,'
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


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    return json.loads(m.group(0) if m else text)


def get_llm() -> LLMClient:
    """Factory: ApiLLM if DRIFT_LLM_BASE_URL + DRIFT_LLM_API_KEY are set, else the offline MockLLM.

    Point the cheap/sensitive tier at **Apertus** (Swiss-sovereign) once you have access (Sat 10:00):
        export DRIFT_LLM_BASE_URL=<apertus-openai-compatible-endpoint>
        export DRIFT_LLM_API_KEY=<key>
        export DRIFT_LLM_CHEAP_MODEL=apertus-8b-instruct      # sensitive Layer-2 stays in CH
        export DRIFT_LLM_HEAVY_MODEL=apertus-70b-instruct     # or a frontier model for the deep-dive
    """
    base, key = os.environ.get("DRIFT_LLM_BASE_URL"), os.environ.get("DRIFT_LLM_API_KEY")
    if base and key:
        return ApiLLM(base, key,
                      os.environ.get("DRIFT_LLM_CHEAP_MODEL", "apertus-8b-instruct"),
                      os.environ.get("DRIFT_LLM_HEAVY_MODEL", "apertus-70b-instruct"))
    return MockLLM()
