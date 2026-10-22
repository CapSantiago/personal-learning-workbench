#!/usr/bin/env bash
# Derivative image only. Preserve account, data, old image and immutable bundle.
set -Eeuo pipefail
[[ "$(uname -s)" == Linux && "$(id -u)" == 0 ]] || { echo 'Run on the Linux host as root.' >&2; exit 1; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ENVFILE=/srv/plw/private/deploy.env
COMPOSE=/opt/plw-offline-20261016/app/compose.yaml
OLD="$(docker inspect --format '{{.Config.Image}}' plw-plw-1)"
case "$OLD" in
  plw:0.3.1-device-library-20261021-r2|plw:0.3.1-reader-smooth-20261022) ;;
  *) echo 'Unexpected running image; stop for review.' >&2; exit 1 ;;
esac
NEW=plw:0.3.1-reading-workspace-20261022
BASE="$(docker image inspect --format '{{.Id}}' "$OLD")"
for file in "$ENVFILE" "$COMPOSE" "$ROOT/reader.js" "$ROOT/verify_device_library_hotfix.py" "$ROOT/Dockerfile" "$ROOT/payload.sha256"; do
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
  --cap-drop ALL --security-opt no-new-privileges:true --entrypoint python "$OLD" -B - "$OLD" < "$ROOT/verify_reading_workspace_base.py"
DOCKER_BUILDKIT=1 docker build --network=none --pull=false --build-arg BASE_IMAGE="$OLD" -t "$NEW" -f "$ROOT/Dockerfile" "$ROOT"
docker run --rm -i --pull=never --network none --read-only --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true --entrypoint python "$NEW" -B - < "$ROOT/verify_device_library_hotfix.py"
docker run --rm -i --pull=never --network none --read-only --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true --entrypoint python "$NEW" -B - < "$ROOT/verify_reader_smooth_hotfix.py"
docker run --rm -i --pull=never --network none --read-only --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,size=32m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true --entrypoint python "$NEW" -B - < "$ROOT/verify_reading_workspace_ui.py"
# Create the full coordinated backup before switching the image.
compose exec -T plw python scripts/cloud_data.py --config /run/plw-private/account.json backup
snapshot="$(mktemp /srv/plw/private/deploy.env.before-readingworkspace.XXXXXXXX)"
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
meta=p.stat();fd,name=tempfile.mkstemp(prefix='.readingworkspace-',dir=p.parent)
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
printf 'READING WORKSPACE HOTFIX STARTED: %s\nPrevious environment: %s\nLog in again. Shelf tools are consolidated, all active courses are shown on Today, and fit-page geometry is stabilized. Existing device downloads, annotations and native HTTPS are preserved. Browser and physical iPad acceptance remains pending.\n' "$NEW" "$snapshot"
