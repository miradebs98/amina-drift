"""Proves the Layer-1/Layer-2 data-separation + masking policy and the audited reveal.

Run: pytest backend/govern/test_data_policy.py -q
Uses a throwaway audit DB (GOVERN_DB) so it never touches the real govern.sqlite.
"""
from __future__ import annotations

import os
import tempfile

# Point the audit log at a temp DB BEFORE importing anything that imports govern.audit.
os.environ["GOVERN_DB"] = os.path.join(tempfile.mkdtemp(), "test_govern.sqlite")

from fastapi.testclient import TestClient  # noqa: E402

from backend.govern import audit, data_policy  # noqa: E402
from backend.api import main  # noqa: E402


def _sample_customer() -> dict:
    return {
        "customer_id": "test-co",
        "legal_name": "Test Co",
        "entity_profile": {"website": "https://test.co", "entity_tin": "TIN-999"},
        "assertions": [
            {"id": "A1", "predicate": "ubo", "value": "Jane Real Owner (100%)"},
            {"id": "A2", "predicate": "business_model", "value": "SaaS"},
            {"id": "A3", "predicate": "source_of_funds", "value": "VC funding round"},
        ],
    }


# ── unit: masking ────────────────────────────────────────────────────────────
def test_mask_hides_restricted_and_keeps_public():
    masked = data_policy.mask_customer(_sample_customer())
    by_id = {a["id"]: a for a in masked["assertions"]}
    assert by_id["A1"]["value"] == data_policy.MASK_TOKEN          # ubo masked
    assert by_id["A3"]["value"] == data_policy.MASK_TOKEN          # source_of_funds masked
    assert by_id["A2"]["value"] == "SaaS"                          # business_model untouched (public)
    assert masked["entity_profile"]["entity_tin"] == data_policy.MASK_TOKEN
    assert masked["entity_profile"]["website"] == "https://test.co"
    # the mask token must not look like JSON (the UI's value formatter only parses leading "{")
    assert not data_policy.MASK_TOKEN.lstrip().startswith("{")


def test_mask_never_mutates_the_source():
    cust = _sample_customer()
    data_policy.mask_customer(cust)
    assert cust["assertions"][0]["value"] == "Jane Real Owner (100%)"   # original intact
    assert cust["entity_profile"]["entity_tin"] == "TIN-999"


def test_can_reveal_rbac():
    assert not data_policy.can_reveal("analyst")
    assert data_policy.can_reveal("mlro")
    assert data_policy.can_reveal("compliance")
    assert data_policy.can_reveal("admin")
    assert not data_policy.can_reveal(None)


# ── API: GET masking is secure-by-default and never mutates the cache ─────────
def test_api_masks_by_default_and_unmasks_for_authorised_role():
    client = TestClient(main.app)
    main._CASE_CACHE["test-co"] = {"customer": _sample_customer(), "events": [], "alert": {}}

    analyst = client.get("/cases/test-co").json()
    assert analyst["customer"]["assertions"][0]["value"] == data_policy.MASK_TOKEN
    assert analyst["data_masked"] is True

    mlro = client.get("/cases/test-co", params={"role": "mlro"}).json()
    assert mlro["customer"]["assertions"][0]["value"] == "Jane Real Owner (100%)"

    # the cached object must stay FULL (masking applied to a copy only)
    assert main._CASE_CACHE["test-co"]["customer"]["assertions"][0]["value"] == "Jane Real Owner (100%)"


# ── API: reveal is RBAC-gated and writes one immutable audit entry ────────────
def test_reveal_denied_for_analyst_allowed_for_mlro_and_audited():
    client = TestClient(main.app)
    denied = client.post("/cases/coinbase-global/reveal", json={"reviewer": "G. Cozzio", "role": "analyst"})
    assert denied.status_code == 403

    ok = client.post("/cases/coinbase-global/reveal",
                     json={"reviewer": "G. Cozzio", "role": "mlro", "note": "EDD review"})
    assert ok.status_code == 200
    assert ok.json()["ok"] is True

    trail = audit.query("coinbase-global")
    assert any(r["action"] == "internal_data_revealed" for r in trail)
    assert audit.verify_chain()["ok"] is True            # chain still intact after the reveal entry
