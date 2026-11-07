#!/usr/bin/env bash
# Backup staleness check (B6-R06/R07): exit 0 only if the newest .ok marker is less than 26 hours old,
# or if no marker exists yet (a pilot before its first nightly backup).
# The nightly run is at 02:15 UTC, so a healthy bucket never exceeds ~24 h plus the upload time.
# Run inside the backup container: deploy.sh --check-backup. ND_BACKUP_MAX_AGE_HOURS overrides 26.
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"

max_hours="${ND_BACKUP_MAX_AGE_HOURS:-26}"
# "<modtime>;<path>" per marker; the time is UTC (TZ=UTC in the image).
# rclone exit 3 = directory not found: the nd/ prefix does not exist before the first backup.
rc=0
listing="$("${RCLONE[@]}" lsf -R --files-only --include '*.ok' --format 'tp' --separator ';' "nd:$ND_BACKUP_BUCKET/nd/")" || rc=$?
case "$rc" in
  0 | 3) ;;
  *) die "cannot list nd:$ND_BACKUP_BUCKET/nd/ (rclone exit $rc): check endpoint, credentials and network" ;;
esac
newest="$(sort <<<"$listing" | tail -n 1)"
# No marker yet: the pilot has not had its first nightly backup, so there is nothing to be stale.
# A listing that fails (credentials, network) still fails above, and once one marker exists an old
# one fails below.
if [[ -z "$newest" ]]; then
  echo "WARNING: no backup .ok marker in the bucket yet (first backup pending); not stale, skipping"
  exit 0
fi
stamp="${newest%%;*}"
age=$(($(date -u +%s) - $(date -u -d "$stamp" +%s)))
echo "newest backup marker: ${newest#*;} ($((age / 3600)) h old, limit $max_hours h)"
((age < max_hours * 3600)) || die "newest backup is $((age / 3600)) h old, limit $max_hours h"
