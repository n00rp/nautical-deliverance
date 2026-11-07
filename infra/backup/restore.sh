#!/usr/bin/env bash
# restore.sh --identity <age identity file> [--force] <key>  (B6-D4, R06)
# <key> is the object key printed by backup.sh (BACKUP_KEY=...), for example
# nd/2026/11/06/nd-20261106T021500Z.tar.age
# Run it with only the database up (an empty stack; see the runbook).
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"

identity="" key="" force=0
while (($#)); do
  case "$1" in
    --identity) identity="${2:-}"; shift 2 ;;
    --force) force=1; shift ;;
    -*) die "unknown option $1" ;;
    *) key="$1"; shift ;;
  esac
done
[[ -n "$identity" && -r "$identity" && -n "$key" ]] || die "usage: restore.sh --identity <age identity file> [--force] <key>"

# Only objects with a .ok marker are complete backups. The marker holds the sha256 of the object.
# rclone exit 3/4 = not found; anything else (network, credentials) is not "no marker".
rc=0
expected="$("${RCLONE[@]}" cat "nd:$ND_BACKUP_BUCKET/$key.ok")" || rc=$?
case "$rc" in
  0) ;;
  3 | 4) die "no .ok marker for $key: not a complete backup" ;;
  *) die "cannot read nd:$ND_BACKUP_BUCKET/$key.ok (rclone exit $rc): check endpoint, credentials and network" ;;
esac
expected="${expected//[[:space:]]/}"
# Some S3 servers (SeaweedFS) answer a missing object with exit 0 and no content.
[[ -n "$expected" ]] || die "no .ok marker for $key: not a complete backup"
[[ "$expected" =~ ^[0-9a-f]{64}$ ]] || die "the .ok marker of $key does not hold a sha256"

# pg_restore --clean would drop tables under a running engine or Keycloak: refuse if anyone is connected.
busy="$(psql -d postgres -tAc "select count(*) from pg_stat_activity where datname in ('$APP_DB','$KC_DB') and pid <> pg_backend_pid()")"
[[ "$busy" == 0 ]] || die "$busy session(s) are connected to $APP_DB/$KC_DB: stop engine and keycloak first"

# An empty stack has no tables in either database (PostGIS's own spatial_ref_sys does not count).
if ((!force)); then
  used=0
  for db in "$APP_DB" "$KC_DB"; do
    n="$(psql -d "$db" -tAc "select count(*) from pg_tables where schemaname='public' and tablename <> 'spatial_ref_sys'")"
    used=$((used + n))
  done
  ((used == 0)) || die "$APP_DB/$KC_DB already hold $used table(s): restore into an empty stack, or pass --force to replace them"
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
"${RCLONE[@]}" copyto "nd:$ND_BACKUP_BUCKET/$key" "$work/nd.tar.age"
actual="$(sha256sum "$work/nd.tar.age" | cut -d' ' -f1)"
[[ "$actual" == "$expected" ]] || die "checksum mismatch for $key (marker $expected, downloaded $actual): the object was changed or damaged"
age -d -i "$identity" -o "$work/nd.tar" "$work/nd.tar.age"
tar -C "$work" -xf "$work/nd.tar"

# A superuser restore keeps owners (nd_owner, keycloak) and grants; the roles come from the db init
# scripts on the empty volume. Single transaction: any error leaves the database as it was.
for pair in "$APP_DB:nd.dump" "$KC_DB:keycloak.dump"; do
  pg_restore --clean --if-exists --single-transaction --exit-on-error -d "${pair%%:*}" "$work/${pair#*:}"
  echo "restored ${pair%%:*}"
done
echo "RESTORED $key"
