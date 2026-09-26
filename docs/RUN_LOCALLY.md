# Running the analytics service locally

This service reports per-stall daily order statistics for the hawker dashboard.
It reads the order service's PostgreSQL database through a SELECT-only role and
writes nothing, anywhere.

## Prerequisites

- Docker, with the `hawkerflow-postgres` container running (PostgreSQL 17, exposed on `127.0.0.1:5432`)
- Python 3.12
- The `hawkerflow-service-order` repository checked out as a sibling directory

Check the container is up:

```bash
docker ps --filter name=hawkerflow-postgres
```

## 1. Create the virtual environment

```bash
cd hawkerflow-service-analytics
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
```

## 2. Create the order service's tables

The analytics service **never** creates tables. The order service owns this
schema, so the tables must come from it.

Two things to know before you run this:

1. The order service may have no virtual environment in your checkout. Create
   one and install `requirements.txt` first.
2. Its tracked `vault/postgres.user` and `vault/postgres.password` hold
   placeholder values that the local container rejects. **Do not edit those
   tracked files.** Point `PROJECT_ROOT` at a scratch directory instead.

`AppConfig` resolves both its YAML file and its secrets directory from
`PROJECT_ROOT`, so one scratch directory overrides both:

```bash
cd ../hawkerflow-service-order
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

SCRATCH=/tmp/order-root
mkdir -p "$SCRATCH/vault" "$SCRATCH/resources"

# Read the container's own credentials rather than writing them down here.
docker inspect hawkerflow-postgres \
  --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^POSTGRES_USER=' \
  | cut -d= -f2- | tr -d '\n' > "$SCRATCH/vault/postgres.user"
docker inspect hawkerflow-postgres \
  --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^POSTGRES_PASSWORD=' \
  | cut -d= -f2- | tr -d '\n' > "$SCRATCH/vault/postgres.password"

sed -e 's/^\(  enabled:\) true/\1 false/' resources/config.yml > "$SCRATCH/resources/config.yml"

PROJECT_ROOT="$SCRATCH" PYTHONPATH=src .venv/Scripts/python -c "
from configurations.app_config import AppConfig
from session.db_session import DBSession
from sqlmodel import SQLModel
import entities.order, entities.stall_order, entities.order_item
SQLModel.metadata.create_all(DBSession(AppConfig().datasource).engine)
print('create_all completed')
"
```

The `sed` disables the SQS worker and the event publisher, which would
otherwise try to reach a LocalStack instance that is not running.

> Do **not** try `SQS__ENABLED=false` as an environment variable. The order
> service's `AppConfig` sets no `env_nested_delimiter`, so nested overrides
> through the environment do not bind — they fail silently, leaving SQS enabled.

Verify:

```bash
docker exec hawkerflow-postgres psql -U hawkerflow -d hawkerflow_order_db -c "\dt"
```

Expected: `orders`, `stall_orders`, `order_items`.

## 3. Confirmed column types

Verified 2026-09-26 against the live database:

| Table | Column | Type |
|---|---|---|
| orders | f_created_at | `timestamp without time zone` |
| orders | f_total_price | `double precision` |
| stall_orders | f_subtotal | `double precision` |
| order_items | f_price | `double precision` |

Two consequences the code depends on:

- `f_created_at` is timezone-naive and holds UTC wall-clock time, so the
  Singapore day boundaries in `analytics/time_window.py` are computed as naive
  UTC. A Singapore day always starts at 16:00 UTC the previous day.
- The money columns are binary floats, not `numeric`. `analytics/aggregation.py`
  converts through `str()` into `Decimal` and rounds half-up, because Python's
  default rounding would turn `12.345` into `12.34` and lose a cent against a
  till reconciliation. Migrating these columns is explicitly out of scope.

If either of these ever changes, the time window and aggregation modules both
need revisiting.

## 4. Create the read-only role

```bash
cd ../hawkerflow-service-analytics
printf 'hawkerflow_analytics_ro' > vault/postgres.user
.venv/Scripts/python -c "import secrets; print(secrets.token_urlsafe(24), end='')" > vault/postgres.password

docker exec -i hawkerflow-postgres psql -U hawkerflow -d hawkerflow_order_db \
  -v ro_password="$(cat vault/postgres.password)" -f - < scripts/create_readonly_role.sql
```

`vault/` is gitignored. Setup credentials (the `hawkerflow` superuser) and
runtime credentials (`hawkerflow_analytics_ro`) are deliberately separate: the
runtime role cannot create tables or modify a single order row.

Prove it:

```bash
PROJECT_ROOT=. .venv/Scripts/python -m pytest tests/integration/test_readonly_role.py -v
```

Expected: 8 passed, including four tests asserting that INSERT, UPDATE, DELETE
and CREATE TABLE are all denied.

### Running the repository integration tests

`tests/integration/test_analytics_repo.py` seeds rows to query back, which the
runtime role deliberately cannot do. It needs the setup role, supplied through
the environment so that no credential is committed to this repository:

```bash
export ANALYTICS_TEST_ADMIN_PASSWORD=$(docker inspect hawkerflow-postgres \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep '^POSTGRES_PASSWORD=' | cut -d= -f2-)

PROJECT_ROOT=. .venv/Scripts/python -m pytest tests/integration -v
```

Without that variable the repository tests skip with an explanatory message
rather than failing. `ANALYTICS_TEST_ADMIN_USER`, `_HOST`, `_PORT` and `_DB`
override the defaults if your local setup differs.

## 5. Configuration

```bash
cp resources/config.local.example.yml resources/config.local.yml
```

`config.local.yml` is gitignored. Credentials live only in `vault/`, never in
any YAML file and never in the repository.

## 6. Run

```bash
make run
```

The service binds to `127.0.0.1:8083` — loopback only — and accepts browser
requests from `http://localhost:4200` alone.

```bash
curl -s http://127.0.0.1:8083/hawkerflow/health
```

## Security notes

**`X-Stall-ID` is not authentication.** It is a local development convention.
Any client can set any value. A missing or malformed header returns 401 and a
mismatch against the requested stall returns 403, but this only makes accidental
cross-stall requests loud — it stops nobody deliberate. Production identity is
explicitly deferred.

The service binds to loopback so it is not reachable from the network. Do not
change the host without also solving identity.

## What feeds these analytics

Only orders **persisted through the order service API**. The diner checkout,
the hawker POS, the KDS and the mock login keep their existing browser-side
flows, and orders that live only in browser state do not appear here.

If a number on the dashboard looks wrong, check first whether the order was
actually persisted:

```bash
docker exec hawkerflow-postgres psql -U hawkerflow -d hawkerflow_order_db \
  -c "SELECT count(*) FROM orders;"
```

## Sample data

See `scripts/seed_sample_orders.py`. It creates orders through the order service
HTTP API, is run by hand only, never runs at application startup, and never
deletes or resets existing rows. Running it repeatedly adds another batch.
