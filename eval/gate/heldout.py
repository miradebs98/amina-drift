"""HELD-OUT generalization test for the Stage-1 gate.

The keyword vocab was TUNED on Circle/Ripple/Kraken/Revolut — so testing on them is training-on-test.
This runs the improved `is_candidate` BLIND on 3 companies it was never tuned for, fed by the REAL
ingestion connectors (Google News — free, no API key, no LLM). For each real news item it prints
which beliefs the gate KEEPS vs DROPS, so we can eyeball whether it routes correctly and stays cheap.

  python -m eval.gate.heldout
"""
from __future__ import annotations

from datetime import date
from shared.schemas import Assertion, EvidenceEvent
from backend.ingest.base import CustomerRef
from backend.ingest.news_rss import NewsRssConnector
from backend.ingest.funding import FundingConnector
from backend.drift.classify import is_candidate

# 3 held-out firms (NOT in the tuning set). Klarna is deliberately NON-crypto (generalization).
HELDOUT = [
    {"id": "binance", "name": "Binance", "domain": "binance.com",
     "beliefs": {
         "business_model": "Global crypto exchange and trading platform",
         "product_mix": "Crypto spot, derivatives and staking; no banking",
         "operating_geographies": {"value": "Global", "allowed_set": ["MT", "AE"]},
         "regulatory_status": "Patchwork registrations; not bank-chartered; under regulatory scrutiny",
         "ubo": "Founder Changpeng Zhao (CZ), majority owner",
         "source_of_wealth": "Exchange trading fees",
         "digital_asset_policy": "Holds large crypto reserves (BNB, BTC)",
         "pep_status": "No PEP among directors or UBOs",
         "sanctions_status": "No sanctions exposure",
         "adverse_media_status": "Regulatory scrutiny; no convictions on file",
     }},
    {"id": "klarna", "name": "Klarna", "domain": "klarna.com",
     "beliefs": {
         "business_model": "Buy-now-pay-later consumer-credit fintech",
         "product_mix": "BNPL instalments and payments; not a full bank",
         "operating_geographies": {"value": "Sweden and EU", "allowed_set": ["SE", "EU"]},
         "regulatory_status": "Swedish/EU banking licence; FCA registration",
         "ubo": "Founder Sebastian Siemiatkowski; Sequoia and SoftBank investors",
         "source_of_wealth": "Venture funding and merchant fees",
         "listing_status": "Private company (IPO plans)",
         "pep_status": "No PEP among directors or UBOs",
         "sanctions_status": "No sanctions exposure",
         "adverse_media_status": "No material adverse media",
     }},
    {"id": "robinhood", "name": "Robinhood", "domain": "robinhood.com",
     "beliefs": {
         "business_model": "US commission-free retail brokerage app",
         "product_mix": "Stocks, options and crypto trading; no banking",
         "operating_geographies": {"value": "US", "allowed_set": ["US"]},
         "regulatory_status": "SEC/FINRA broker-dealer; under regulatory scrutiny",
         "ubo": "Founders Vlad Tenev and Baiju Bhatt; publicly listed",
         "listing_status": "Public company (NASDAQ: HOOD)",
         "digital_asset_policy": "Offers crypto trading to customers",
         "pep_status": "No PEP among directors or UBOs",
         "sanctions_status": "No sanctions exposure",
         "adverse_media_status": "No material adverse media",
     }},
]


def mk_assertions(cid, beliefs):
    out = []
    for pred, val in beliefs.items():
        env = None
        if isinstance(val, dict):
            env = {"allowed_set": val.get("allowed_set"), "unit": "country"}
            val = val["value"]
        out.append(Assertion(id=f"{cid}-{pred}", customer_id=cid, predicate=pred, value=val,
                             expected_envelope=env, as_of=date(2023, 1, 1), last_verified=date(2023, 1, 1),
                             source="onboarding (heldout eval)", confidence=0.9, status="valid"))
    return out


def fetch_real_news(co):
    ref = CustomerRef(customer_id=co["id"], legal_name=co["name"], domain=co["domain"])
    events = []
    for conn in (NewsRssConnector(max_records=14), FundingConnector(max_records=6)):
        try:
            events += conn.fetch(ref)
        except Exception as e:
            print(f"   [{conn.name}] fetch error: {type(e).__name__}: {e}")
    # de-dup by summary
    seen, uniq = set(), []
    for e in events:
        k = e.summary.lower()[:80]
        if k not in seen:
            seen.add(k); uniq.append(e)
    return uniq


for co in HELDOUT:
    print(f"\n{'='*78}\n{co['name'].upper()}  (held-out — gate never tuned on it)\n{'='*78}")
    A = mk_assertions(co["id"], co["beliefs"])
    events = fetch_real_news(co)
    print(f"{len(events)} real news items from the connectors\n")
    for e in events:
        kept = [a.predicate.value for a in A if is_candidate(a, e)]
        dropped = [a.predicate.value for a in A if a.predicate.value not in kept]
        # adverse_media is always-kept by design; show the *interesting* routing separately
        kept_ex = [k for k in kept if k != "adverse_media_status"]
        print(f"• {e.summary[:96]}")
        print(f"    KEEP: {kept_ex if kept_ex else '(adverse-media only)'}")
        print(f"    drop: {dropped}\n")
