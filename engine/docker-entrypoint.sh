#!/bin/sh
# Migrate (and optionally seed) as nd_owner, then serve as nd_app.
set -eu
# Compose puts the raw passwords into the URLs: encode them so a '/', '@' or ':' cannot end the
# userinfo early for libpq or SQLAlchemy (C2).
ND_DATABASE_URL="$(python -m nautical_deliverance.persistence.dburl ND_DATABASE_URL)"
ND_MIGRATION_DATABASE_URL="$(python -m nautical_deliverance.persistence.dburl ND_MIGRATION_DATABASE_URL)"
export ND_DATABASE_URL ND_MIGRATION_DATABASE_URL
# Bounded wait for the database (works without compose depends_on).
i=0
until python -c "import os,psycopg; psycopg.connect(os.environ['ND_MIGRATION_DATABASE_URL'].replace('+psycopg',''), connect_timeout=2).close()" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then echo "database not reachable after 30 attempts" >&2; exit 1; fi
  sleep 1
done
alembic upgrade head
case "${ND_SEED:-}" in
  "") ;;
  dev|pilot) python -m nautical_deliverance.persistence.seed ;;
  *) echo "ND_SEED must be dev, pilot or empty (got '${ND_SEED}')" >&2; exit 1 ;;
esac
unset ND_MIGRATION_DATABASE_URL  # the server only ever needs the nd_app URL
exec uvicorn --factory nautical_deliverance.main:create_app --host 0.0.0.0 --port 8000
