#!/usr/bin/env bash
# Run on the Linux server: bash scripts/update_cloud.sh <branch/tag/commit>
set -Eeuo pipefail
cd "$(dirname "$0")/.."
compose() { bash scripts/cloud_compose.sh "$@"; }
ref="${1:?Supply an explicit Git ref}"
[[ "$ref" != -* ]] || { echo 'Invalid Git ref'; exit 2; }
docker compose version >/dev/null
[[ -f .env ]] || { echo 'Prepare .env first'; exit 2; }
git fetch origin
commit=$(git rev-parse --verify "${ref}^{commit}")
mkdir -p .sandbox/releases
exec 9>.sandbox/cloud-update.lock
flock -n 9 || { echo 'Another update is running'; exit 2; }
release=".sandbox/releases/$commit"
if [[ ! -e "$release" ]]; then
  mkdir "$release"
  git archive "$commit" | tar -x -C "$release"
fi
container=$(compose ps -q plw)
[[ -n "$container" ]] || { echo 'Start the initial deployment before using update'; exit 2; }
old_image=$(docker inspect --format '{{.Image}}' "$container")
new_image="plw:git-$commit"
# Build before downtime; a failed build leaves the running service intact.
docker build --tag "$new_image" "$release"
# Backup command exits nonzero on unfinished file operations or checksum failure.
compose exec -T plw python scripts/cloud_data.py --config /run/plw-private/account.json backup
rollback() {
  echo 'Update failed; restoring previous program image. Learning data has not been replaced.'
  PLW_IMAGE="$old_image" compose up -d --no-build --force-recreate plw
}
compose stop plw
if ! PLW_IMAGE="$new_image" compose up -d --no-build --force-recreate plw; then
  rollback; exit 1
fi
healthy=false
for attempt in $(seq 1 30); do
  candidate=$(compose ps -q plw)
  if [[ -n "$candidate" ]] && [[ "$(docker inspect --format '{{.State.Health.Status}}' "$candidate")" == healthy ]]; then
    healthy=true; break
  fi
  sleep 2
done
if [[ "$healthy" != true ]]; then rollback; exit 1; fi
printf '%s\n' "$old_image" > .sandbox/previous-cloud-image
printf '%s\n' "PLW_IMAGE=$new_image" > .env.release.tmp
mv .env.release.tmp .env.release
echo "Updated to $commit. Use bash scripts/cloud_compose.sh for subsequent maintenance."
# New schemas are deliberately NOT migrated by this script. Health fails and
# reverts the image; use the explicit verified-backup restore procedure first.
