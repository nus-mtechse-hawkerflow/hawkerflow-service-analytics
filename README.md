# hawkerflow-service-analytics

Per-stall daily order statistics for the HawkerFlow hawker dashboard.

This service reads the order service's PostgreSQL database through a SELECT-only
role and writes nothing, anywhere. It is the backend for the analytics screen in
`hawker-ui`, which previously computed its figures from in-browser order state.

## Status

Working and integrated. Runs on `127.0.0.1:8083` against a local PostgreSQL
instance, and the hawker dashboard reads its figures from it — verified end to
end on 2026-09-27 against the running stack, with the API's numbers matching
SQL exactly. The frontend side lives on the `hawker-ui` branch
`analytics-integration`.

AWS deployment, Lambda packaging, Cognito and event-driven aggregation are
deliberately out of scope — see [Deferred](#deferred).

## The endpoint

```
GET /hawkerflow/v1/analytics/stalls/{stall_id}/summary?date=YYYY-MM-DD
```

`date` defaults to today's Singapore calendar date. The `X-Stall-ID` header must
match `stall_id`.

```json
{
  "stallId": 1,
  "date": "2026-09-26",
  "timezone": "Asia/Singapore",
  "source": "postgresql",
  "totalOrders": 12,
  "completedOrders": 10,
  "cancelledOrders": 1,
  "completedOrderValue": 128.40,
  "averageCompletedOrderValue": 12.84,
  "topItems": [
    { "dishId": 1, "name": "Chicken Rice", "quantity": 14, "completedItemValue": 63.00 }
  ],
  "hourlyOrders": [{ "hour": 0, "orderCount": 0, "completedOrderValue": 0.0 }],
  "unavailableMetrics": [
    "paymentBreakdown", "preparationTime", "takeawayFees", "shiftClosure"
  ]
}
```

`hourlyOrders` always has exactly 24 entries. `averageCompletedOrderValue` is
`null` when nothing completed — never `0`, which would read as a measurement.

| Status | Meaning |
|---|---|
| 200 | Success. A stall with no orders returns zeros, not an error. |
| 401 | `X-Stall-ID` missing or malformed |
| 403 | `X-Stall-ID` does not match the requested stall |
| 422 | Invalid stall id or date |
| 503 | Database unavailable. Generic message; details go to the log, not the client. |

`GET /hawkerflow/health` reports process liveness without touching the database.

## Why some metrics are unavailable

The order schema records no payment method, no preparation timestamps, no
takeaway fee and no shift record. Rather than invent numbers, the API names
these in `unavailableMetrics` and the dashboard says so plainly. The previous
frontend-only implementation displayed a hardcoded `4.2` minute preparation
time; that is exactly what this service exists to stop.

## Design notes

**Money comes from `stall_orders.f_subtotal`, never `orders.f_total_price`.**
An order can span several stalls, and the parent total covers all of them.

**Order counts deduplicate by parent order.** One parent order can hold two
partitions at the same stall; that is one order, and both subtotals.

**Two queries, not one join.** Joining `order_items` onto stall partitions would
repeat a partition once per dish and multiply its subtotal. Dishes are fetched
separately.

**Money rounds half up.** The order schema's money columns are `double
precision`. `Decimal`'s default `ROUND_HALF_EVEN` turns `12.345` into `12.34`
and loses a cent against a till reconciliation. See
`src/analytics/aggregation.py`.

**Singapore days are converted to naive UTC.** `orders.f_created_at` is
`timestamp without time zone` holding UTC wall-clock, so a Singapore day runs
from 16:00 UTC the previous day. See `src/analytics/time_window.py`.

**`src/analytics/` is pure.** No FastAPI, no SQLAlchemy. A future Lambda adapter
can call the same aggregation and time-window functions unchanged.

## Schema dependency

This service reads tables owned by `hawkerflow-service-order`: `orders`,
`stall_orders` and `order_items`. That dependency is intentional. **The order
service's owner should tell this service's owner before changing those
columns.** `src/entities/` holds read-only mirrors used only to build typed
selects; they are never passed to `create_all`.

## Security

- Binds to loopback only. Not reachable from the network.
- CORS grants exactly one origin, `http://localhost:4200`. GET only.
- The runtime database role cannot INSERT, UPDATE, DELETE or CREATE TABLE.
  Four tests in `tests/integration/test_readonly_role.py` assert each denial.
- **`X-Stall-ID` is not authentication.** It is a local development convention;
  any client can set any value. It makes accidental cross-stall requests loud,
  nothing more. Production identity is deferred.
- No credential is committed. `vault/` and `resources/config.local.yml` are
  gitignored, and the integration tests read the setup password from the
  environment.

## Running it

See [docs/RUN_LOCALLY.md](docs/RUN_LOCALLY.md) for full setup, including
creating the order service's tables and the read-only role.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
make run
```

```bash
make test    # pytest
make lint    # ruff
```

The repository integration tests need the setup role and skip with an
explanatory message when `ANALYTICS_TEST_ADMIN_PASSWORD` is unset.

## Sample data

`scripts/seed_sample_orders.py` creates orders through the order service's HTTP
API. It is run by hand only, never at startup, and never deletes or resets
existing rows — repeated runs add another batch.

## Deferred

AWS deployment, Lambda and API Gateway infrastructure, Cognito, event-driven
aggregates, payment and shift schema changes, real diner checkout integration,
production identity and production database networking.

The organisation's `hawkerflow` umbrella repository contains an earlier
DynamoDB-and-SQS analytics Lambda. It was not reused: it is the superseded
architecture from before the team split into per-service repositories on FastAPI
and PostgreSQL. One idea from it is worth keeping — it stored money as integer
cents, which removes the rounding question entirely, and is the better answer if
the order schema is ever migrated.

## Integration

Wiring this into the hawker dashboard: see [docs/INTEGRATION.md](docs/INTEGRATION.md).
