#!/usr/bin/env bash
# Restore drill (P4, runbook section 16): restores one backup into a throw-away database on this
# computer and prints what is in it. Never touches the live server.
#   ND_DRILL_IDENTITY=<age private key file> ND_BACKUP_BUCKET=... ND_BACKUP_S3_ENDPOINT=... \
#   ND_BACKUP_S3_REGION=... ND_BACKUP_S3_ACCESS_KEY=... ND_BACKUP_S3_SECRET_KEY=... \
#     bash tools/restore_drill.sh <BACKUP_KEY>
# Optional (CI): ND_DRILL_IMAGE (a built backup image, else built here), ND_DRILL_RECIPIENTS (a
# recipients file instead of the one baked into the image), ND_DRILL_JOIN_NETWORK (a docker network
# to attach the drill database to, as "drill-db", so the restore reaches an S3 server on it).
# Needs Docker and Git Bash or WSL. Exits non-zero unless the restore reports RESTORED.
set -euo pipefail

key="${1:?usage: restore_drill.sh <BACKUP_KEY>}"
identity="${ND_DRILL_IDENTITY:?set ND_DRILL_IDENTITY to the age private key file}"
for v in ND_BACKUP_BUCKET ND_BACKUP_S3_ENDPOINT ND_BACKUP_S3_REGION ND_BACKUP_S3_ACCESS_KEY ND_BACKUP_S3_SECRET_KEY; do
  [[ -n "${!v:-}" ]] || { echo "ERROR: $v is not set" >&2; exit 2; }
done
[[ -r "$identity" ]] || { echo "ERROR: cannot read $identity" >&2; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT=nd-drill
COMPOSE=(docker compose -p "$PROJECT" -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.drill.yml")
img="${ND_DRILL_IMAGE:-}"
if [[ -z "$img" ]]; then
  img=nd-backup
  docker build -q -t "$img" "$ROOT/infra/backup" >/dev/null
fi

# The identity is copied next to nothing else, readable by the image's non-root user, and removed.
work="$(mktemp -d)"
chmod 711 "$work" # mktemp -d is 0700 on Linux; the image's non-root user must traverse it (no listing)
# shellcheck disable=SC2329 # runs through the EXIT trap
cleanup() {
  rm -rf "$work"
  "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
cp "$identity" "$work/identity.txt"
chmod a+r "$work/identity.txt"
recipients=()
if [[ -n "${ND_DRILL_RECIPIENTS:-}" ]]; then
  cp "$ND_DRILL_RECIPIENTS" "$work/recipients.txt"
  chmod a+r "$work/recipients.txt"
  recipients=(-e ND_AGE_RECIPIENTS=/work/recipients.txt)
fi
hostwork="$(cygpath -m "$work" 2>/dev/null || echo "$work")" # a path docker can mount

"${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true # a leftover of an aborted drill
"${COMPOSE[@]}" up -d --wait db
net="${PROJECT}_default"
pghost=db
if [[ -n "${ND_DRILL_JOIN_NETWORK:-}" ]]; then
  docker network connect --alias drill-db "$ND_DRILL_JOIN_NETWORK" "$("${COMPOSE[@]}" ps -q db)"
  net="$ND_DRILL_JOIN_NETWORK"
  pghost=drill-db
fi

# MSYS_NO_PATHCONV: Git Bash must not rewrite /work/... in the docker arguments.
MSYS_NO_PATHCONV=1 docker run --rm --network "$net" -v "$hostwork:/work:ro" \
  "${recipients[@]}" -e PGHOST="$pghost" -e PGUSER=postgres -e PGPASSWORD=dev-superuser-password \
  -e ND_BACKUP_BUCKET -e ND_BACKUP_S3_ENDPOINT -e ND_BACKUP_S3_REGION \
  -e ND_BACKUP_S3_ACCESS_KEY -e ND_BACKUP_S3_SECRET_KEY \
  "$img" restore.sh --identity /work/identity.txt "$key"

echo "inquiries in the restored database:"
"${COMPOSE[@]}" exec -T db psql -U postgres -d nd -tAc "select count(*) from inquiry"
echo "Keycloak users in the restored database:"
"${COMPOSE[@]}" exec -T db psql -U postgres -d keycloak -tAc "select username from user_entity order by 1"
