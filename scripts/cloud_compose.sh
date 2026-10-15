#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
args=(--env-file .env)
if [[ -f .env.release ]]; then args+=(--env-file .env.release); fi
exec docker compose "${args[@]}" "$@"
