"""grain_lite LLM cache — file-based (replaces GRAIN's Postgres-backed cache).

Same interface llm_client.py expects: get_cache(), LLMCache.get()/.set(), .enabled.
Caches LLM responses on disk so the demo is cheap + reproducible + offline-friendly.
Cost story: repeated runs over the same (assertion, evidence) pairs cost $0 after the first.
"""

import json
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any

from backend.grain_lite.config import get_config

logger = logging.getLogger("grain_lite.cache")

# On-disk cache dir (git-ignored). Override with GRAIN_CACHE_DIR.
import os
_CACHE_DIR = Path(os.getenv("GRAIN_CACHE_DIR", ".grain_cache"))


class LLMCache:
    """File-based cache for LLM responses (one JSON file per key)."""

    def __init__(self, ttl_hours: int = 24):
        config = get_config()
        self.ttl_hours = ttl_hours
        self.enabled = config.cache.enabled
        self.dir = _CACHE_DIR
        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def _generate_key(self, prompt: str, **metadata) -> str:
        key_data = {"prompt": prompt, **metadata}
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, prompt: str, prompt_type: str = "unknown", **metadata) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        key = self._generate_key(prompt, prompt_type=prompt_type, **metadata)
        p = self._path(key)
        if not p.exists():
            return None
        try:
            entry = json.loads(p.read_text())
            if (time.time() - entry["ts"]) > self.ttl_hours * 3600:
                return None  # expired
            return entry["value"]
        except Exception as e:
            logger.debug(f"cache read miss ({key}): {e}")
            return None

    def set(self, prompt: str, value: Dict[str, Any], prompt_type: str = "unknown",
            tokens_used: int = 0, **metadata) -> None:
        if not self.enabled:
            return
        key = self._generate_key(prompt, prompt_type=prompt_type, **metadata)
        try:
            self._path(key).write_text(json.dumps(
                {"ts": time.time(), "value": value, "tokens_used": tokens_used}
            ))
        except Exception as e:
            logger.debug(f"cache write failed ({key}): {e}")


_cache: Optional[LLMCache] = None


def get_cache() -> LLMCache:
    global _cache
    if _cache is None:
        _cache = LLMCache(ttl_hours=get_config().cache.ttl_hours)
    return _cache
