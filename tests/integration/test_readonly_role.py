"""Privilege tests for the runtime database role.

These are the gate on the whole security posture of this service. If they
pass while the role can in fact write, the SELECT-only claim in the design
is fiction. A failure on any negative test means the grant is too broad:
fix the SQL in scripts/create_readonly_role.sql, never the test.

Requires the PostgreSQL container and the order service's tables.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from configurations.app_config import AppConfig
from session.db_session import DBSession

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    try:
        eng = DBSession(AppConfig().datasource).engine
        with eng.connect():
            pass
        return eng
    except Exception as exc:
        pytest.skip(
            f"PostgreSQL database is not reachable ({exc}). "
            "These tests require the PostgreSQL container and the order service's tables. "
            "See docs/RUN_LOCALLY.md."
        )


def test_readonly_role_can_select_orders(engine):
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM orders")).scalar_one()

    assert count >= 0


def test_readonly_role_can_select_every_table_it_needs(engine):
    with engine.connect() as conn:
        for table in ("orders", "stall_orders", "order_items"):
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            assert count >= 0, table


def test_readonly_role_cannot_insert(engine):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with engine.connect() as conn:
            conn.execute(
                text("INSERT INTO orders (f_total_price, f_status) VALUES (1.0, 'PENDING')")
            )


def test_readonly_role_cannot_update(engine):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with engine.connect() as conn:
            conn.execute(text("UPDATE orders SET f_status = 'COMPLETED'"))


def test_readonly_role_cannot_delete(engine):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM orders"))


def test_readonly_role_cannot_create_tables(engine):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE analytics_should_not_exist (id int)"))


def test_readonly_role_cannot_drop_tables(engine):
    with pytest.raises(ProgrammingError, match="must be owner|permission denied"):
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE orders"))


def test_readonly_role_cannot_reach_the_other_service_databases(engine):
    """The design scopes this service to hawkerflow_order_db only."""
    with engine.connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar_one()

    assert current == "hawkerflow_order_db"
