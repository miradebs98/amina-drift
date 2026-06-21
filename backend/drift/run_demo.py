"""Replay a customer's timeline and print the risk-score arc + the three situations. Runs offline.

    python backend/drift/run_demo.py [customer_id]      (from the repo root; default = coinbase)
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.drift.client_state import load_client_state_from_fixtures
from backend.drift.engine import replay
from backend.drift.score import tier_for
from backend.drift.llm import get_llm

_DOT = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}


def main() -> None:
    customer = sys.argv[1] if len(sys.argv) > 1 else "coinbase"
    state = load_client_state_from_fixtures(customer)
    print(f"\n=== Drift replay · {state.legal_name} "
          f"(onboarded {state.onboarded_as_of}, baseline {state.baseline_risk_score}/{tier_for(state.baseline_risk_score)}) ===\n")
    llm = get_llm()
    print(f"(LLM: {type(llm).__name__})")
    r = replay(state, llm)

    print(f"{'date':<12}{'tier':<10}{'score':<8}{'surprise':<10}{'situation':<12}{'traj'}")
    print("-" * 58)
    for t in r["timeline"]:
        print(f"{str(t['as_of']):<12}{_DOT[t['tier']]+' '+t['tier']:<10}{t['risk_score']:<8}"
              f"{t['surprise']:<10}{t['situation']:<12}{t['traj_distance']}")

    print(f"\n--- {len(r['alerts'])} alert(s) ---")
    for al in r["alerts"]:
        print(f"\n[{al.created_at:%Y-%m-%d}] {al.old_risk_score}→{al.new_risk_score} "
              f"({al.old_risk_tier}→{al.new_risk_tier}, {al.drift_type.value})  {al.flag}")
        print(f"  contradicts: {al.contradicted_assertion_id}   evidence: {al.evidence_ids}")
        print(f"  rationale: {al.rationale}")
        print(f"  action: {al.recommended_action}")

    c = r["cost"]
    print(f"\n--- cost ---  cheap: {c['cheap_calls']} · heavy: {c['heavy_calls']} · "
          f"tokens: {c['total_tokens']} · escalation: {c['escalation_rate']}")
    print(f"\nFINAL: {_DOT[r['final_tier']]} {r['final_tier']}  score {r['final_score']}\n")


if __name__ == "__main__":
    main()
