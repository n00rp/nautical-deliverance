#!/usr/bin/env bash
# Runs ON THE SERVER as the deploy user (B6-D3, B6-R07). Called by .github/workflows/deploy.yml:
#   nd/infra/deploy/deploy.sh [--allow-rollback] <40-character sha>   check out that commit, build natively, restart
#   nd/infra/deploy/deploy.sh --check-backup                           fail if the newest backup .ok is 26 h old or more
# It never removes volumes: the database must survive every deploy.
# Guards: the commit must be on origin/main, and must not be older than the commit running now
# (recorded in $ND_DEPLOYED_SHA_FILE, default /srv/nd/DEPLOYED_SHA) unless --allow-rollback is given.
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

  local rollback=0
  if [[ "${1:-}" == "--allow-rollback" ]]; then rollback=1; shift; fi
  local sha="${1:-}"
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "usage: deploy.sh [--allow-rollback] <40-character commit sha>" >&2; exit 2; }
  local state="${ND_DEPLOYED_SHA_FILE:-/srv/nd/DEPLOYED_SHA}"

  git fetch --prune origin
  # I5: only a commit that is part of main (a feature branch fetched above is not).
  git merge-base --is-ancestor "$sha" origin/main ||
    { echo "ERROR: $sha is not an ancestor of origin/main: refusing to deploy it" >&2; exit 1; }
  # Two CI runs finishing out of order must not move the pilot back to an older commit.
  local deployed=""
  [[ -s "$state" ]] && deployed="$(<"$state")"
  if [[ -n "$deployed" && "$deployed" != "$sha" ]] && git merge-base --is-ancestor "$sha" "$deployed" 2>/dev/null && ((!rollback)); then
    echo "ERROR: $sha is older than the deployed $deployed: pass --allow-rollback to go back on purpose" >&2
    exit 1
  fi

  git checkout --detach "$sha"
  # A shell variable beats --env-file: the health endpoint shows exactly this commit.
  export ND_GIT_SHA="$sha"
  compose build
  compose up -d --remove-orphans --wait --wait-timeout 600
  printf '%s\n' "$sha" >"$state"
  docker image prune -f >/dev/null
  echo "deployed $sha"
}
main "$@"
exit
