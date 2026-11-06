#!/bin/bash
# Production only: Keycloak keeps its data in its own database on this Postgres (the dev stack uses
# Keycloak's built-in H2). Runs only when the prod overlay passes ND_DB_KEYCLOAK_PASSWORD.
# Init scripts are sourced, not executed, when not executable: no `exit` here.
if [ -n "${ND_DB_KEYCLOAK_PASSWORD:-}" ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v kc_pw="$ND_DB_KEYCLOAK_PASSWORD" <<'SQL'
CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'kc_pw';
CREATE DATABASE keycloak OWNER keycloak;
SQL
fi
