#!/usr/bin/env bash
# Restore (B6-D4, R06): restore.sh --identity <age identity file> <key>
# <key> is the object key printed by backup.sh (BACKUP_KEY=...), for example
# nd/2026/11/06/nd-20261106T021500Z.tar.age
# Run it with only the database up (an empty stack; see the runbook).
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"

identity="" key=""
while (($#)); do
  case "$1" in
    --identity) identity="${2:-}"; shift 2 ;;
    -*) die "unknown option $1" ;;
    *) key="$1"; shift ;;
  esac
done
[[ -n "$identity" && -r "$identity" && -n "$key" ]] || die "usage: restore.sh --identity <age identity file> <key>"

# Only objects with a .ok marker are complete backups.
"${RCLONE[@]}" lsf "nd:$ND_BACKUP_BUCKET/$key.ok" | grep -q . || die "no .ok marker for $key: not a complete backup"

# pg_restore --clean would drop tables under a running engine or Keycloak: refuse if anyone is connected.
busy="$(psql -d postgres -tAc "select count(*) from pg_stat_activity where datname in ('$APP_DB','$KC_DB') and pid <> pg_backend_pid()")"
[[ "$busy" == 0 ]] || die "$busy session(s) are connected to $APP_DB/$KC_DB: stop engine and keycloak first"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
"${RCLONE[@]}" copyto "nd:$ND_BACKUP_BUCKET/$key" "$work/nd.tar.age"
age -d -i "$identity" -o "$work/nd.tar" "$work/nd.tar.age"
tar -C "$work" -xf "$work/nd.tar"

# A superuser restore keeps owners (nd_owner, keycloak) and grants; the roles come from the db init
# scripts on the empty volume. Single transaction: any error leaves the database as it was.
for pair in "$APP_DB:nd.dump" "$KC_DB:keycloak.dump"; do
  pg_restore --clean --if-exists --single-transaction --exit-on-error -d "${pair%%:*}" "$work/${pair#*:}"
  echo "restored ${pair%%:*}"
done
echo "RESTORED $key"
