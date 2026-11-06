#!/usr/bin/env bash
# Prod-overlay smoke test (B6-R01): starts the production overlay on https://localhost with
# throwaway secrets and checks it through Caddy. Caddy serves `localhost` from its own internal CA;
# curl trusts exactly that root certificate (copied out of the container), never -k.
# The stack is left running; the caller tears it down (CI "always" step, or the trap with CLEANUP=1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
ENV_FILE="$WORK/env"
secret() { openssl rand -hex 16; }
cat > "$ENV_FILE" <<ENV
ND_PUBLIC_HOST=localhost
ND_DB_SUPERUSER_PASSWORD=$(secret)
ND_DB_OWNER_PASSWORD=$(secret)
ND_DB_APP_PASSWORD=$(secret)
ND_DB_KEYCLOAK_PASSWORD=$(secret)
ND_KEYCLOAK_ADMIN_PASSWORD=$(secret)
ND_BACKUP_BUCKET=unused
ND_BACKUP_S3_ENDPOINT=http://127.0.0.1:9
ND_BACKUP_S3_REGION=unused
ND_BACKUP_S3_ACCESS_KEY=unused
ND_BACKUP_S3_SECRET_KEY=unused
ND_IMAGE_TAG=${ND_IMAGE_TAG:-dev}
ND_GIT_SHA=${ND_GIT_SHA:-dev}
ENV
COMPOSE=(docker compose -p nd-prod-smoke --env-file "$ENV_FILE" -f "$ROOT/infra/docker-compose.yml" -f "$ROOT/infra/docker-compose.prod.yml")
if [[ "${CLEANUP:-0}" == 1 ]]; then
  trap '"${COMPOSE[@]}" down --volumes >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT
fi
failures=()
fail() { failures+=("$1"); echo "FAIL: $1"; }
ok() { echo "ok:   $1"; }

# CI builds and tags the images first and sets NO_BUILD=1; locally compose builds them.
build_flag=--build
[[ -z "${NO_BUILD:-}" ]] || build_flag=--no-build
"${COMPOSE[@]}" up --detach --wait --wait-timeout 300 "$build_flag"
"${COMPOSE[@]}" cp caddy:/data/caddy/pki/authorities/local/root.crt "$WORK/root.crt"
URL=https://localhost
# --ssl-no-revoke: Windows Schannel rejects a private CA that has no CRL; no-op elsewhere.
CURL=(curl -s --cacert "$WORK/root.crt" --ssl-no-revoke --max-time 20)

code="$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$URL/api/v1/health" || true)"
[[ "$code" == 200 ]] && ok "GET /api/v1/health over HTTPS = 200" || fail "health returned '$code'"
code="$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$URL/admin/" || true)"
[[ "$code" == 404 ]] && ok "GET /admin/ = 404" || fail "/admin/ returned '$code'"
code="$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$URL/realms/master/.well-known/openid-configuration" || true)"
[[ "$code" == 404 ]] && ok "master realm = 404" || fail "master realm returned '$code'"
code="$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$URL/" || true)"
[[ "$code" == 200 ]] && ok "GET / (web) = 200" || fail "web returned '$code'"

for path in /ADMIN/ //admin/ /realms/nautical-deliverance/../master/ /admin/realms/; do
  code="$("${CURL[@]}" --path-as-is -o /dev/null -w '%{http_code}' "$URL$path" || true)"
  [[ "$code" == 404 ]] && ok "bypass probe $path = 404" || fail "bypass probe $path returned '$code'"
done

# Admin console: only through the loopback port (the SSH tunnel target), no redirect to the
# public host.
out="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 20 \
  http://127.0.0.1:8081/admin/master/console/ || true)"
[[ "$out" == "200 " ]] && ok "admin console on 127.0.0.1:8081 = 200, no redirect" || fail "admin console: '$out'"

headers="$("${CURL[@]}" -D - -o /dev/null "$URL/" | tr -d '\r')"
for h in "strict-transport-security: max-age=31536000" "x-content-type-options: nosniff" \
  "referrer-policy: strict-origin-when-cross-origin" "x-frame-options: DENY" \
  "content-security-policy: default-src 'self'"; do
  [[ "${headers,,}" == *"${h,,}"* ]] && ok "header $h" || fail "missing header: $h"
done

# Keycloak pages keep Keycloak's own CSP (not the app's), so the login page's inline scripts run.
# (-L: the auth endpoint redirects to the login form; judge the final response.)
code="$("${CURL[@]}" -L -c "$WORK/jar" -b "$WORK/jar" -D "$WORK/login.h" -o /dev/null -w '%{http_code}' \
  "$URL/realms/nautical-deliverance/protocol/openid-connect/auth?client_id=nd-web&redirect_uri=$URL/&response_type=code&scope=openid&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256" || true)"
login="$(tr -d '\r' < "$WORK/login.h")"
login="${login##*$'\n\n'}"
[[ "$code" == 200 ]] && ok "login page = 200" || fail "login page status: $code"
[[ "${login,,}" == *"content-security-policy:"* && "${login,,}" != *"connect-src 'self'; form-action"* ]] \
  && ok "login page carries Keycloak's CSP" || fail "login page CSP is missing or the app's"

# The token issuer is the discovery issuer: it must be the public URL even though Keycloak is
# reached over plain HTTP inside the network.
issuer="$("${CURL[@]}" "$URL/realms/nautical-deliverance/.well-known/openid-configuration" \
  | python -c "import json,sys; print(json.load(sys.stdin)['issuer'])" 2>/dev/null || true)"
[[ "$issuer" == "$URL/realms/nautical-deliverance" ]] && ok "OIDC issuer = $issuer" || fail "issuer is '$issuer'"
# The engine fetches signing keys over the internal URL.
"${COMPOSE[@]}" exec -T engine python -c "import urllib.request as u; assert b'keys' in u.urlopen('http://keycloak:8080/realms/nautical-deliverance/protocol/openid-connect/certs').read()" \
  && ok "engine reaches the internal JWKS" || fail "engine cannot reach the JWKS"

if ((${#failures[@]})); then
  printf 'FAILED: %s\n' "${failures[@]}"
  exit 1
fi
echo "prod overlay OK"
