#!/bin/bash
# Creates the two application roles (D-034). Passwords come from the container environment.
# nd_owner owns the schema and runs migrations; nd_app is the runtime role: no DDL, no RLS bypass.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v owner_pw="$ND_DB_OWNER_PASSWORD" -v app_pw="$ND_DB_APP_PASSWORD" <<'SQL'
CREATE ROLE nd_owner LOGIN NOBYPASSRLS PASSWORD :'owner_pw';
CREATE ROLE nd_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_pw';
ALTER SCHEMA public OWNER TO nd_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO nd_app;
SQL

# PostGIS (D-033): mounting this directory hides the image's own init script, and nd_owner is not
# a superuser, so create the extension here as the superuser.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c 'CREATE EXTENSION IF NOT EXISTS postgis;'
