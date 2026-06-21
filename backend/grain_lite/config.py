"""
grain_lite Configuration

Reads from backend environment variables (loaded by dotenv in run_local.py).
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    """LLM (OpenAI) configuration."""
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    embedding_model: str = field(default_factory=lambda: os.getenv("GRAIN_EMBEDDING_MODEL", "text-embedding-3-small"))
    llm_model: str = field(default_factory=lambda: os.getenv("GRAIN_LLM_MODEL", "gpt-4.1-mini"))
    llm_temperature: float = field(default_factory=lambda: float(os.getenv("GRAIN_LLM_TEMPERATURE", "0.1")))

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)


@dataclass
class VectorStoreConfig:
    """GCS-backed vector store configuration (with local file fallback)."""
    gcs_bucket: str = field(default_factory=lambda: os.getenv("GRAIN_GCS_BUCKET", "vectors"))
    gcs_prefix: str = field(default_factory=lambda: os.getenv("GRAIN_GCS_PREFIX", "vectors"))
    local_file: str = field(default_factory=lambda: os.getenv("GRAIN_LOCAL_VECTOR_FILE", ""))


@dataclass
class CacheConfig:
    """LLM response caching configuration."""
    enabled: bool = field(default_factory=lambda: os.getenv("GRAIN_CACHE_ENABLED", "true").lower() == "true")
    ttl_hours: int = field(default_factory=lambda: int(os.getenv("GRAIN_CACHE_TTL_HOURS", "24")))


@dataclass
class RerankConfig:
    """LLM Reranking configuration."""
    enabled: bool = field(default_factory=lambda: os.getenv("GRAIN_RERANK_ENABLED", "true").lower() == "true")
    model: str = field(default_factory=lambda: os.getenv("GRAIN_RERANK_MODEL", "gpt-4.1-mini"))
    weight: float = field(default_factory=lambda: float(os.getenv("GRAIN_RERANK_WEIGHT", "0.7")))
    max_chunks: int = field(default_factory=lambda: int(os.getenv("GRAIN_RERANK_MAX_CHUNKS", "100")))


@dataclass
class ScoringConfig:
    """Exposure scoring configuration (ordinal 5-tier system)."""
    mode: str = field(default_factory=lambda: os.getenv("GRAIN_SCORING_MODE", "ordinal"))
    model: str = field(default_factory=lambda: os.getenv("GRAIN_SCORING_MODEL", "gpt-4.1-mini"))


@dataclass
class GrainConfig:
    """Main grain_lite configuration."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    vector_store: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)

    # Temporary data directory for raw filings cache (fetched from SEC, processed, then discarded)
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("GRAIN_DATA_DIR", "/tmp/grain_data")))

    @property
    def edgar_dir(self) -> Path:
        """Path to temporary EDGAR filings cache."""
        return self.data_dir / "raw_filings"

    # base_dir alias for backward compatibility with existing grain_lite modules
    @property
    def base_dir(self) -> Path:
        return self.data_dir

    @property
    def prompts_dir(self) -> Path:
        """Path to LLM prompts directory (shipped with the package)."""
        return Path(__file__).parent / "llm" / "prompts"

    def validate(self) -> list:
        """Validate configuration and return list of issues."""
        issues = []
        if not self.llm.has_openai:
            issues.append("OPENAI_API_KEY not set (required for embeddings and scoring)")
        return issues


# Global config instance
_config: Optional[GrainConfig] = None


def get_config() -> GrainConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = GrainConfig()
    return _config
