"""Explicit local paths. Production data remains disabled until M2 acceptance."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / ".sandbox" / "m1" / "plw.sqlite3"
DEFAULT_WORKSPACE = PROJECT_ROOT / ".sandbox" / "m2"
