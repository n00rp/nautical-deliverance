#!/usr/bin/env bash
# Runs ON THE SERVER as the deploy user (B6-D3, B6-R07). Called by .github/workflows/deploy.yml:
#   nd/infra/deploy/deploy.sh <40-character sha>   check out that commit, build natively, restart
#   nd/infra/deploy/deploy.sh --check-backup       fail if the newest backup .ok is 26 h old or more
# It never removes volumes: the database must survive every deploy.
set -euo pipefail

# Everything lives in functions and ends with `exit`: the checkout below may replace this very file
# while bash is still reading it.
main() {
  local root
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  cd "$root"
  [[ -f infra/.env.prod ]] || { echo "ERROR: infra/.env.prod is missing (runbook, first deploy)" >&2; exit 1; }
  compose() {
    docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/.env.prod "$@"
  }

  if [[ "${1:-}" == "--check-backup" ]]; then
    compose exec -T backup /usr/local/bin/check_fresh.sh
    return
  fi

  local sha="${1:-}"
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "usage: deploy.sh <40-character commit sha>" >&2; exit 2; }

  git fetch --prune origin
  git checkout --detach "$sha"
  # A shell variable beats --env-file: the health endpoint shows exactly this commit.
  export ND_GIT_SHA="$sha"
  compose build
  compose up -d --remove-orphans --wait --wait-timeout 600
  docker image prune -f >/dev/null
  echo "deployed $sha"
}
main "$@"
exit
