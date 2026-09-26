-- Read-only database role for the analytics service.
--
-- Run as the hawkerflow superuser AFTER the order service has created its
-- tables. The analytics service depends on another service's schema; that
-- dependency is intentional and its owner must be told before these columns
-- change.
--
-- Usage:
--   docker exec -i hawkerflow-postgres psql -U hawkerflow -d hawkerflow_order_db \
--     -v ro_password="$(cat vault/postgres.password)" -f - < scripts/create_readonly_role.sql
--
-- :'ro_password' is a psql variable bound at invocation, not string
-- interpolation into SQL text.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hawkerflow_analytics_ro') THEN
    CREATE ROLE hawkerflow_analytics_ro LOGIN;
  END IF;
END
$$;

ALTER ROLE hawkerflow_analytics_ro WITH PASSWORD :'ro_password';

GRANT CONNECT ON DATABASE hawkerflow_order_db TO hawkerflow_analytics_ro;
GRANT USAGE ON SCHEMA public TO hawkerflow_analytics_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO hawkerflow_analytics_ro;

-- Tables the order service adds later are readable too, without re-granting.
-- This applies only to tables created by the role running this script.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO hawkerflow_analytics_ro;

-- Explicitly withhold everything else. The runtime role must not be able to
-- create tables or modify a single order row.
REVOKE CREATE ON SCHEMA public FROM hawkerflow_analytics_ro;
