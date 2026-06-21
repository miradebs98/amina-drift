"""Connector framework — every Layer-1 source emits the SAME `EvidenceEvent` shape.

Add a source = subclass `Connector`, implement `fetch(customer) -> list[EvidenceEvent]`.
The runner handles caching, the offline switch, and merging. Connectors stay DUMB: they emit
facts (with a `source_url` citation); the drift engine decides what they mean.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared.schemas import EvidenceEvent, EvidenceType

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "data" / "fixtures"
CUSTOMERS_DIR = REPO_ROOT / "data" / "customers"

# Load .env (repo root) so OPENAI_API_KEY / SEC_USER_AGENT / ALPHAVANTAGE_API_KEY are picked up.
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass


def load_assertions(customer_id: str) -> list[dict]:
    """Return the authored assertions for a customer (used as relevance queries in Level-2)."""
    for p in CUSTOMERS_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        if data.get("customer_id") == customer_id:
            return data.get("assertions", [])
    return []


def offline() -> bool:
    """Offline demo mode: connectors replay cached fixtures, no network."""
    return os.getenv("OFFLINE_DEMO", "true").lower() == "true"


# --------------------------------------------------------------------------- #
# Customer identity — what a connector needs to query its source
# --------------------------------------------------------------------------- #
@dataclass
class CustomerRef:
    customer_id: str
    legal_name: str
    ticker: Optional[str] = None
    cik: Optional[str] = None
    lei: Optional[str] = None
    domain: Optional[str] = None
    country: Optional[str] = None
    aliases: list[str] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: Path) -> "CustomerRef":
        data = json.loads(Path(path).read_text())
        ep = data.get("entity_profile", {})
        # ticker: first UPPERCASE token that isn't an exchange/qualifier, e.g. "NASDAQ: COIN (...)"
        ticker = None
        tkr_raw = ep.get("ticker", "")
        if tkr_raw:
            _skip = {"NASDAQ", "NYSE", "SEC", "EDGAR", "LSE", "OTC"}
            for tok in re.findall(r"\b([A-Z]{2,6})\b", tkr_raw.split("(")[0]):
                if tok not in _skip:
                    ticker = tok
                    break
        # cik: leading digit run (a 10-digit CIK is real even if the note says "VERIFY")
        cik = None
        m = re.search(r"\d{6,10}", str(ep.get("sec_cik", "")))
        if m:
            cik = m.group(0).zfill(10)
        lei = ep.get("lei")
        if lei and ("VERIFY" in lei.upper() or "n/a" in lei.lower()):
            lei = None
        domain = None
        site = ep.get("website", "")
        if site:
            domain = re.sub(r"^https?://(www\.)?", "", site).split("/")[0] or None
        return cls(
            customer_id=data["customer_id"],
            legal_name=data.get("legal_name", data["customer_id"]),
            ticker=ticker,
            cik=cik,
            lei=lei,
            domain=domain,
            country=ep.get("country_of_incorporation"),
        )

    @classmethod
    def load(cls, customer_id: str) -> "CustomerRef":
        for p in CUSTOMERS_DIR.glob("*.json"):
            try:
                if json.loads(p.read_text()).get("customer_id") == customer_id:
                    return cls.from_file(p)
            except Exception:
                continue
        raise FileNotFoundError(f"No customer file for '{customer_id}' in {CUSTOMERS_DIR}")


# --------------------------------------------------------------------------- #
# Event construction — one helper so every connector produces identical shape
# --------------------------------------------------------------------------- #
def _stable_id(prefix: str, *parts: str) -> str:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:10]
    return f"{prefix}-{h}"


def _as_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    s = str(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y%m%d", "%Y%m%d%H%M%S"):
        try:
            dt = datetime.strptime(s.replace("Z", "+0000") if fmt.endswith("%z") else s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def make_event(
    *,
    connector: str,
    customer: CustomerRef,
    type: EvidenceType,
    summary: str,
    source: str,
    source_url: Optional[str],
    published_at,
    payload: Optional[dict] = None,
    confidence: float = 0.8,
    resolution_confidence: Optional[float] = 0.9,
    entity_ref: Optional[str] = None,
) -> EvidenceEvent:
    """Build a schema-valid EvidenceEvent. `customer_id` is stamped here (already resolved
    because we queried the source BY this customer's identifiers)."""
    return EvidenceEvent(
        id=_stable_id(connector, customer.customer_id, summary, str(published_at)),
        entity_ref=entity_ref or customer.legal_name,
        customer_id=customer.customer_id,
        resolution_confidence=resolution_confidence,
        type=type,
        summary=summary,
        payload=payload or {},
        source=source,
        source_url=source_url,
        published_at=_as_dt(published_at),
        confidence=confidence,
    )


# --------------------------------------------------------------------------- #
# Connector base
# --------------------------------------------------------------------------- #
class Connector(ABC):
    name: str = "connector"           # short id, used for event id prefix + cache file
    source_label: str = "Source"      # human label for EvidenceEvent.source
    live: bool = True                 # False for fixture-only / stub connectors

    @abstractmethod
    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        """Query the source for one customer and return EvidenceEvents (may be empty)."""
        ...

    def cache_path(self, customer: CustomerRef) -> Path:
        return FIXTURES_DIR / f"{customer.customer_id}.{self.name}.cache.json"

    def fetch_cached(self, customer: CustomerRef, refresh: bool = False) -> list[EvidenceEvent]:
        """Live fetch with disk cache → offline-safe demo. On any error, fall back to cache."""
        cache = self.cache_path(customer)
        if not refresh and cache.exists():
            return [EvidenceEvent(**e) for e in json.loads(cache.read_text())]
        try:
            events = self.fetch(customer)
        except Exception as e:  # network/dep failure → degrade gracefully
            if cache.exists():
                return [EvidenceEvent(**e) for e in json.loads(cache.read_text())]
            print(f"[{self.name}] fetch failed ({type(e).__name__}: {e}); no cache → 0 events")
            return []
        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([json.loads(e.model_dump_json()) for e in events], indent=2))
        return events
