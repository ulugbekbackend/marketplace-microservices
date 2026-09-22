#!/bin/sh
# Runs once on first start: one database and one owner per service.
set -eu

: "${DB_PASSWORD:?DB_PASSWORD must be set}"

for service in auth catalog order payment; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
    CREATE USER ${service}_user WITH PASSWORD '${DB_PASSWORD}';
    CREATE DATABASE ${service}_db OWNER ${service}_user;
    REVOKE ALL ON DATABASE ${service}_db FROM PUBLIC;
SQL
done
