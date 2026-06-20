"""pytest bootstrap: repo root on sys.path; force the deterministic offline MockLLM for tests
(so the suite is reproducible + network-free — `get_llm()` resolves to MockLLM under pytest)."""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DRIFT_LLM_MOCK", "1")
