"""PLW M2 entry point; earlier milestone entry points remain separate."""
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parent
if str(PROJECT / 'src') not in sys.path:
    sys.path.insert(0, str(PROJECT / 'src'))

from plw.ui_workbench import run as main

main()
