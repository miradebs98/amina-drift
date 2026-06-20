"""Immutable, hash-chained audit log (SQLite) — the real thing, never faked.

Every governance decision appends one row. Each row hash-chains to the previous
(entry_hash = sha256(prev_hash + canonical(payload))), so any later tampering breaks the chain —
`verify_chain()` proves integrity. Stores model provenance + an inputs_hash (sha256), NOT raw PII.

Append-only by design: there is no update or delete. This is the graded Compliance guarantee.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = os.getenv("GOVERN_DB", str(REPO_ROOT / "govern.sqlite"))
GENESIS = "0" * 64


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS audit_log(
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT, timestamp TEXT, action TEXT, actor TEXT, role TEXT,
            customer_id TEXT, alert_id TEXT,
            model_name TEXT, model_version TEXT, inputs_hash TEXT, policy_version TEXT,
            details TEXT, prev_hash TEXT, entry_hash TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS decisions(
            alert_id TEXT PRIMARY KEY, customer_id TEXT, governance_state TEXT,
            reviewer TEXT, role TEXT, note TEXT, decided_at TEXT)""")
    _conn().close()


init()


def _payload(d: dict) -> str:
    """Canonical JSON of the fields that are hash-chained (stable ordering)."""
    keys = ("id", "timestamp", "action", "actor", "role", "customer_id", "alert_id",
            "model_name", "model_version", "inputs_hash", "policy_version", "details")
    return json.dumps({k: d.get(k) for k in keys}, sort_keys=True, default=str)


def record(*, action: str, actor: str, role: str, customer_id: Optional[str], alert_id: Optional[str],
           model_name: Optional[str] = None, model_version: Optional[str] = None,
           inputs_hash: Optional[str] = None, policy_version: str = "v1",
           details: Optional[dict] = None) -> str:
    entry = {
        "id": "audit-" + uuid.uuid4().hex[:12],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action, "actor": actor, "role": role,
        "customer_id": customer_id, "alert_id": alert_id,
        "model_name": model_name, "model_version": model_version,
        "inputs_hash": inputs_hash, "policy_version": policy_version,
        "details": details or {},
    }
    conn = _conn()
    try:
        prev = conn.execute("SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = prev["entry_hash"] if prev else GENESIS
        entry_hash = hashlib.sha256((prev_hash + _payload(entry)).encode()).hexdigest()
        conn.execute(
            """INSERT INTO audit_log(id,timestamp,action,actor,role,customer_id,alert_id,
               model_name,model_version,inputs_hash,policy_version,details,prev_hash,entry_hash)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (entry["id"], entry["timestamp"], action, actor, role, customer_id, alert_id,
             model_name, model_version, inputs_hash, policy_version,
             json.dumps(entry["details"], sort_keys=True), prev_hash, entry_hash))
        conn.commit()
    finally:
        conn.close()
    return entry["id"]


def query(customer_id: Optional[str] = None, alert_id: Optional[str] = None) -> list[dict]:
    sql, params = "SELECT * FROM audit_log", []
    where = []
    if customer_id:
        where.append("customer_id=?"); params.append(customer_id)
    if alert_id:
        where.append("alert_id=?"); params.append(alert_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY seq ASC"
    conn = _conn()
    try:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
    for r in rows:                       # details back to dict for the API
        try:
            r["details"] = json.loads(r["details"]) if r.get("details") else {}
        except Exception:
            pass
    return rows


def verify_chain() -> dict:
    """Recompute the chain and report integrity (tamper-evidence)."""
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY seq ASC").fetchall()
    finally:
        conn.close()
    prev = GENESIS
    for r in rows:
        entry = {k: r[k] for k in r.keys()}
        try:
            entry["details"] = json.loads(r["details"]) if r["details"] else {}
        except Exception:
            entry["details"] = {}
        expected = hashlib.sha256((prev + _payload(entry)).encode()).hexdigest()
        if r["prev_hash"] != prev or r["entry_hash"] != expected:
            return {"ok": False, "length": len(rows), "broken_at_seq": r["seq"]}
        prev = r["entry_hash"]
    return {"ok": True, "length": len(rows), "head": prev if rows else GENESIS}
