#!/usr/bin/env bash
# Stack smoke test: brings the compose stack up on the images present locally (CI builds them
# first, tagged via ND_IMAGE_TAG) and checks the end-to-end path. Exits non-zero listing failures.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml")
TAG="${ND_IMAGE_TAG:-dev}"  # same default as docker-compose.yml
ISSUER="http://localhost:8081/realms/nautical-deliverance"
failures=()

fail() { failures+=("$1"); echo "FAIL: $1"; }
ok() { echo "ok:   $1"; }

start=$SECONDS
"${COMPOSE[@]}" up --detach --wait --wait-timeout 180
echo "up --wait took $((SECONDS - start)) s"

# Python is only used as a JSON reader on the host; the engine tests already require it.
PY=python; command -v python >/dev/null 2>&1 || PY=python3
json() { "$PY" -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

code="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/api/v1/health || true)"
[[ "$code" == 200 ]] && ok "GET /api/v1/health via web proxy = 200" || fail "health returned '$code'"
code="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/health || true)"
[[ "$code" == 200 ]] && ok "GET /api/v1/health on engine = 200" || fail "engine health returned '$code'"
SHA="${ND_GIT_SHA:-dev}"  # same default as docker-compose.yml; CI sets the commit SHA
ver="$(curl -sf http://localhost:8080/api/v1/health | json "d['version']" 2>/dev/null || true)"
[[ "$ver" == "$SHA" ]] && ok "health version = $SHA" || fail "health version is '$ver', expected '$SHA'"

token() { # token <user>: password == username (test-only realm)
  curl -sf "$ISSUER/protocol/openid-connect/token" -d grant_type=password -d client_id=nd-smoke \
    -d "username=$1" -d "password=$1" | json "d['access_token']"
}

check_me() { # check_me <user> <expected org name> <expected role>
  local tok me
  if ! tok="$(token "$1")" || [[ -z "$tok" ]]; then fail "token for $1"; return; fi
  ok "token for $1"
  local iss
  iss="$("$PY" -c "import base64,json,sys; p=sys.argv[1].split('.')[1]; print(json.loads(base64.urlsafe_b64decode(p+'='*(-len(p)%4)))['iss'])" "$tok" 2>/dev/null || true)"
  [[ "$iss" == "$ISSUER" ]] && ok "iss of $1 token is $ISSUER" || fail "iss of $1 token is '$iss'"
  me="$(curl -sf -H "Authorization: Bearer $tok" http://localhost:8080/api/v1/me || true)"
  [[ "$(echo "$me" | json "d['organization']['name']" 2>/dev/null || true)" == "$2" ]] \
    && ok "/me for $1 -> $2" || fail "/me for $1 expected org '$2', got: $me"
  [[ "$(echo "$me" | json "d['roles']" 2>/dev/null || true)" == "['$3']" ]] \
    && ok "/me for $1 roles = $3" || fail "/me for $1 expected role '$3', got: $me"
}

for role in admin bunker_buyer operator viewer; do
  check_me "$role@acme.test" "Acme Shipping" "$role"
  check_me "$role@borealis.test" "Borealis Tankers" "$role"
done

check_master() { # check_master <user>: seeded ports and a suggestion with both "all" and "some"
  local tok api=http://localhost:8080/api/v1/master ports prods pq pid a s hit=0
  if ! tok="$(token "$1")" || [[ -z "$tok" ]]; then fail "token for $1"; return; fi
  ports="$(curl -sf -H "Authorization: Bearer $tok" "$api/ports" || true)"
  [[ "$(echo "$ports" | json "len(d)" 2>/dev/null || echo 0)" -ge 10 ]] \
    && ok "GET /master/ports for $1 >= 10" || fail "ports for $1: $ports"
  prods="$(curl -sf -H "Authorization: Bearer $tok" "$api/products?q=VLSFO" | json "[p['id'] for p in d if p['name']=='VLSFO'][0]" 2>/dev/null || true)"
  pq="product_id=$prods&product_id=$(curl -sf -H "Authorization: Bearer $tok" "$api/products?q=MGO" | json "[p['id'] for p in d if p['name']=='MGO'][0]" 2>/dev/null || true)"
  for pid in $(echo "$ports" | json "' '.join(p['id'] for p in d)" 2>/dev/null || true); do
    out="$(curl -sf -H "Authorization: Bearer $tok" "$api/counterparties/suggest?port_id=$pid&$pq" || true)"
    a="$(echo "$out" | json "len(d['all'])" 2>/dev/null || echo 0)"
    s="$(echo "$out" | json "len(d['some'])" 2>/dev/null || echo 0)"
    if ((a > 0 && s > 0)); then hit=1; break; fi
  done
  ((hit)) && ok "suggest for $1 yields all and some at one port" || fail "no port with all+some for $1"
}
check_master viewer@acme.test
check_master viewer@borealis.test

for svc in engine web; do
  img="nautical-deliverance/$svc:$TAG"
  user="$(docker inspect --format '{{.Config.User}}' "$img")"
  [[ -n "$user" && "$user" != 0 && "$user" != root && "$user" != 0:* && "$user" != root:* ]] \
    && ok "$svc image runs as non-root ($user)" || fail "$svc image user is '$user'"
  if docker run --rm --entrypoint sh "$img" -c 'command -v gcc' >/dev/null 2>&1; then
    fail "$svc image contains gcc"
  else ok "$svc image has no gcc"; fi
done

if ((${#failures[@]})); then
  printf '\nSMOKE FAILED (%d):\n' "${#failures[@]}"
  printf ' - %s\n' "${failures[@]}"
  exit 1
fi
echo "SMOKE PASSED"
