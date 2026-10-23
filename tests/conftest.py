"""Create only the ignored synthetic-test parent on a fresh checkout."""
from pathlib import Path

def pytest_configure(config):
    sandbox=Path(__file__).resolve().parents[1]/'.sandbox'
    if sandbox.is_symlink() or sandbox.is_junction():
        raise RuntimeError('Test sandbox must be a real project directory')
    sandbox.mkdir(exist_ok=True)
