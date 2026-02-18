#!/bin/bash
# Creates the 'gitea' database inside the same PostgreSQL instance.
# Runs once on first container start (docker-entrypoint-initdb.d).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE gitea'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'gitea')\gexec
    GRANT ALL PRIVILEGES ON DATABASE gitea TO $POSTGRES_USER;
EOSQL
