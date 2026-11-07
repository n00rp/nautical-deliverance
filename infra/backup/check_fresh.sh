#!/usr/bin/env bash
# Backup staleness check (B6-R06/R07): exit 0 only if the bucket is reachable and the newest .ok
# marker is less than 26 hours old, or if no marker exists yet and the first deploy (ND_FIRST_DEPLOYED,
# a UTC timestamp passed in by deploy.sh --check-backup) was less than 26 hours ago.
# The nightly run is at 02:15 UTC, so a healthy bucket never exceeds ~24 h plus the upload time.
# Run inside the backup container: deploy.sh --check-backup. ND_BACKUP_MAX_AGE_HOURS overrides 26.
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"

max_hours="${ND_BACKUP_MAX_AGE_HOURS:-26}"
# The bucket first: rclone exit 3 means "not found" for a missing bucket as well as a missing prefix,
# so a mistyped ND_BACKUP_BUCKET must not pass as "no backup yet".
"${RCLONE[@]}" lsd "nd:$ND_BACKUP_BUCKET" >/dev/null ||
  die "bucket $ND_BACKUP_BUCKET is missing or not accessible: check ND_BACKUP_BUCKET, endpoint, credentials and network"
# "<modtime>;<path>" per marker; the time is UTC (TZ=UTC in the image).
# rclone exit 3 here = the nd/ prefix does not exist before the first backup.
rc=0
listing="$("${RCLONE[@]}" lsf -R --files-only --include '*.ok' --format 'tp' --separator ';' "nd:$ND_BACKUP_BUCKET/nd/")" || rc=$?
case "$rc" in
  0 | 3) ;;
  *) die "cannot list nd:$ND_BACKUP_BUCKET/nd/ (rclone exit $rc): check endpoint, credentials and network" ;;
esac
newest="$(sort <<<"$listing" | tail -n 1)"
if [[ -z "$newest" ]]; then
  # No marker: allowed only for max_hours after the first deploy; a backup that never succeeds must fail.
  [[ -n "${ND_FIRST_DEPLOYED:-}" ]] ||
    die "no backup .ok marker and no FIRST_DEPLOYED record (/srv/nd/FIRST_DEPLOYED): cannot tell how long the stack has run"
  up=$(($(date -u +%s) - $(date -u -d "$ND_FIRST_DEPLOYED" +%s)))
  ((up < max_hours * 3600)) ||
    die "no backup .ok marker, and the first deploy was $((up / 3600)) h ago (limit $max_hours h): the nightly backup is not succeeding"
  echo "WARNING: no backup .ok marker yet (first deploy $((up / 3600)) h ago, grace $max_hours h); not stale"
  exit 0
fi
stamp="${newest%%;*}"
age=$(($(date -u +%s) - $(date -u -d "$stamp" +%s)))
echo "newest backup marker: ${newest#*;} ($((age / 3600)) h old, limit $max_hours h)"
((age < max_hours * 3600)) || die "newest backup is $((age / 3600)) h old, limit $max_hours h"
