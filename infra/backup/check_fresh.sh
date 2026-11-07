#!/usr/bin/env bash
# Backup staleness check (B6-R06/R07): exit 0 only if the newest .ok marker is less than 26 hours old
# (the nightly run is at 02:15 UTC, so a healthy bucket never exceeds ~24 h plus the upload time).
# Run inside the backup container: deploy.sh --check-backup. ND_BACKUP_MAX_AGE_HOURS overrides 26.
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"

max_hours="${ND_BACKUP_MAX_AGE_HOURS:-26}"
# "<modtime>;<path>" per marker; the time is UTC (TZ=UTC in the image).
newest="$("${RCLONE[@]}" lsf -R --files-only --include '*.ok' --format 'tp' --separator ';' "nd:$ND_BACKUP_BUCKET/nd/" | sort | tail -n 1)"
[[ -n "$newest" ]] || die "no backup .ok marker in the bucket"
stamp="${newest%%;*}"
age=$(($(date -u +%s) - $(date -u -d "$stamp" +%s)))
echo "newest backup marker: ${newest#*;} ($((age / 3600)) h old, limit $max_hours h)"
((age < max_hours * 3600)) || die "newest backup is $((age / 3600)) h old, limit $max_hours h"
