"""Certificate Transparency — the 'digital exhaust' connector (free, no key, novel).

Every TLS certificate a company issues is logged publicly (CT logs). crt.sh exposes them. By
reading a customer's certs over time we see the **infrastructure they spin up** — new subdomains
like `otc.`, `global.`, `mena.`, `custody.`, `derivatives.` — often MONTHS before any press release
or website change. It's the earliest, cheapest signal of a product/jurisdiction expansion.

Almost nobody mines CT for KYC. For a startup this is gold: the pivot shows up in the infra first.
Emits WEBSITE_CHANGE events (Contextual dimension) dated at the cert's first-seen date.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from shared.schemas import EvidenceEvent, EvidenceType
from backend.ingest.base import Connector, CustomerRef, make_event

CRT_URL = "https://crt.sh/?q=%25.{domain}&output=json&exclude=expired"

# subdomain token -> what it usually signals (product / jurisdiction / capability expansion)
_SIGNAL = {
    "otc": "OTC trading desk", "exchange": "exchange platform", "trade": "trading platform",
    "pro": "pro/advanced trading", "global": "global expansion", "mena": "Middle East expansion",
    "dubai": "UAE/Dubai expansion", "eu": "EU expansion", "sg": "Singapore presence",
    "jp": "Japan presence", "custody": "custody product", "wallet": "wallet/custody",
    "pay": "payments", "card": "card product", "chain": "own blockchain / L1",
    "defi": "DeFi", "token": "tokenisation", "earn": "yield / earn product", "stake": "staking",
    "derivativ": "derivatives", "futures": "derivatives / futures", "bank": "banking",
    "institution": "institutional desk", "prime": "prime brokerage", "fund": "fund / asset mgmt",
}


class CertTransparencyConnector(Connector):
    name = "cert_transparency"
    source_label = "Certificate Transparency (crt.sh)"

    def __init__(self, max_signals: int = 8):
        self.max_signals = max_signals

    def fetch(self, customer: CustomerRef) -> list[EvidenceEvent]:
        if not customer.domain:
            return []
        url = CRT_URL.format(domain=urllib.parse.quote(customer.domain))
        req = urllib.request.Request(url, headers={"User-Agent": "amina-drift/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                rows = json.loads(r.read().decode("utf-8", "replace") or "[]")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            print(f"[cert_transparency] crt.sh unreachable ({type(e).__name__}) → skipping")
            return []
        except Exception as e:
            print(f"[cert_transparency] parse failed ({type(e).__name__}) → skipping")
            return []

        # subdomain prefix -> earliest cert date observed
        first_seen: dict[str, str] = {}
        for row in rows:
            when = (row.get("not_before") or "")[:10]
            for name in (row.get("name_value") or "").split("\n"):
                name = name.strip().lstrip("*.").lower()
                if not name.endswith(customer.domain) or name == customer.domain:
                    continue
                prefix = name[: -(len(customer.domain) + 1)]            # strip ".domain"
                if not prefix or prefix in ("www",):
                    continue
                if prefix not in first_seen or when < first_seen[prefix]:
                    first_seen[prefix] = when

        # keep only the SIGNAL subdomains (infra that implies a product/jurisdiction move)
        signals = []
        for prefix, when in first_seen.items():
            hit = next((meaning for tok, meaning in _SIGNAL.items() if tok in prefix), None)
            if hit:
                signals.append((when, prefix, hit))
        signals.sort()  # by first-seen date (oldest first)

        out: list[EvidenceEvent] = []
        for when, prefix, meaning in signals[: self.max_signals]:
            out.append(make_event(
                connector=self.name, customer=customer, type=EvidenceType.WEBSITE_CHANGE,
                summary=f"New infrastructure '{prefix}.{customer.domain}' first seen in cert logs — suggests {meaning}",
                source="Certificate Transparency (crt.sh)",
                source_url=f"https://crt.sh/?q=%25.{customer.domain}",
                published_at=when or "2024-01-01",
                payload={"subdomain": f"{prefix}.{customer.domain}", "first_seen": when,
                         "inferred_signal": meaning,
                         "note": "Infrastructure observed via TLS certs BEFORE any announcement (digital exhaust)."},
                confidence=0.6, resolution_confidence=0.85,
            ))
        print(f"[cert_transparency] {len(first_seen)} subdomains, {len(out)} infra signals")
        return out
