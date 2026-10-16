#!/usr/bin/env bash
# Copied to the offline bundle root. Never downloads packages or opens ports.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
APP="$ROOT/app"
ACTION="${1:-prepare}"
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || fail 'Requires Linux x86_64.'
[[ "$EUID" -eq 0 ]] || fail 'Run on the cloud host as root.'
command -v python3 >/dev/null || fail 'Host python3 is required.'
command -v docker >/dev/null || fail 'Docker is required.'
[[ "$(docker info --format '{{.OSType}}')" == linux ]] || fail 'Requires a running Linux Docker engine.'
python3 "$ROOT/verify_offline_bundle.py" "$ROOT"
IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image"])' "$ROOT/bundle-manifest.json")"
[[ "$IMAGE" =~ ^plw:0\.3\.1-offline-[a-f0-9]{7,40}$ ]] || fail 'Unexpected image name.'
ENVFILE=/srv/plw/private/deploy.env
compose() { docker compose --env-file "$ENVFILE" -f "$APP/compose.yaml" "$@"; }

case "$ACTION" in
  prepare)
    docker load -i "$ROOT/python-3.14-slim-bookworm-amd64.tar.gz"
    expected="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["config_digest"])' "$ROOT/base-image-provenance.json")"
    [[ "$(docker image inspect python:3.14-slim-bookworm --format '{{.Id}}')" == "$expected" ]] || fail 'Loaded base image identity mismatch.'
    DOCKER_BUILDKIT=1 docker build --network=none --pull=false --progress=plain \
      -f "$APP/Dockerfile.offline" -t "$IMAGE" "$APP"
    # A fresh host directory is retained for inspection; no production volumes.
    acceptance="$(mktemp -d /var/tmp/plw-acceptance.XXXXXXXX)"
    chown 10001:10001 "$acceptance"
    chmod 0700 "$acceptance"
    options=(--rm --pull=never --network none --read-only --user 10001:10001
      --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:size=256m,mode=1777
      --mount "type=bind,src=$acceptance,dst=/app/.sandbox/test-runs")
    docker run "${options[@]}" "$IMAGE" python scripts/offline_smoke.py seed --receipt /app/.sandbox/test-runs/receipt.json
    docker run "${options[@]}" "$IMAGE" python scripts/offline_smoke.py check --receipt /app/.sandbox/test-runs/receipt.json
    printf 'PREPARED %s\nSynthetic evidence: %s\nNext: install-tailscale, then log in to Tailscale.\n' "$IMAGE" "$acceptance"
    ;;
  install-tailscale)
    command -v tailscale >/dev/null && fail 'Tailscale already exists; leave the existing installation unchanged.'
    [[ -c /dev/net/tun ]] || fail '/dev/net/tun is unavailable; inspect the host before installing.'
    [[ ! -e /usr/sbin/tailscale && ! -e /usr/sbin/tailscaled && ! -e /etc/systemd/system/tailscaled.service && ! -e /etc/default/tailscaled ]] || fail 'Existing Tailscale files found; refusing to overwrite.'
    staging="$(mktemp -d /var/tmp/plw-tailscale.XXXXXXXX)"
    python3 "$ROOT/extract_tailscale.py" "$ROOT" "$staging"
    install -m 0755 "$staging/tailscale" /usr/sbin/tailscale
    install -m 0755 "$staging/tailscaled" /usr/sbin/tailscaled
    install -m 0644 "$staging/tailscaled.service" /etc/systemd/system/tailscaled.service
    install -m 0644 "$staging/tailscaled.defaults" /etc/default/tailscaled
    systemctl daemon-reload
    systemctl enable --now tailscaled
    tailscale version
    printf '%s\n' 'Next run: tailscale up --hostname=plw' 'Open its login link yourself; do not share auth keys.'
    ;;
  configure)
    [[ -t 0 ]] || fail 'Interactive terminal required for account/password setup.'
    docker image inspect "$IMAGE" >/dev/null
    tailscale status --json | python3 -c 'import json,sys; s=json.load(sys.stdin); assert s.get("BackendState")=="Running"; print("Private host:",s["Self"]["DNSName"])'
    for p in /srv/plw /srv/plw/data /srv/plw/backups /srv/plw/private; do
      [[ ! -L "$p" ]] || fail "Linked path: $p"
      [[ ! -e "$p" || -d "$p" ]] || fail "Not a directory: $p"
    done
    for p in /srv/plw/data /srv/plw/backups /srv/plw/private; do
      if [[ -d "$p" && -n "$(find "$p" -mindepth 1 -print -quit)" ]]; then fail "Existing content: $p; use the documented update/recovery procedure."; fi
    done
    install -d -m 0700 -o 10001 -g 10001 /srv/plw/data /srv/plw/backups /srv/plw/private
    printf '%s\n' 'Enter the full https://<host>.<tailnet>.ts.net origin shown by Tailscale Serve.'
    docker run --rm -it --pull=never --network none --user 10001:10001 \
      --mount type=bind,src=/srv/plw/private,dst=/run/plw-private \
      "$IMAGE" python scripts/setup_private.py --cloud-defaults --config /run/plw-private/account.json
    umask 077
    [[ ! -e "$ENVFILE" ]] || fail 'Deployment environment already exists.'
    printf '%s\n' "PLW_IMAGE=$IMAGE" 'PLW_DATA_DIR=/srv/plw/data' 'PLW_BACKUP_DIR=/srv/plw/backups' 'PLW_CONFIG_DIR=/srv/plw/private' > "$ENVFILE"
    compose run --rm --no-deps --pull never plw python scripts/launch_private.py --config /run/plw-private/account.json --check
    printf '%s\n' 'Configured. Next: init (new empty cloud workspace only), then start.'
    ;;
  init)
    [[ -f "$ENVFILE" && -f /srv/plw/private/account.json ]] || fail 'Run configure first.'
    [[ ! -e /srv/plw/data/control/active.json ]] || fail 'Existing workspace found; refusing to initialize.'
    compose run --rm --no-deps --pull never plw python scripts/cloud_data.py --config /run/plw-private/account.json init
    ;;
  start)
    [[ -f "$ENVFILE" && -f /srv/plw/private/account.json && -f /srv/plw/data/control/active.json ]] || fail 'Configure and initialize first.'
    compose up -d --no-build --pull never
    for _ in {1..30}; do
      if curl --fail --silent --max-time 5 http://127.0.0.1:8501/plw-health; then
        printf '\nLocal health passed. Verify private HTTPS and login from your own device.\n'
        exit 0
      fi
      sleep 2
    done
    compose logs --tail 60 plw
    fail 'Health check failed; no public ports have been opened.'
    ;;
  status)
    [[ -f "$ENVFILE" ]] || fail 'No configured deployment.'
    compose ps
    curl --fail --silent --max-time 5 http://127.0.0.1:8501/plw-health
    ;;
  *) fail 'Usage: bash install_offline.sh prepare|install-tailscale|configure|init|start|status' ;;
esac
