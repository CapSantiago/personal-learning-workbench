"""Preserved synthetic M2 acceptance entry."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from plw.ui_m2 import main
main()
