"""pytest path bootstrap: put the repo root on sys.path so `shared` and `backend.drift` import."""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
