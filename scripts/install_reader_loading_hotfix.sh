#!/usr/bin/env bash
# Derivative image only. Preserve account, data, old image and immutable bundle.
set -Eeuo pipefail
[[ "$(uname -s)" == Linux && "$(id -u)" == 0 ]] || { echo 'Run on the Linux host as root.' >&2; exit 1; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ENVFILE=/srv/plw/private/deploy.env
COMPOSE=/opt/plw-offline-20261016/app/compose.yaml
OLD=plw:0.3.1-assetsfix-20261017
NEW=plw:0.3.1-readerfix-20261017
BASE="$(docker image inspect --format '{{.Id}}' "$OLD")"
for file in "$ENVFILE" "$COMPOSE" "$ROOT/reader_runtime.py" "$ROOT/reader.js" "$ROOT/verify_reader_loading_hotfix.py" "$ROOT/Dockerfile" "$ROOT/payload.sha256"; do
  [[ -f "$file" && ! -L "$file" ]] || { echo "Missing regular file: $file" >&2; exit 1; }
done
cd "$ROOT"
sha256sum -c payload.sha256
[[ "$(docker inspect --format '{{.Image}}' plw-plw-1)" == "$BASE" ]] || { echo 'Unexpected running image; stop for review.' >&2; exit 1; }
[[ "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$BASE")" == linux/amd64 ]]
if docker image inspect "$NEW" >/dev/null 2>&1; then
  echo 'Hotfix image already exists; stop instead of overwriting.' >&2; exit 1
fi
python3 - "$ENVFILE" "$OLD" <<'PY'
from pathlib import Path
import sys
assert [x for x in Path(sys.argv[1]).read_text().splitlines() if x.startswith('PLW_IMAGE=')]==['PLW_IMAGE='+sys.argv[2]], 'Unexpected deployment image'
PY
compose() { docker compose --env-file "$ENVFILE" -f "$COMPOSE" "$@"; }
docker run --rm -i --pull=never --network none --read-only --user 10001:10001 \
  --cap-drop ALL --security-opt no-new-privileges:true --entrypoint python "$OLD" -B - <<'PYBASE'
from pathlib import Path
import hashlib, streamlit
assert streamlit.__version__ == '1.65.0', 'Unexpected framework version'
expected={
    'private_auth.py':'0ff1ab929a353b99ea26b74854918ea8303181dec600651a73acccb80993065f',
    'private_assets.py':'dc809c6d46c501e282032ae26c192537b5e56c471cb94c8edce81edabdd002b6',
    'reader_runtime.py':'ec7b40d35ac36cff8d9061f204fb5dd4d4857d21c5884f0d04cbff1143647fec',
    'reader/reader.js':'256a26aef572278464d852579fa8c0dc95fcddf5084e0dd7b5b576b8a1c6c933',
}
for name,digest in expected.items():
    assert hashlib.sha256((Path('/app/src/plw')/name).read_bytes()).hexdigest()==digest, 'Unexpected previous file: '+name
print('READER BASE IMAGE CHECK PASSED')
PYBASE
DOCKER_BUILDKIT=1 docker build --network=none --pull=false -t "$NEW" -f "$ROOT/Dockerfile" "$ROOT"
docker run --rm -i --pull=never --network none --read-only --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true --entrypoint python "$NEW" -B - < "$ROOT/verify_reader_loading_hotfix.py"
# Create the full coordinated backup before switching the image.
compose exec -T plw python scripts/cloud_data.py --config /run/plw-private/account.json backup
snapshot="$(mktemp /srv/plw/private/deploy.env.before-readerfix.XXXXXXXX)"
cp --preserve=mode,ownership -- "$ENVFILE" "$snapshot"
armed=0
rollback() {
  result=${1:-$?}
  trap - ERR INT TERM
  if [[ "$armed" == 1 ]]; then
    echo 'Update failed. Restoring the previous deployment image.' >&2
    cp --preserve=mode,ownership -- "$snapshot" "$ENVFILE"
    if ! compose up -d --no-build --pull never; then
      echo "Rollback also failed. Environment snapshot: $snapshot" >&2
    fi
  fi
  exit "$result"
}
trap rollback ERR
trap 'rollback 130' INT
trap 'rollback 143' TERM
armed=1
python3 - "$ENVFILE" "$OLD" "$NEW" <<'PY'
from pathlib import Path
import os, stat, sys, tempfile
p=Path(sys.argv[1]);old=p.read_bytes();before=('PLW_IMAGE='+sys.argv[2]).encode()
assert [line for line in old.splitlines() if line.startswith(b'PLW_IMAGE=')]==[before]
after=old.replace(before,('PLW_IMAGE='+sys.argv[3]).encode(),1)
meta=p.stat();fd,name=tempfile.mkstemp(prefix='.readerfix-',dir=p.parent)
try:
    os.fchmod(fd,stat.S_IMODE(meta.st_mode));os.fchown(fd,meta.st_uid,meta.st_gid)
    with os.fdopen(fd,'wb') as stream:
        stream.write(after);stream.flush();os.fsync(stream.fileno())
    os.replace(name,p)
finally:
    if os.path.exists(name):os.unlink(name)
PY
compose up -d --no-build --pull never
ok=0
for _ in {1..30}; do
  if [[ "$(docker inspect --format '{{.Image}}' plw-plw-1)" == "$(docker image inspect --format '{{.Id}}' "$NEW")" ]] \
    && curl --noproxy '*' --fail --silent --max-time 3 http://127.0.0.1:8501/plw-health \
      | python3 -c 'import json,sys; s=json.loads(sys.stdin.read() or "{}"); sys.exit(0 if s.get("ok") is True and s.get("initialized") is True else 1)'; then
    ok=1;break
  fi
  sleep 2
done
[[ "$ok" == 1 ]]
armed=0
trap - ERR INT TERM
printf 'READER LOADING HOTFIX STARTED: %s\nPrevious environment: %s\nLog in again, then verify the PDF first page and page navigation.\n' "$NEW" "$snapshot"
