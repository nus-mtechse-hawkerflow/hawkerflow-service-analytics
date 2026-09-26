"""HTTP contract tests.

The repository is stubbed: these test the route, its validation, its
identity check and its error mapping, not SQL. Database behaviour is
covered by tests/integration/test_analytics_repo.py.
"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from analytics.time_window import singapore_today
from endpoints.analytics_routes import analytics_router


class StubRepo:
    def __init__(self, partitions=None, items=None, error=None):
        self._partitions = partitions or []
        self._items = items or []
        self._error = error

    def fetch_partitions(self, stall_id, day):
        if self._error:
            raise self._error
        return self._partitions

    def fetch_completed_items(self, stall_id, day):
        if self._error:
            raise self._error
        return self._items


def build_client(repo) -> TestClient:
    app = FastAPI()
    app.include_router(analytics_router)
    app.state.analytics_repo = repo
    return TestClient(app, raise_server_exceptions=False)


def headers(stall_id):
    return {"X-Stall-ID": str(stall_id)}


def partition(order_id=1, stall_order_id=11, subtotal=12.50, hour_utc=4):
    return {
        "order_id": order_id,
        "stall_order_id": stall_order_id,
        "stall_status": "COMPLETED",
        "parent_status": "COMPLETED",
        "subtotal": subtotal,
        "created_at": datetime(2026, 9, 26, hour_utc, 0, 0),
    }


def test_summary_returns_the_full_contract():
    items = [{"dish_id": 1, "dish_name": "Chicken Rice", "quantity": 2, "price": 4.50}]
    client = build_client(StubRepo([partition()], items))

    response = client.get(
        "/v1/analytics/stalls/1/summary", params={"date": "2026-09-26"}, headers=headers(1)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stallId"] == 1
    assert body["date"] == "2026-09-26"
    assert body["timezone"] == "Asia/Singapore"
    assert body["source"] == "postgresql"
    assert body["totalOrders"] == 1
    assert body["completedOrders"] == 1
    assert body["completedOrderValue"] == 12.50
    assert body["averageCompletedOrderValue"] == 12.50
    assert len(body["hourlyOrders"]) == 24
    assert body["topItems"][0]["name"] == "Chicken Rice"
    assert body["unavailableMetrics"] == [
        "paymentBreakdown",
        "preparationTime",
        "takeawayFees",
        "shiftClosure",
    ]


# Review Focus 5: a stall with no rows is a confident zero, not an error.
def test_a_stall_with_no_orders_returns_zeros_and_status_200():
    client = build_client(StubRepo([], []))

    response = client.get(
        "/v1/analytics/stalls/7/summary", params={"date": "2026-09-26"}, headers=headers(7)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["totalOrders"] == 0
    assert body["completedOrders"] == 0
    assert body["cancelledOrders"] == 0
    assert body["completedOrderValue"] == 0.0
    assert body["averageCompletedOrderValue"] is None
    assert body["topItems"] == []
    assert len(body["hourlyOrders"]) == 24


def test_date_defaults_to_singapore_today_when_omitted():
    client = build_client(StubRepo([], []))

    response = client.get("/v1/analytics/stalls/1/summary", headers=headers(1))

    assert response.status_code == 200
    assert response.json()["date"] == singapore_today().isoformat()


@pytest.mark.parametrize("bad_date", ["not-a-date", "2026-13-01", "26-09-2026", "2026-09-31"])
def test_invalid_dates_return_422(bad_date):
    client = build_client(StubRepo())

    response = client.get(
        "/v1/analytics/stalls/1/summary", params={"date": bad_date}, headers=headers(1)
    )

    assert response.status_code == 422


@pytest.mark.parametrize("bad_stall", ["0", "-1", "abc"])
def test_invalid_stall_ids_return_422(bad_stall):
    client = build_client(StubRepo())

    response = client.get(
        f"/v1/analytics/stalls/{bad_stall}/summary", headers={"X-Stall-ID": bad_stall}
    )

    assert response.status_code == 422


def test_missing_identity_header_returns_401():
    client = build_client(StubRepo())

    response = client.get("/v1/analytics/stalls/1/summary")

    assert response.status_code == 401


def test_blank_identity_header_returns_401():
    client = build_client(StubRepo())

    response = client.get("/v1/analytics/stalls/1/summary", headers={"X-Stall-ID": "   "})

    assert response.status_code == 401


def test_malformed_identity_header_returns_401():
    client = build_client(StubRepo())

    response = client.get("/v1/analytics/stalls/1/summary", headers={"X-Stall-ID": "not-a-number"})

    assert response.status_code == 401


def test_mismatched_identity_header_returns_403():
    client = build_client(StubRepo())

    response = client.get("/v1/analytics/stalls/1/summary", headers=headers(2))

    assert response.status_code == 403


def test_database_failure_returns_503_and_leaks_nothing():
    error = OperationalError("SELECT 1", {}, Exception("password=REDACTED_LOCAL_DEV_PASSWORD connection refused"))
    client = build_client(StubRepo(error=error))

    response = client.get(
        "/v1/analytics/stalls/1/summary", params={"date": "2026-09-26"}, headers=headers(1)
    )

    assert response.status_code == 503
    body = response.text
    assert "REDACTED_LOCAL_DEV_PASSWORD" not in body
    assert "password" not in body.lower()
    assert "retry" in response.json()["detail"].lower()


def test_a_database_failure_never_returns_partial_figures():
    error = OperationalError("SELECT 1", {}, Exception("gone"))
    client = build_client(StubRepo(partitions=[partition()], error=error))

    response = client.get("/v1/analytics/stalls/1/summary", headers=headers(1))

    assert response.status_code == 503
    assert "completedOrderValue" not in response.text
