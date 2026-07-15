#!/bin/sh
set -eu

: "${APP_DB_NAME:?APP_DB_NAME is required}"
: "${APP_DB_USER:?APP_DB_USER is required}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"
: "${APP_DB_OWNER:=${APP_DB_USER}_owner}"

# Passwords are generated as hexadecimal values in the deployment procedure,
# so they are safe to interpolate in the init-time SQL literal.
psql --username "$POSTGRES_USER" --dbname postgres --set=ON_ERROR_STOP=1 <<SQL
-- Create owner role (superuser-managed, no login, owns schema/tables/policies)
CREATE ROLE $APP_DB_OWNER NOLOGIN;

-- Create app role (login, application use, DML-only permissions)
CREATE ROLE $APP_DB_USER LOGIN PASSWORD '$APP_DB_PASSWORD';

-- Create database, owned by owner role
CREATE DATABASE $APP_DB_NAME OWNER $APP_DB_OWNER;
SQL

# Connect to the new database and set up RLS defaults and app role permissions
psql --username "$POSTGRES_USER" --dbname "$APP_DB_NAME" --set=ON_ERROR_STOP=1 <<SQL
-- Revoke default public permissions
REVOKE ALL ON SCHEMA public FROM public;
REVOKE ALL ON DATABASE $APP_DB_NAME FROM public;

-- Grant owner role all permissions on schema (owner-only operations)
GRANT ALL ON SCHEMA public TO $APP_DB_OWNER;

-- Grant app role usage (not create) on schema, and CONNECT on the database
-- (REVOKE ALL FROM public above also revokes the default public CONNECT
-- grant, so the app role needs it back explicitly or it can't log in at all)
GRANT CONNECT ON DATABASE $APP_DB_NAME TO $APP_DB_USER;
GRANT USAGE ON SCHEMA public TO $APP_DB_USER;

-- Set default privileges so future tables are owned by owner, app can SELECT/INSERT/UPDATE/DELETE
ALTER DEFAULT PRIVILEGES FOR USER $APP_DB_OWNER IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $APP_DB_USER;
ALTER DEFAULT PRIVILEGES FOR USER $APP_DB_OWNER IN SCHEMA public GRANT USAGE ON SEQUENCES TO $APP_DB_USER;
SQL
