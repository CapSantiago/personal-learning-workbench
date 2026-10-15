"""Container health probe: no credentials and no external network requests."""
import json
from urllib.request import urlopen

with urlopen('http://127.0.0.1:8501/plw-health', timeout=8) as response:
    result = json.load(response)
    if not result.get('ok'):
        raise SystemExit(1)
