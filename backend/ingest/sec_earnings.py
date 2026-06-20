"""SEC + earnings-call bridge — grain_lite → EvidenceEvent.

The bridge between Sablier's GRAIN ingestion (`backend/grain_lite/`) and our drift pipeline.
Best for Coinbase (real, listed). Two levels:

  Level 1 (KEYLESS, always on): SEC EDGAR filing list → one EvidenceEvent per recent filing
     (form, date, official URL). Needs only SEC_USER_AGENT. This already gives the engine real,
     cited evidence to classify.

  Level 2 (needs OPENAI_API_KEY): download filing text → chunk → embed → keep the passages most
     relevant to the customer's assertions → richer EvidenceEvents carrying the cited passage.
     (Optional enhancement; off by default. This is where grain_lite's embedder = our Stage-1.)

  Earnings (needs ALPHAVANTAGE_API_KEY): earnings-call transcripts → EvidenceEvents. Super
     relevant for business-model / regulatory drift signals.

All heavy imports are LAZY so the framework loads without optional deps/keys.
"""
from __future__ import annotations

import os

from shared.schemas import EvidenceEvent, EvidenceType
from backend.ingest.base import Connector, CustomerRef, make_event

# 8-K = material event; 10-K = annual; DEF 14A = proxy/ownership. Map to our enum:
_FORM_TYPE = {
    "8-K": EvidenceType.NEWS,
    "10-K": EvidenceType.NEWS,
    "10-Q": EvidenceType.NEWS,
    "DEF 14A": EvidenceType.OWNERSHIP_CHANGE,
}
_FORM_DESC = {
    "8-K": "material-event filing",
    "10-K": "annual report",
    "10-Q": "quarterly report",
    "DEF 14A": "proxy statement (ownership/governance)",
}


class SecEarningsConnector(Connector):
    name = "sec_earnings"
    source_label = "SEC EDGAR"

    def __init__(self, filing_types=("10-K", "8-K"), limit: int = 6, with_earnings: bool = True):
        self.filing_types = list(filing_types)
        self.limit = limit
        self.with_earnings = with_earnings

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        if not customer.ticker:
            return []  # SEC filings only exist for US-listed entities
        events: list[EvidenceEvent] = []
        events += self._filings(customer)
        if self.with_earnings and os.getenv("ALPHAVANTAGE_API_KEY"):
            events += self._earnings(customer)
        return events

    # --- Level 1: keyless filing list ------------------------------------- #
    def _filings(self, customer: CustomerRef) -> list[EvidenceEvent]:
        from backend.grain_lite.sources import edgar  # lazy (needs requests)

        filings = edgar.fetch_filing_list(customer.ticker, self.filing_types, limit=self.limit)
        out = []
        for f in filings:
            form = f.get("form", "?")
            desc = _FORM_DESC.get(form, "SEC filing")
            out.append(make_event(
                connector=self.name,
                customer=customer,
                type=_FORM_TYPE.get(form, EvidenceType.NEWS),
                summary=f"{customer.legal_name} filed a {form} ({desc}) with the SEC",
                source="SEC EDGAR",
                source_url=f.get("url"),
                published_at=f.get("filing_date"),
                payload={"form": form, "accession": f.get("accession"), "cik": f.get("cik")},
                confidence=0.95, resolution_confidence=1.0,
            ))
        return out

    # --- Earnings-call transcripts (Alpha Vantage) ------------------------ #
    def _earnings(self, customer: CustomerRef) -> list[EvidenceEvent]:
        from backend.grain_lite.sources.transcript import EarningsTranscriptSource  # lazy

        try:
            src = EarningsTranscriptSource()
            result = src.fetch(customer.ticker)
            docs = getattr(result, "documents", []) or []
        except Exception as e:
            print(f"[sec_earnings] earnings fetch failed: {e}")
            return []
        out = []
        for d in docs[: self.limit]:
            period = getattr(d, "fiscal_period", None) or "recent quarter"
            out.append(make_event(
                connector=self.name,
                customer=customer,
                type=EvidenceType.NEWS,
                summary=f"{customer.legal_name} earnings call ({period}) transcript available",
                source="Alpha Vantage (earnings call)",
                source_url=None,
                published_at=getattr(d, "filing_date", None) or "2025-01-01",
                payload={"fiscal_period": period, "excerpt": (getattr(d, "content", "") or "")[:400]},
                confidence=0.85,
            ))
        return out
