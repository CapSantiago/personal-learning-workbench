"""Preserved PLW M1 semester/course entry point."""
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parent
if str(PROJECT / 'src') not in sys.path:
    sys.path.insert(0, str(PROJECT / 'src'))

from plw.ui import main

main()
