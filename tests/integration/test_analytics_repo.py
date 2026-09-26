"""Repository tests against a real PostgreSQL database.

Fixtures insert through a separate superuser connection, because the
runtime role deliberately cannot write. Every test cleans up only the rows
it created, and seeds under a stall id no sample data uses, so these never
disturb demo rows or each other.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, text

from configurations.app_config import AppConfig
from repository.analytics_repo import AnalyticsRepo
from session.db_session import DBSession

# An id the seed script never uses, so tests never collide with demo data.
SEED_STALL = 9001
OTHER_STALL = 9002

ADMIN_URL = "postgresql+psycopg2://hawkerflow:REDACTED_LOCAL_DEV_PASSWORD@localhost:5432/hawkerflow_order_db"


@pytest.fixture(scope="module")
def ro_engine():
    return DBSession(AppConfig().datasource).engine


@pytest.fixture(scope="module")
def admin_engine():
    """Fixture-only writer. Never used by service code."""
    return create_engine(ADMIN_URL)


@pytest.fixture
def seeded(admin_engine):
    created: list[int] = []

    def _insert(created_at: datetime, partitions: list[dict], parent_status: str = "COMPLETED"):
        total = sum(p["subtotal"] for p in partitions)

        with admin_engine.begin() as conn:
            order_id = conn.execute(
                text(
                    "INSERT INTO orders (f_total_price, f_created_at, f_status) "
                    "VALUES (:total, :created, :status) RETURNING f_id"
                ),
                {"total": total, "created": created_at, "status": parent_status},
            ).scalar_one()
            created.append(order_id)

            for p in partitions:
                stall_order_id = conn.execute(
                    text(
                        "INSERT INTO stall_orders "
                        "(f_order_id, f_stall_id, f_status, f_subtotal) "
                        "VALUES (:oid, :sid, :status, :sub) RETURNING f_id"
                    ),
                    {
                        "oid": order_id,
                        "sid": p["stall_id"],
                        "status": p.get("status", "COMPLETED"),
                        "sub": p["subtotal"],
                    },
                ).scalar_one()

                for dish in p.get("dishes", []):
                    conn.execute(
                        text(
                            "INSERT INTO order_items (f_order_id, f_stall_order_id, "
                            "f_stall_id, f_dish_id, f_dish_name, f_quantity, f_price) "
                            "VALUES (:oid, :soid, :sid, :did, :name, :qty, :price)"
                        ),
                        {
                            "oid": order_id,
                            "soid": stall_order_id,
                            "sid": p["stall_id"],
                            "did": dish["dish_id"],
                            "name": dish["name"],
                            "qty": dish["quantity"],
                            "price": dish["price"],
                        },
                    )

        return order_id

    yield _insert

    with admin_engine.begin() as conn:
        for order_id in created:
            conn.execute(text("DELETE FROM order_items WHERE f_order_id = :o"), {"o": order_id})
            conn.execute(text("DELETE FROM stall_orders WHERE f_order_id = :o"), {"o": order_id})
            conn.execute(text("DELETE FROM orders WHERE f_id = :o"), {"o": order_id})


def test_fetch_partitions_scopes_to_the_requested_stall(ro_engine, seeded):
    seeded(
        datetime(2026, 9, 26, 4, 0),
        [
            {"stall_id": SEED_STALL, "subtotal": 10.0},
            {"stall_id": OTHER_STALL, "subtotal": 99.0},
        ],
    )

    rows = AnalyticsRepo(ro_engine).fetch_partitions(SEED_STALL, date(2026, 9, 26))

    assert len(rows) == 1
    assert rows[0]["subtotal"] == 10.0


# Review Focus 2: dish rows must not multiply the subtotal.
def test_a_partition_with_three_dishes_is_returned_once(ro_engine, seeded):
    seeded(
        datetime(2026, 9, 26, 4, 0),
        [
            {
                "stall_id": SEED_STALL,
                "subtotal": 12.0,
                "dishes": [
                    {"dish_id": 1, "name": "A", "quantity": 1, "price": 4.0},
                    {"dish_id": 2, "name": "B", "quantity": 1, "price": 4.0},
                    {"dish_id": 3, "name": "C", "quantity": 1, "price": 4.0},
                ],
            }
        ],
    )

    rows = AnalyticsRepo(ro_engine).fetch_partitions(SEED_STALL, date(2026, 9, 26))

    assert len(rows) == 1
    assert sum(r["subtotal"] for r in rows) == 12.0


def test_fetch_partitions_respects_the_singapore_day_boundary(ro_engine, seeded):
    # 15:59 UTC on 25 Sep == 23:59 SGT on 25 Sep -> the previous day
    seeded(datetime(2026, 9, 25, 15, 59), [{"stall_id": SEED_STALL, "subtotal": 5.0}])
    # 16:00 UTC on 25 Sep == 00:00 SGT on 26 Sep -> this day
    seeded(datetime(2026, 9, 25, 16, 0), [{"stall_id": SEED_STALL, "subtotal": 7.0}])

    rows = AnalyticsRepo(ro_engine).fetch_partitions(SEED_STALL, date(2026, 9, 26))

    assert [r["subtotal"] for r in rows] == [7.0]


def test_fetch_partitions_returns_both_partitions_of_a_split_order(ro_engine, seeded):
    seeded(
        datetime(2026, 9, 26, 4, 0),
        [
            {"stall_id": SEED_STALL, "subtotal": 10.0},
            {"stall_id": SEED_STALL, "subtotal": 5.0},
        ],
    )

    rows = AnalyticsRepo(ro_engine).fetch_partitions(SEED_STALL, date(2026, 9, 26))

    assert len(rows) == 2
    assert len({r["order_id"] for r in rows}) == 1
    assert sorted(r["subtotal"] for r in rows) == [5.0, 10.0]


def test_fetch_partitions_carries_both_statuses(ro_engine, seeded):
    seeded(
        datetime(2026, 9, 26, 4, 0),
        [{"stall_id": SEED_STALL, "subtotal": 3.0, "status": "PENDING"}],
        parent_status="CANCELLED",
    )

    rows = AnalyticsRepo(ro_engine).fetch_partitions(SEED_STALL, date(2026, 9, 26))

    assert rows[0]["stall_status"] == "PENDING"
    assert rows[0]["parent_status"] == "CANCELLED"


def test_fetch_completed_items_returns_dishes_of_completed_partitions(ro_engine, seeded):
    seeded(
        datetime(2026, 9, 26, 4, 0),
        [
            {
                "stall_id": SEED_STALL,
                "subtotal": 9.0,
                "dishes": [{"dish_id": 3, "name": "Laksa", "quantity": 2, "price": 4.50}],
            }
        ],
    )

    items = AnalyticsRepo(ro_engine).fetch_completed_items(SEED_STALL, date(2026, 9, 26))

    assert len(items) == 1
    assert items[0]["dish_name"] == "Laksa"
    assert items[0]["quantity"] == 2


def test_fetch_completed_items_excludes_pending_partitions(ro_engine, seeded):
    seeded(
        datetime(2026, 9, 26, 4, 0),
        [
            {
                "stall_id": SEED_STALL,
                "subtotal": 4.0,
                "status": "PENDING",
                "dishes": [{"dish_id": 7, "name": "Pending Dish", "quantity": 1, "price": 4.0}],
            }
        ],
        parent_status="PENDING",
    )

    items = AnalyticsRepo(ro_engine).fetch_completed_items(SEED_STALL, date(2026, 9, 26))

    assert items == []


def test_fetch_completed_items_excludes_a_cancelled_parent(ro_engine, seeded):
    seeded(
        datetime(2026, 9, 26, 4, 0),
        [
            {
                "stall_id": SEED_STALL,
                "subtotal": 4.0,
                "dishes": [{"dish_id": 8, "name": "Voided", "quantity": 1, "price": 4.0}],
            }
        ],
        parent_status="CANCELLED",
    )

    items = AnalyticsRepo(ro_engine).fetch_completed_items(SEED_STALL, date(2026, 9, 26))

    assert items == []


def test_an_unknown_stall_returns_an_empty_list_not_an_error(ro_engine):
    repo = AnalyticsRepo(ro_engine)

    assert repo.fetch_partitions(424242, date(2026, 9, 26)) == []
    assert repo.fetch_completed_items(424242, date(2026, 9, 26)) == []
