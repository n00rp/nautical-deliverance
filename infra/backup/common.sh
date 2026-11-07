#!/usr/bin/env bash
# shellcheck disable=SC2034 # a sourced library: its callers use the variables
# Shared by backup.sh and restore.sh (sourced). B6-R06.
# Needs: ND_BACKUP_BUCKET, ND_BACKUP_S3_ENDPOINT, ND_BACKUP_S3_REGION, ND_BACKUP_S3_ACCESS_KEY,
# ND_BACKUP_S3_SECRET_KEY, and PGHOST/PGUSER/PGPASSWORD for a superuser.

RECIPIENTS="${ND_AGE_RECIPIENTS:-/etc/nd-backup/age-recipients.txt}"
APP_DB="${ND_APP_DB:-nd}"
KC_DB="${ND_KEYCLOAK_DB:-keycloak}"

die() { echo "ERROR: $*" >&2; exit 1; }

for v in ND_BACKUP_BUCKET ND_BACKUP_S3_ENDPOINT ND_BACKUP_S3_REGION ND_BACKUP_S3_ACCESS_KEY ND_BACKUP_S3_SECRET_KEY PGHOST PGUSER PGPASSWORD; do
  [[ -n "${!v:-}" ]] || die "$v is not set"
done

# R7: the committed recipients file holds a placeholder key nobody can decrypt with; a backup made
# with it is useless, and a restore pointed at it means the owner key was never installed.
if grep -q 'NOT-FOR-PRODUCTION-PLACEHOLDER' "$RECIPIENTS"; then
  die "$RECIPIENTS still holds the placeholder recipient; replace it with the owner's age public key (runbook)"
fi

# rclone S3 remote "nd" from the environment: no config file, no secret on a command line.
export RCLONE_CONFIG_ND_TYPE=s3 RCLONE_CONFIG_ND_PROVIDER=Other
export RCLONE_CONFIG_ND_ENDPOINT="$ND_BACKUP_S3_ENDPOINT" RCLONE_CONFIG_ND_REGION="$ND_BACKUP_S3_REGION"
export RCLONE_CONFIG_ND_ACCESS_KEY_ID="$ND_BACKUP_S3_ACCESS_KEY" RCLONE_CONFIG_ND_SECRET_ACCESS_KEY="$ND_BACKUP_S3_SECRET_KEY"
export RCLONE_CONFIG_ND_FORCE_PATH_STYLE=true RCLONE_CONFIG_ND_NO_CHECK_BUCKET=true
# A dead endpoint must fail within about a minute, not hang the nightly job.
RCLONE=(rclone --retries 2 --low-level-retries 3 --contimeout 10s --timeout 60s)
