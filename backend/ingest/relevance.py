"""Stage-1 relevance filter — the cheap gate (embeddings, or lexical fallback).

Given a query (e.g. an assertion) and candidate passages, return the most relevant passages.
This is exactly the cost cascade's Stage 1: a cheap pass that decides what's even worth deeper
(LLM) analysis — so the frontier model only ever sees a handful of passages, not whole filings.

  - If OPENAI_API_KEY is set → OpenAI embeddings + cosine (grain_lite.embedder).
  - Else → lexical token-overlap scoring (no key, no network) so it always runs.

`mode` records which path ran (for the cost story on stage).
"""
from __future__ import annotations

import math
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
        self.mode = "lexical"
        self._embedder = None
        try:
            from backend.grain_lite.config import get_config
            if get_config().llm.has_openai:
                from backend.grain_lite.embedder import get_embedder
                self._embedder = get_embedder()
                self.mode = "embedding"
        except Exception:
            self.mode = "lexical"

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
