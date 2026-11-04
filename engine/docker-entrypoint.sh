#!/bin/sh
# Migrate (and optionally seed) as nd_owner, then serve as nd_app.
set -eu
alembic upgrade head
if [ "${ND_SEED_DEV_DATA:-false}" = "true" ]; then
  python -m nautical_deliverance.persistence.seed
fi
unset ND_MIGRATION_DATABASE_URL  # the server only ever needs the nd_app URL
exec uvicorn --factory nautical_deliverance.main:create_app --host 0.0.0.0 --port 8000
