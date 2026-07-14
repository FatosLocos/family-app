#!/bin/sh
set -eu

: "${APP_DB_NAME:?APP_DB_NAME is required}"
: "${APP_DB_USER:?APP_DB_USER is required}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"

# Passwords are generated as hexadecimal values in the deployment procedure,
# so they are safe to interpolate in the init-time SQL literal.
psql --username "$POSTGRES_USER" --dbname postgres --set=ON_ERROR_STOP=1 <<SQL
CREATE ROLE $APP_DB_USER LOGIN PASSWORD '$APP_DB_PASSWORD';
CREATE DATABASE $APP_DB_NAME OWNER $APP_DB_USER;
SQL
