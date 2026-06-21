"""SEC + earnings-call bridge — grain_lite → EvidenceEvent.

The bridge between the grain_lite SEC ingestion (`backend/grain_lite/`) and the drift pipeline.
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
from backend.ingest.base import Connector, CustomerRef, make_event, load_assertions
from backend.ingest.relevance import RelevanceFilter

# Predicates whose drift shows up in filing prose (skip pure-internal ones like volume).
_TEXT_PREDICATES = {
    "business_model", "product_mix", "regulatory_status", "operating_geographies",
    "adverse_media_status", "sanctions_status", "digital_asset_holdings", "digital_asset_policy",
}

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

    def __init__(self, filing_types=("10-K", "8-K"), limit: int = 6, with_earnings: bool = True,
                 with_text: bool = False, text_top_k: int = 1, min_relevance: float = 0.15):
        self.filing_types = list(filing_types)
        self.limit = limit
        self.with_earnings = with_earnings
        self.with_text = with_text          # Level-2: read filing text → cited relevant passages
        self.text_top_k = text_top_k        # passages per assertion
        self.min_relevance = min_relevance  # drop weak matches

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        if not customer.ticker:
            return []  # SEC filings only exist for US-listed entities
        events: list[EvidenceEvent] = []
        events += self._filings(customer)
        if self.with_text:
            events += self._filing_passages(customer)
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

    # --- Level 2: filing text → cited passages relevant to assertions ----- #
    def _filing_passages(self, customer: CustomerRef) -> list[EvidenceEvent]:
        from backend.grain_lite.sources import edgar          # lazy (requests, bs4)
        from backend.grain_lite.chunker import chunk_sec_filing

        assertions = [a for a in load_assertions(customer.customer_id)
                      if a.get("predicate") in _TEXT_PREDICATES]
        if not assertions:
            return []
        # Latest annual report (richest prose); fall back to whatever's available.
        try:
            filings = edgar.fetch_filing_list(customer.ticker, ["10-K"], limit=1)
            if not filings:
                return []
            content = edgar.fetch_filing_content(filings[0])
            chunks = chunk_sec_filing(content.get("raw_text", ""), "10-K")
        except Exception as e:
            print(f"[sec_earnings] Level-2 fetch/chunk failed: {e}")
            return []
        passages = [c.text for c in chunks][:150]              # bound cost
        if not passages:
            return []

        rf = RelevanceFilter()                                 # embeddings if key, else lexical
        f = filings[0]
        events: list[EvidenceEvent] = []
        for a in assertions:
            predicate = a.get("predicate", "")
            query = f"{predicate.replace('_', ' ')}: {a.get('value', '')}"
            top = rf.rank(query, passages, top_k=self.text_top_k)
            for r in top:
                if r.score < self.min_relevance:
                    continue
                quote = " ".join(r.passage.split())[:400]
                events.append(make_event(
                    connector=self.name, customer=customer, type=EvidenceType.NEWS,
                    summary=f"10-K passage relevant to '{predicate}': “{quote[:90]}…”",
                    source="SEC EDGAR · 10-K (full text)",
                    source_url=f.get("url"),
                    published_at=f.get("filing_date"),
                    payload={
                        "form": "10-K",
                        "related_assertion_hint": a.get("id"),   # HINT only — verdict is the engine's
                        "predicate": predicate,
                        "quote": quote,
                        "relevance_score": round(r.score, 3),
                        "relevance_mode": rf.mode,               # 'embedding' or 'lexical' (cost story)
                    },
                    confidence=min(0.9, 0.5 + r.score / 2),
                ))
        print(f"[sec_earnings] Level-2: {len(events)} cited passages ({rf.mode}) from 10-K")
        return events

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
