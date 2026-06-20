"""Live smoke test for the CSCS Swiss AI endpoint — the fully-sovereign path.

    DRIFT_LLM_BASE_URL=https://api.swissai.svc.cscs.ch/v1 \
    DRIFT_LLM_API_KEY=sk-rc-... \
    DRIFT_LLM_CHEAP_MODEL=swiss-ai/Apertus-8B-Instruct-2509 \
    DRIFT_LLM_HEAVY_MODEL=swiss-ai/Apertus-70B-Instruct-2509 \
    python backend/drift/smoke_apertus.py

Confirms, all on Swiss CSCS infra (no OpenAI): the 8B verdict, the 70B explanation, and the
arctic-embed sovereign embeddings. Exits 0 = green. Skips (0) if env isn't set, so CI stays offline-safe.
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from backend.drift.llm import get_llm, ApiLLM
from backend.drift.swissai_embed import SwissAIEmbedder
from backend.drift.classify import classify_event
from backend.drift.client_state import load_client_state_from_fixtures


def main() -> int:
    if not (os.environ.get("DRIFT_LLM_BASE_URL") and os.environ.get("DRIFT_LLM_API_KEY")):
        print("⚠️  DRIFT_LLM_BASE_URL + DRIFT_LLM_API_KEY not set — skipping live smoke (offline-safe).")
        return 0

    llm = get_llm()
    assert isinstance(llm, ApiLLM), "env set but get_llm() returned the mock — check DRIFT_LLM_*"

    st = load_client_state_from_fixtures("meridian-sands")
    A = next(a for a in st.assertions if a.predicate.value == "product_mix")
    E = next(e for e in st.evidence if "crypto" in (e.summary + str(e.payload)).lower())

    v = classify_event(A, E, llm)
    print(f"✓ verdict   [{llm.cheap_model}]  -> {v.verdict} (strength={v.strength})")
    assert v.verdict == "contradicts", f"expected contradicts, got {v.verdict}"
    assert v.evidence_quote, "verdict must be grounded by a cited span"

    exp = llm.synthesize("One sentence: a SaaS startup pivoted to crypto trading — why is that a KYC risk?")
    print(f"✓ explain   [{llm.heavy_model}]  -> {exp[:110]}")
    assert len(exp) > 20

    emb = SwissAIEmbedder().embed_texts(["crypto brokerage product", "saas analytics subscriptions"])
    print(f"✓ embeddings[{SwissAIEmbedder().model}]  -> {len(emb)} vecs, dim {len(emb[0])}")
    assert len(emb[0]) > 100

    m = llm.meter
    print(f"✓ cost      cheap={m.cheap_calls} heavy={m.heavy_calls} tokens={m.total_tokens}")
    print("\n✅ ALL SOVEREIGN CHECKS PASSED — verdict + explain + embeddings, 100% on CSCS, no OpenAI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
