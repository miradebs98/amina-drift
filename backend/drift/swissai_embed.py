"""Sovereign embeddings via the CSCS Swiss AI API (OpenAI-compatible `/v1/embeddings`).

Apertus is a *generative* model — it can't embed. For the Stage-1 retrieval ("which passage bears
on which belief?") use a real **embedding** model. This one is **Swiss-hosted on CSCS**, so the
sovereign story stays intact (no OpenAI). It reuses the SAME endpoint + key as the LLM.

Drop-in for grain_lite's `Embedder` — same `embed_texts` interface — so Mira's relevance filter can
switch with one env var (`RELEVANCE_EMBEDDINGS=swissai`).

Env (reuses the LLM's by default):
    DRIFT_LLM_BASE_URL / DRIFT_LLM_API_KEY   (or SWISSAI_BASE_URL / SWISSAI_API_KEY)
    SWISSAI_EMBED_MODEL  (default: Snowflake/snowflake-arctic-embed-l-v2.0)
"""
from __future__ import annotations

import os
from typing import List

DEFAULT_MODEL = "Snowflake/snowflake-arctic-embed-l-v2.0"   # verified live on CSCS, 1024-d


class SwissAIEmbedder:
    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.environ.get("SWISSAI_BASE_URL")
                         or os.environ.get("DRIFT_LLM_BASE_URL") or "").rstrip("/")
        self.api_key = (api_key or os.environ.get("SWISSAI_API_KEY")
                        or os.environ.get("DRIFT_LLM_API_KEY") or "")
        self.model = model or os.environ.get("SWISSAI_EMBED_MODEL", DEFAULT_MODEL)
        self.timeout = timeout
        if not (self.base_url and self.api_key):
            raise ValueError("SwissAIEmbedder needs DRIFT_LLM_BASE_URL/API_KEY (or SWISSAI_*) set.")

    def embed_texts(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        import httpx
        out: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = [t if t.strip() else " " for t in texts[i:i + batch_size]]
            r = httpx.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "input": batch}, timeout=self.timeout,
            )
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        return out

    def embed_text(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]
