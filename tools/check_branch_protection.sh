#!/usr/bin/env bash
# req: S0-R12
# Verifies the GitHub merge settings (squash only). D-043: GitHub Free has no branch protection to check.
# Needs an authenticated `gh`. ND_REPO overrides the repository slug (tests use it with a fake gh).
set -uo pipefail

repo="${ND_REPO:-n00rp/nautical-deliverance}"
if ! json="$(gh api "repos/$repo" 2>&1)"; then
  echo "FAIL: cannot read repos/$repo (missing repo, or gh not installed/authenticated): $json" >&2
  exit 2
fi

failures=0
check() { # setting expected
  actual="$(grep -Eo "\"$1\" *: *(true|false)" <<<"$json" | grep -Eo '(true|false)$' || echo missing)"
  if [ "$actual" != "$2" ]; then
    echo "FAIL: $1 is $actual, expected $2" >&2
    failures=$((failures + 1))
  fi
}
check allow_squash_merge true
check allow_merge_commit false
check allow_rebase_merge false

[ "$failures" -eq 0 ] && echo "OK: merge settings of $repo match" || exit 1
