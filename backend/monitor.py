"""Production monitor — the scheduled poll loop behind the demo's replay.

The demo drives a `SimClock` over a frozen timeline (`engine.replay`). In production the SAME
per-client pipeline runs on the wall clock, on a cadence AMINA controls:

    collect (Layer-1 connectors)  →  assess (gate → verdict → score)  →  new drift?  →  alert + audit

How "real-time" works without a long-running daemon: an external scheduler (cron, a cloud
scheduler, or a Kubernetes CronJob) ticks this module on a fixed beat — e.g. hourly — and the
SWEEP decides which clients are actually DUE from `config.MONITORING` (a global default plus a
per-risk-band override: HIGH re-checked every 6h, LOW weekly). So the cadence is pure
configuration: AMINA changes it (env override or a /monitoring endpoint) with no redeploy, and a
client is never polled more often than its band warrants — which is also the main cost lever
(daily × N clients × the cheap cascade).

Idempotent by construction: connectors cache and the stream is de-duplicated by event id, and
Stage-2 verdicts are memoised per (assertion, event) — so re-polling only spends tokens on
genuinely NEW evidence. A client is flagged only when this poll's score rises vs. the last poll.

    python -m backend.monitor                  # one sweep over all DUE clients (cron-friendly)
    python -m backend.monitor --all            # ignore cadence, sweep everyone now
    python -m backend.monitor --loop --tick 3600   # self-contained scheduler (ticks every hour)

Live data needs OFFLINE_DEMO=false (+ connector keys); default is the offline fixtures pipeline.
"""
from __future__ import annotations

import json
import os
import sys
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from backend.drift import config
from backend.drift.score import tier_for

REPO_ROOT = Path(__file__).resolve().parents[1]
_CUSTOMERS_DIR = REPO_ROOT / "data" / "customers"
_STATE_FILE = REPO_ROOT / "data" / "monitor_state.json"   # {cid: {last_checked, last_score, last_tier}}


# ── cadence (AMINA-tunable: config defaults, env overrides at runtime, no redeploy) ──────────────
def _interval_hours(tier: str) -> float:
    """Re-check interval for a client currently in `tier`. Env overrides win so AMINA can retune live:
    DRIFT_MONITOR_DEFAULT_HOURS, DRIFT_MONITOR_HIGH_HOURS / _MEDIUM_HOURS / _LOW_HOURS."""
    by_band = dict(config.MONITORING["by_band_hours"])
    default = float(os.getenv("DRIFT_MONITOR_DEFAULT_HOURS", config.MONITORING["default_interval_hours"]))
    env = os.getenv(f"DRIFT_MONITOR_{tier}_HOURS")
    return float(env) if env else float(by_band.get(tier, default))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_state() -> dict:
    if _STATE_FILE.exists():
        return json.loads(_STATE_FILE.read_text())
    return {}


def _save_state(state: dict) -> None:
    _STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def _customers() -> list[str]:
    return sorted(p.stem for p in _CUSTOMERS_DIR.glob("*.json"))


def _baseline_tier(cid: str) -> str:
    cust = json.loads((_CUSTOMERS_DIR / f"{cid}.json").read_text())
    return tier_for(int(cust.get("risk_model", {}).get("onboarding_score", 30)))


def _is_due(cid: str, st: dict, force: bool) -> bool:
    if force or cid not in st or not st[cid].get("last_checked"):
        return True
    last = datetime.fromisoformat(st[cid]["last_checked"])
    band = st[cid].get("last_tier") or _baseline_tier(cid)
    elapsed_h = (_now() - last).total_seconds() / 3600.0
    return elapsed_h >= _interval_hours(band)


def _notify(cid: str, name: str, prev: dict | None, score: int, tier: str, alerts: list) -> None:
    """Where a confirmed new drift leaves the monitor. The detected alert enters the SAME governance
    path as the demo (HITL approve/escalate → hash-chained audit via backend/govern). This hook is
    the pluggable sink — wire email / Slack / a case-queue here. Logged for now (honest: no live
    downstream system is bundled)."""
    base = f"{prev.get('last_score') if prev else 'onboarding'}"
    flag = alerts[-1].get("flag") if alerts else "re-tiering"
    print(f"  🚩 DRIFT  {name} ({cid}): {base} → {score}/{tier}  · {flag}  · {len(alerts)} alert(s) → govern queue")


def sweep(force: bool = False, live: bool | None = None) -> list[dict]:
    """One pass: run every DUE client through the live pipeline, flag new drift, persist cursors."""
    from backend.api.cases import build_case   # canonical pipeline (collect → replay), same as the API

    if not config.MONITORING.get("enabled", True) and not force:
        print("monitoring disabled (config.MONITORING.enabled = False)"); return []

    st = _load_state()
    fired: list[dict] = []
    due = [c for c in _customers() if _is_due(c, st, force)]
    print(f"[{_now():%Y-%m-%d %H:%M:%SZ}] sweep — {len(due)}/{len(_customers())} client(s) due")

    for cid in due:
        case = build_case(cid, live=live)
        if case is None:
            continue
        score, tier = case["final_score"], case["final_tier"]
        prev = st.get(cid)
        rise = score - (prev.get("last_score") if prev else None) if prev and prev.get("last_score") is not None else None
        # flag when the score climbed at least the configured step since the last poll (or first-ever HIGH)
        new_drift = (rise is not None and rise >= config.MONITORING["alert_on_score_increase"]) or \
                    (prev is None and tier == "HIGH")
        if new_drift:
            _notify(cid, case["customer"].get("legal_name", cid), prev, score, tier, case.get("alerts", []))
            fired.append({"customer_id": cid, "score": score, "tier": tier, "rise": rise})
        else:
            print(f"  ✓ stable  {cid}: {score}/{tier}")
        st[cid] = {"last_checked": _now().isoformat(), "last_score": score, "last_tier": tier}

    _save_state(st)
    print(f"sweep done — {len(fired)} new drift event(s); next run re-checks each client per its band cadence")
    return fired


def _main(argv: list[str]) -> int:
    force = "--all" in argv
    loop = "--loop" in argv
    tick = 3600
    if "--tick" in argv:
        tick = int(argv[argv.index("--tick") + 1])
    if not loop:
        sweep(force=force)
        return 0
    print(f"scheduler loop — ticking every {tick}s (Ctrl-C to stop)")
    while True:                       # self-contained alternative to cron for a demo/VM
        sweep(force=False)
        _time.sleep(tick)


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
