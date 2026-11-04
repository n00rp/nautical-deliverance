#!/usr/bin/env bash
# req: S0-R12
# Verifies the GitHub merge settings (squash only). D-043: GitHub Free has no branch protection to check.
# Needs an authenticated `gh`. ND_REPO overrides the repository slug (tests use it with a fake gh).
set -uo pipefail

repo="${ND_REPO:-n00rp/nautical-deliverance}"
# gh's built-in jq reads only top-level keys (nested objects such as `parent` repeat allow_*_merge).
# A null or missing key becomes the non-whitespace placeholder "missing" (an empty field would
# shift the others left when read) and counts as a mismatch.
JQ='[.allow_squash_merge, .allow_merge_commit, .allow_rebase_merge] | map(if . == null then "missing" else tostring end) | @tsv'
if ! out="$(gh api "repos/$repo" --jq "$JQ" 2>&1)"; then
  echo "FAIL: cannot read repos/$repo (missing repo, or gh not installed/authenticated): $out" >&2
  exit 2
fi
IFS=$'\t' read -r squash merge rebase <<<"$out"

failures=0
check() { # setting actual expected
  if [ "$2" != "$3" ]; then
    echo "FAIL: $1 is $2, expected $3" >&2
    failures=$((failures + 1))
  fi
}
check allow_squash_merge "$squash" true
check allow_merge_commit "$merge" false
check allow_rebase_merge "$rebase" false

[ "$failures" -eq 0 ] && echo "OK: merge settings of $repo match" || exit 1
