-- Creates (or updates) the app role and database for local development.
-- Run through scripts/setup_local_db.ps1, which passes :app_user, :app_password and :app_db from .env.
-- Safe to run more than once.

SELECT format('CREATE ROLE %I LOGIN', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user')
\gexec

-- CREATEDB lets Django's test runner create and drop its test database.
SELECT format('ALTER ROLE %I WITH LOGIN CREATEDB PASSWORD %L', :'app_user', :'app_password')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'app_db')
\gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'app_db', :'app_user')
\gexec

-- The Store Assistant's login. It can read only the store_data views (granted by the assistant app's migrations),
-- which show one store's data, and nothing else. Its sessions are read-only and stop runaway queries.
SELECT format('CREATE ROLE %I LOGIN', :'assistant_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'assistant_user')
\gexec

SELECT format('ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 20 PASSWORD %L',
              :'assistant_user', :'assistant_password')
\gexec

SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'assistant_user')
\gexec
SELECT format('ALTER ROLE %I SET statement_timeout = %L', :'assistant_user', '5s')
\gexec
SELECT format('ALTER ROLE %I SET idle_in_transaction_session_timeout = %L', :'assistant_user', '30s')
\gexec
SELECT format('ALTER ROLE %I SET search_path = store_data', :'assistant_user')
\gexec
