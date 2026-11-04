#!/bin/sh
# Migrate (and optionally seed) as nd_owner, then serve as nd_app.
set -eu
# Bounded wait for the database (works without compose depends_on).
i=0
until python -c "import os,psycopg; psycopg.connect(os.environ['ND_MIGRATION_DATABASE_URL'].replace('+psycopg',''), connect_timeout=2).close()" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then echo "database not reachable after 30 attempts" >&2; exit 1; fi
  sleep 1
done
alembic upgrade head
if [ "${ND_SEED_DEV_DATA:-false}" = "true" ]; then
  python -m nautical_deliverance.persistence.seed
fi
unset ND_MIGRATION_DATABASE_URL  # the server only ever needs the nd_app URL
exec uvicorn --factory nautical_deliverance.main:create_app --host 0.0.0.0 --port 8000
