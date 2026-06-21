"""ClientState — the per-customer 'living representation' the engine reads.

PROPOSED read model (the glue between lanes): the union of the shared contracts for one customer.
In production, storage materializes this from SQLite; here we assemble it from the customer
+ events fixtures so the engine runs offline. Snapshots are mocked until the Wayback snapshot feed lands.

→ KICKOFF: agree this shape and move it to shared/schemas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from shared.schemas import Assertion, EvidenceEvent, Snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]

# customer_id -> events fixture file
_EVENTS_FILE = {
    "meridian-sands": "meridian-events.example.json",
    "coinbase": "coinbase-events.example.json",
}


@dataclass
class ClientState:
    customer_id: str
    legal_name: str
    onboarded_as_of: date
    baseline_risk_score: int           # the rolled-up 0–100 KYC score at onboarding (the prior)
    assertions: list[Assertion]
    evidence: list[EvidenceEvent]
    snapshots: list[Snapshot]
    dossier: str = ""                  # rolling compacted summary (compaction handled in prod)


def load_client_state_from_fixtures(customer_id: str = "meridian-sands") -> ClientState:
    cust = _load_json(REPO_ROOT / "data" / "customers" / f"{customer_id}.json")

    # assertions, minus the rolled-up outputs (risk_score/risk_tier are produced, not consumed)
    assertions = [Assertion(**a) for a in cust["assertions"]]

    events_file = _EVENTS_FILE.get(customer_id, f"{customer_id}-events.example.json")
    events = [EvidenceEvent(**e) for e in _load_json(REPO_ROOT / "data" / "fixtures" / events_file)["events"]]
    events.sort(key=lambda e: e.published_at)

    snapshots = _MOCK_SNAPSHOTS.get(customer_id, lambda c: [])(customer_id)

    return ClientState(
        customer_id=customer_id,
        legal_name=cust.get("legal_name", customer_id),
        onboarded_as_of=date.fromisoformat(cust["onboarded_as_of"]),
        baseline_risk_score=_baseline_score(cust, assertions),
        assertions=assertions,
        evidence=events,
        snapshots=snapshots,
    )


def _baseline_score(cust: dict, assertions: list[Assertion]) -> int:
    rm = cust.get("risk_model", {})
    if "onboarding_score" in rm:
        return int(rm["onboarding_score"])
    for a in assertions:
        if a.predicate.value == "risk_score":
            try:
                return int(str(a.value).strip())
            except ValueError:
                pass
    return 30


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _meridian_snapshots(customer_id: str) -> list[Snapshot]:
    """MOCK reconstructed public-profile snapshots for Meridian Sands (real Wayback replaces these).

    signal_mix lives in config.CONCEPT_AXES space. Trajectory migrates SaaS→crypto, UAE→offshore.
    """
    rows = [
        # as_of,        saas, crypto, offshore, uae, description
        ("2023-01-15", 0.95, 0.00, 0.00, 1.00, "B2B SaaS — financial-data analytics for UAE SMEs. ADGM, UAE-only."),
        ("2023-11-15", 0.70, 0.35, 0.00, 0.95, "Website pivots messaging toward 'Web3 trading infrastructure'."),
        ("2024-03-10", 0.60, 0.40, 0.45, 0.70, "Opens a BVI offshore subsidiary; expansion beyond UAE."),
        ("2024-09-05", 0.45, 0.60, 0.50, 0.60, "US$22M round; proceeds earmarked for a crypto trading desk."),
        ("2025-01-20", 0.35, 0.78, 0.55, 0.50, "Launches a retail crypto brokerage product (regulated activity)."),
        ("2026-02-18", 0.25, 0.90, 0.60, 0.40, "Adopts a corporate crypto treasury (BTC/ETH/USDC)."),
    ]
    snaps = []
    for as_of, saas, crypto, off, uae, desc in rows:
        snaps.append(Snapshot(
            customer_id=customer_id, as_of=date.fromisoformat(as_of),
            business_description=desc, domain="meridiansands.example",
            domicile="ADGM, AE", legal_form="ADGM Private Company Limited by Shares",
            signal_mix={"saas_analytics": saas, "crypto_web3": crypto,
                        "offshore_expansion": off, "uae_domestic": uae},
            source_urls=[],
        ))
    return snaps


_MOCK_SNAPSHOTS = {"meridian-sands": _meridian_snapshots}
