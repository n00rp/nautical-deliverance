#!/usr/bin/env bash
# req: B6-R06
# Backup -> wipe -> restore, end to end, against MinIO as the S3 stand-in (B6-D4, D11).
# Stack: dev compose + infra/docker-compose.backup-test.yml (Keycloak on Postgres, MinIO).
# Uses the images present locally (CI builds them first, tagged via ND_IMAGE_TAG; set NO_BUILD=1).
# Needs Git Bash on Windows. Exits non-zero listing failures; tears everything down on exit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COMPOSE_PROJECT_NAME=nd-backup-test
export ND_COMPOSE_OVERRIDE="$ROOT/infra/docker-compose.backup-test.yml"
TAG="${ND_IMAGE_TAG:-dev}"
IMG="nautical-deliverance/backup:$TAG"
MC_IMG=bitnamilegacy/minio-client@sha256:1a2f12802dc75668aded6de1b7b53d67518ac2a7df823760d9f935235fb3d948
COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml" -f "$ND_COMPOSE_OVERRIDE")
NET="${COMPOSE_PROJECT_NAME}_default"
BUCKET=nd-backups
WORK="$(mktemp -d)"
ISSUER=http://localhost:8081/realms/nautical-deliverance
failures=()
fail() { failures+=("$1"); echo "FAIL: $1"; }
ok() { echo "ok:   $1"; }
# shellcheck disable=SC2329 # runs through the EXIT trap
cleanup() { "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
PY=python; command -v python >/dev/null 2>&1 || PY=python3
json() { "$PY" -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
HOSTWORK="$(cygpath -m "$WORK" 2>/dev/null || echo "$WORK")" # a path docker can mount

build_flag=--build
if [[ -n "${NO_BUILD:-}" ]]; then build_flag=--no-build; else docker build -q -t "$IMG" "$ROOT/infra/backup" >/dev/null; fi

s3env=(-e "ND_BACKUP_BUCKET=$BUCKET" -e ND_BACKUP_S3_ENDPOINT=http://minio:9000 -e ND_BACKUP_S3_REGION=us-east-1
  -e ND_BACKUP_S3_ACCESS_KEY=ci-minio-user -e ND_BACKUP_S3_SECRET_KEY=ci-minio-password)
pgenv=(-e PGHOST=db -e PGUSER=postgres -e PGPASSWORD=dev-superuser-password)
# MSYS_NO_PATHCONV: Git Bash must not rewrite /work etc. in docker arguments.
# Runs a script from the backup image on the stack's network with the generated recipients file.
runb() {
  MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" "${s3env[@]}" "${pgenv[@]}" \
    -v "$HOSTWORK:/work" -e ND_AGE_RECIPIENTS=/work/recipients.txt "$IMG" "$@"
}
mc() {
  MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" -e MC_HOST_local=http://ci-minio-user:ci-minio-password@minio:9000 \
    --entrypoint mc "$MC_IMG" "$@"
}
psql_app() { "${COMPOSE[@]}" exec -T -e PGPASSWORD=dev-app-password db psql -h 127.0.0.1 -U nd_app -d nd -tAc "$1"; }
psql_su() { "${COMPOSE[@]}" exec -T db psql -U postgres -d nd -tAc "$1"; }
token() {
  curl -sf "$ISSUER/protocol/openid-connect/token" -d grant_type=password -d client_id=nd-smoke \
    -d "username=$1" -d "password=$2" | json "d['access_token']"
}
api() { curl -s -H "Authorization: Bearer $1" "http://localhost:8080/api/v1/$2"; }
rls_state() {
  psql_su "select count(*) from pg_policies where schemaname='public'"
  psql_su "select string_agg(relname, ',' order by relname) from pg_class where relrowsecurity and relkind='r'"
}

echo "== 1. start the stack and MinIO"
"${COMPOSE[@]}" up --detach --wait --wait-timeout 300 "$build_flag"

echo "== 2. data: seed (done by the engine), a probe user in Keycloak, one inquiry through the API"
adm="$(curl -sf http://localhost:8081/realms/master/protocol/openid-connect/token -d grant_type=password \
  -d client_id=admin-cli -d username=admin -d password=dev-keycloak-admin-password | json "d['access_token']")"
curl -sf -o /dev/null -H "Authorization: Bearer $adm" -H 'Content-Type: application/json' \
  http://localhost:8081/admin/realms/nautical-deliverance/users -d '{"username":"restore-probe@acme.test",
  "email":"restore-probe@acme.test","firstName":"Restore","lastName":"Probe","enabled":true,"emailVerified":true,
  "credentials":[{"type":"password","value":"probe-pass-1234","temporary":false}]}' \
  && ok "probe user created in Keycloak" || fail "could not create the probe user"
buyer="$(token bunker_buyer@acme.test bunker_buyer@acme.test)"
src="$(api "$buyer" inquiries | json "d[0]['id']")"
ver="$(api "$buyer" "inquiries/$src" | json "d['version']")"
new="$(curl -sf -X POST -H "Authorization: Bearer $buyer" -H 'Content-Type: application/json' \
  "http://localhost:8080/api/v1/inquiries/$src/duplicate" -d "{\"version\": $ver}" | json "d['id'] + ' ' + d['reference']")"
new_id="${new% *}"
new_ref="${new#* }"
[[ -n "$new_id" ]] && ok "inquiry $new_ref created ($new_id)" || fail "inquiry not created"
before_n="$(psql_su "select count(*) from inquiry")"
before_rls="$(rls_state)"

echo "== 3. bucket with a 14-day lifecycle rule"
mc mb --ignore-existing "local/$BUCKET" >/dev/null
mc ilm rule add --expire-days 14 "local/$BUCKET" >/dev/null
mc ilm rule ls "local/$BUCKET" | tee "$WORK/ilm.txt"
grep -Eq '(^|[^0-9])14([^0-9]|$)' "$WORK/ilm.txt" && ok "lifecycle rule: expire after 14 days" || fail "lifecycle rule missing or not 14 days"

echo "== 4. refuses the committed placeholder recipient (no real key yet)"
if docker run --rm --network "$NET" "${s3env[@]}" "${pgenv[@]}" "$IMG" backup.sh >"$WORK/refuse.log" 2>&1; then
  fail "backup.sh ran with the placeholder recipients file"
elif grep -q "placeholder" "$WORK/refuse.log"; then ok "backup.sh refuses the placeholder recipient"
else fail "refusal had no clear message"; fi

echo "== 5. backup with a throwaway age key"
docker run --rm --entrypoint age-keygen "$IMG" >"$WORK/identity.txt" 2>"$WORK/keygen.err"
sed -n 's/^# public key: //p' "$WORK/identity.txt" >"$WORK/recipients.txt"
chmod a+r "$WORK/identity.txt" "$WORK/recipients.txt" # the image runs as a non-root user
if out="$(runb backup.sh 2>&1)"; then ok "backup.sh exit 0"; else echo "$out"; fail "backup.sh failed"; fi
key="$(echo "$out" | sed -n 's/^BACKUP_KEY=//p' | tail -1)"
[[ "$key" =~ ^nd/[0-9]{4}/[0-9]{2}/[0-9]{2}/nd-[0-9]{8}T[0-9]{6}Z\.tar\.age$ ]] && ok "key $key" || fail "unexpected key '$key'"
mc stat "local/$BUCKET/$key.ok" >/dev/null 2>&1 && ok ".ok marker exists" || fail ".ok marker missing"
header="$(mc cat "local/$BUCKET/$key" | head -c 30 || true)" # head closes the pipe early
[[ "$header" == age-encryption.org/* ]] && ok "object is age-encrypted" || fail "object is not age output"

echo "== 6. stop the stack and wipe its volumes; start an empty database"
"${COMPOSE[@]}" rm -sf -v engine web keycloak db >/dev/null
docker volume rm "${COMPOSE_PROJECT_NAME}_db-data" >/dev/null
"${COMPOSE[@]}" up --detach --wait --wait-timeout 120 db
[[ "$(psql_su "select count(*) from information_schema.tables where table_schema='public' and table_name='inquiry'")" == 0 ]] \
  && ok "database is empty" || fail "database is not empty after the wipe"

echo "== 7. restore with the test identity"
if runb restore.sh --identity /work/identity.txt "$key"; then ok "restore.sh exit 0"; else fail "restore.sh failed"; fi
if runb restore.sh --identity /work/identity.txt "${key%.tar.age}-nope.tar.age" >/dev/null 2>&1; then
  fail "restore.sh accepted a key without .ok marker"
else ok "restore.sh refuses a key without .ok marker"; fi

echo "== 8. start the restored stack; data, RLS, users and smoke"
"${COMPOSE[@]}" up --detach --wait --wait-timeout 300 --no-build
buyer="$(token bunker_buyer@acme.test bunker_buyer@acme.test)"
[[ "$(api "$buyer" "inquiries/$new_id" | json "d['reference']" 2>/dev/null || true)" == "$new_ref" ]] \
  && ok "inquiry $new_ref exists after restore" || fail "inquiry $new_ref missing after restore"
[[ "$(psql_su "select count(*) from inquiry")" == "$before_n" ]] && ok "inquiry count unchanged ($before_n)" || fail "inquiry count changed"
[[ "$(rls_state)" == "$before_rls" ]] && ok "RLS policies and RLS-enabled tables identical" || fail "RLS differs after restore"
[[ "$(psql_app "select count(*) from inquiry")" == 0 ]] && ok "nd_app without an organization sees 0 inquiries" || fail "nd_app sees rows without an organization"
[[ "$(psql_su "select tableowner from pg_tables where tablename='inquiry'")" == nd_owner ]] \
  && ok "tables are owned by nd_owner" || fail "table owner is not nd_owner"
borealis="$(token bunker_buyer@borealis.test bunker_buyer@borealis.test)"
code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $borealis" "http://localhost:8080/api/v1/inquiries/$new_id")"
[[ "$code" == 404 ]] && ok "other organization gets 404 for the restored inquiry" || fail "cross-org read returned $code"
[[ -n "$(token restore-probe@acme.test probe-pass-1234 2>/dev/null || true)" ]] \
  && ok "Keycloak user created after the realm import can still log in" || fail "probe user lost in restore"
if bash "$ROOT/tools/smoke.sh" >"$WORK/smoke.log" 2>&1; then ok "smoke test passes on the restored stack"
else tail -20 "$WORK/smoke.log"; fail "smoke test failed on the restored stack"; fi

echo "== 9. marker and lifecycle rule still there"
mc stat "local/$BUCKET/$key.ok" >/dev/null 2>&1 && ok ".ok marker still exists" || fail ".ok marker gone"
mc ilm rule ls "local/$BUCKET" | grep -Eq '(^|[^0-9])14([^0-9]|$)' && ok "lifecycle rule still configured" || fail "lifecycle rule gone"

echo "== 10. failed upload: MinIO stopped"
oks_before="$(mc ls --recursive "local/$BUCKET" | grep -c '\.ok$' || true)"
"${COMPOSE[@]}" stop minio >/dev/null
if runb backup.sh >"$WORK/fail.log" 2>&1; then fail "backup.sh exited 0 with MinIO down"; else ok "backup.sh exits non-zero with MinIO down"; fi
"${COMPOSE[@]}" up --detach --wait --wait-timeout 60 minio >/dev/null
oks_after="$(mc ls --recursive "local/$BUCKET" | grep -c '\.ok$' || true)"
[[ "$oks_before" == 1 && "$oks_after" == 1 ]] && ok "no new .ok marker after the failed upload" || fail ".ok markers: $oks_before -> $oks_after"

if ((${#failures[@]})); then
  printf '\nBACKUP/RESTORE TEST FAILED (%d):\n' "${#failures[@]}"
  printf ' - %s\n' "${failures[@]}"
  exit 1
fi
echo "BACKUP/RESTORE TEST PASSED"
