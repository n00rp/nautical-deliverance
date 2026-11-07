#!/usr/bin/env bash
# Post-deploy smoke test against a running pilot (B6-R07). Read-only requests, no credentials.
# ND_SMOKE_BASE_URL  e.g. https://nd-pilot.duckdns.org   ND_SMOKE_SHA  the commit that must be live
set -euo pipefail
: "${ND_SMOKE_BASE_URL:?set ND_SMOKE_BASE_URL}" "${ND_SMOKE_SHA:?set ND_SMOKE_SHA}"
base="${ND_SMOKE_BASE_URL%/}"
failures=0
check() { # check <name> <expected status> <path>
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$base$3" || true)"
  if [[ "$code" == "$2" ]]; then echo "ok:   $1 = $code"; else echo "FAIL: $1 returned '$code', expected $2"; failures=1; fi
}
check "web" 200 /
check "health" 200 /api/v1/health
check "admin console is not public" 404 /admin/
check "master realm is not public" 404 /realms/master/.well-known/openid-configuration
check "pilot realm discovery" 200 /realms/nautical-deliverance/.well-known/openid-configuration
version="$(curl -sf --max-time 20 "$base/api/v1/health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])' || true)"
if [[ "$version" == "$ND_SMOKE_SHA" ]]; then echo "ok:   live version = $version"; else echo "FAIL: live version '$version', expected '$ND_SMOKE_SHA'"; failures=1; fi
exit "$failures"
