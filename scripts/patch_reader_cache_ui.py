"""Add immutable document identity/size to an otherwise unchanged deployed UI."""
from pathlib import Path
import sys

BEFORE = b"'pages':edition['page_count'],'state':state"
AFTER = b"'pages':edition['page_count'],'bytes':edition['size_bytes'],'digest':edition['pdf_sha256'],'state':state"


def patch(path):
    path = Path(path)
    data = path.read_bytes()
    if data.count(BEFORE) != 1 or AFTER in data:
        raise ValueError('Unexpected reader UI baseline; refusing to alter it')
    path.write_bytes(data.replace(BEFORE, AFTER, 1))


if __name__ == '__main__':
    patch(sys.argv[1] if len(sys.argv) > 1 else '/app/src/plw/ui_workbench.py')
