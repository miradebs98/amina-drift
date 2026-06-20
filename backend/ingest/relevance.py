"""Stage-1 relevance filter — the cheap gate.

Given a query (e.g. an assertion) and candidate passages, return the most relevant passages.
This is exactly the cost cascade's Stage 1: a cheap pass that decides what's even worth deeper
(LLM) analysis — so the frontier model only ever sees a handful of passages, not whole filings.

DEFAULT = lexical token-overlap (FREE, no key, no network, no surprise charges). The mode is set
explicitly via env `RELEVANCE_EMBEDDINGS`:
  - unset / "lexical"  → lexical            (default, free)
  - "local"            → free local sentence-transformers   ← see SHARED-EMBEDDER note below
  - "openai"           → OpenAI embeddings  (PAID — explicit opt-in only)

We do NOT auto-enable OpenAI just because a key exists (that would be a silent-cost footgun).

── SHARED-EMBEDDER NOTE (for Miguel) ──────────────────────────────────────────────────────────
A single FREE local `sentence-transformers` model (e.g. all-MiniLM-L6-v2, ~90MB, CPU, offline)
could serve BOTH:
  • Mira's retrieval here (set RELEVANCE_EMBEDDINGS=local), and
  • Miguel's slow-drift trajectory (swap `drift/embeddings.py::ConceptAxisEmbedder` for it).
Miguel already notes his embedder is swappable. If we want embedding-quality for free, wire the
local model once and both lanes use it. Keep Miguel's concept-axis version for the explainability
pitch; use the local model where semantic similarity matters (retrieval). Not built yet — note only.

`mode` records which path ran (shown in event payload for the cost story on stage).
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "as", "is", "are",
    "be", "by", "at", "from", "that", "this", "its", "it", "we", "our", "their", "no", "not",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 2]


@dataclass
class Ranked:
    index: int
    score: float
    passage: str


class RelevanceFilter:
    def __init__(self):
        self.mode = "lexical"           # FREE default
        self._embedder = None
        choice = os.getenv("RELEVANCE_EMBEDDINGS", "lexical").lower()
        if choice == "openai":          # PAID — explicit opt-in only
            try:
                from backend.grain_lite.config import get_config
                if get_config().llm.has_openai:
                    from backend.grain_lite.embedder import get_embedder
                    self._embedder = get_embedder()
                    self.mode = "embedding(openai)"
                else:
                    print("[relevance] RELEVANCE_EMBEDDINGS=openai but no OPENAI_API_KEY → lexical")
            except Exception as e:
                print(f"[relevance] openai embedder init failed ({e}) → lexical")
        elif choice == "local":         # FREE local model — not wired yet (see note in module docstring)
            print("[relevance] RELEVANCE_EMBEDDINGS=local not wired yet → lexical (free). "
                  "Wire sentence-transformers to enable; see SHARED-EMBEDDER note.")
        # else: lexical (default, free)

    # --- public ---------------------------------------------------------- #
    def rank(self, query: str, passages: list[str], top_k: int = 3) -> list[Ranked]:
        if not passages:
            return []
        scores = (self._rank_embedding(query, passages) if self._embedder
                  else self._rank_lexical(query, passages))
        ranked = sorted(
            (Ranked(i, s, passages[i]) for i, s in enumerate(scores)),
            key=lambda r: r.score, reverse=True,
        )
        return ranked[:top_k]

    # --- embedding path -------------------------------------------------- #
    def _rank_embedding(self, query: str, passages: list[str]) -> list[float]:
        from backend.grain_lite.embedder import cosine_similarity
        try:
            vecs = self._embedder.embed_texts([query] + passages)
            qv, pvs = vecs[0], vecs[1:]
            return [cosine_similarity(qv, pv) for pv in pvs]
        except Exception as e:
            print(f"[relevance] embedding failed ({type(e).__name__}); lexical fallback: {e}")
            self.mode = "lexical"
            return self._rank_lexical(query, passages)

    # --- lexical fallback ------------------------------------------------ #
    def _rank_lexical(self, query: str, passages: list[str]) -> list[float]:
        q = set(_tokens(query))
        if not q:
            return [0.0] * len(passages)
        out = []
        for p in passages:
            pt = _tokens(p)
            if not pt:
                out.append(0.0)
                continue
            overlap = sum(1 for t in pt if t in q)
            # tf-ish, length-normalised
            out.append(overlap / math.sqrt(len(pt)))
        return out
