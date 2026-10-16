#!/usr/bin/env bash
# Resume synthetic checks only; the existing application image/bundle stay unchanged.
set -Eeuo pipefail
bundle="${1:-/opt/plw-offline-20261016}"
python3 "$bundle/verify_offline_bundle.py" "$bundle"
image="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image"])' "$bundle/bundle-manifest.json")"
[[ "$image" =~ ^plw:0\.3\.1-offline-[a-f0-9]{7,40}$ ]] || { echo 'Unexpected image name' >&2; exit 1; }
docker image inspect "$image" --format 'Image={{.Id}} OS={{.Os}} ARCH={{.Architecture}}'
testdir="$(mktemp -d /var/tmp/plw-acceptance.XXXXXXXX)"
chown 10001:10001 "$testdir"
for action in seed check; do
  docker run --rm -i --pull=never --network none --read-only --user 10001:10001 \
    --cap-drop ALL --security-opt no-new-privileges:true \
    --tmpfs /tmp:size=256m,mode=1777 \
    --mount "type=bind,src=$testdir,dst=/app/.sandbox/test-runs" \
    "$image" python - "$action" <<'PY'
from pathlib import Path
import subprocess
import sys
path = Path('/app/scripts/offline_smoke.py')
text = path.read_text(encoding='utf-8')
old_import = 'import sys; from pypdf'
old_write = 'w.write(sys.stdout.buffer)'
if text.count(old_import) != 1 or text.count(old_write) != 1:
    raise RuntimeError('Unexpected smoke script version; no substitution made')
text = text.replace(old_import, 'import io, sys; from pypdf')
text = text.replace(old_write, 'buffer=io.BytesIO(); w.write(buffer); sys.stdout.buffer.write(buffer.getvalue())')
sys.argv = [str(path), sys.argv[1], '--receipt', '/app/.sandbox/test-runs/receipt.json']
try:
    exec(compile(text, str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
except subprocess.CalledProcessError as exc:
    print((exc.stderr or b'').decode('utf-8', errors='replace')[-2000:], file=sys.stderr)
    raise
PY
done
printf 'ACCEPTANCE PASSED: %s\nSynthetic evidence: %s\n' "$image" "$testdir"
