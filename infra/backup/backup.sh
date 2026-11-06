#!/usr/bin/env bash
# Nightly backup (B6-D4, D11, R06): dump -> tar -> age -> upload -> .ok marker. Exits non-zero on any
# failure and writes the marker only after the upload succeeded, so a half-done run is never valid.
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"

now="$(date -u +%Y%m%dT%H%M%SZ)"
key="nd/${now:0:4}/${now:4:2}/${now:6:2}/nd-$now.tar.age"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# pg_dump reads one repeatable-read snapshot per database, so a busy database still dumps
# consistently (writers are never blocked). The two databases are separate snapshots (R6).
pg_dump -Fc -d "$APP_DB" -f "$work/nd.dump"
pg_dump -Fc -d "$KC_DB" -f "$work/keycloak.dump"
tar -C "$work" -cf "$work/nd.tar" nd.dump keycloak.dump
age -R "$RECIPIENTS" -o "$work/nd.tar.age" "$work/nd.tar"

"${RCLONE[@]}" copyto "$work/nd.tar.age" "nd:$ND_BACKUP_BUCKET/$key"
# The marker comes last; its content is the checksum of the uploaded object.
sha256sum "$work/nd.tar.age" | cut -d' ' -f1 | "${RCLONE[@]}" rcat "nd:$ND_BACKUP_BUCKET/$key.ok"
echo "BACKUP_KEY=$key"
