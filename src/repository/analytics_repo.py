"""Read-only queries against the order service's schema.

This service depends on another service's tables. That dependency is
intentional and documented: the order service's owner must be told before
any of these columns change.

Every query is parameterized and scoped to one stall and one Singapore day.
Nothing here writes, and the runtime role could not write even if it tried.
"""

import logging
from datetime import date
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from analytics.time_window import singapore_day_bounds_utc
from entities.order import Order
from entities.order_item import OrderItem
from entities.stall_order import StallOrder

logger = logging.getLogger("hawkerflow-analytics.repository")

COMPLETED = "COMPLETED"
CANCELLED_SPELLINGS = ("CANCELLED", "CANCELED")


class AnalyticsRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_partitions(self, stall_id: int, day: date) -> list[dict[str, Any]]:
        """One row per stall partition for this stall on this Singapore day.

        Deliberately does NOT join order_items. A partition holding three
        dishes must stay one row: joining would repeat it once per dish and
        its subtotal would then be counted three times. Dishes are fetched
        separately by fetch_completed_items.

        Returns every partition regardless of status, because the summary
        reports total, completed and cancelled counts.
        """
        start, end = singapore_day_bounds_utc(day)

        statement = (
            select(
                StallOrder.f_order_id,
                StallOrder.f_id,
                StallOrder.f_status,
                Order.f_status,
                StallOrder.f_subtotal,
                Order.f_created_at,
            )
            .join(Order, Order.f_id == StallOrder.f_order_id)
            .where(StallOrder.f_stall_id == stall_id)
            .where(Order.f_created_at >= start)
            .where(Order.f_created_at < end)
            .order_by(StallOrder.f_id)
        )

        with Session(self._engine) as session:
            rows = session.exec(statement).all()

        return [
            {
                "order_id": row[0],
                "stall_order_id": row[1],
                "stall_status": row[2],
                "parent_status": row[3],
                "subtotal": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]

    def fetch_completed_items(self, stall_id: int, day: date) -> list[dict[str, Any]]:
        """Dish rows belonging to completed partitions of this stall on this day.

        Scoped through the partition, not just order_items.f_stall_id, so a
        dish only counts when its own partition completed and its parent
        order was not cancelled.
        """
        start, end = singapore_day_bounds_utc(day)

        statement = (
            select(
                OrderItem.f_dish_id,
                OrderItem.f_dish_name,
                OrderItem.f_quantity,
                OrderItem.f_price,
            )
            .join(StallOrder, StallOrder.f_id == OrderItem.f_stall_order_id)
            .join(Order, Order.f_id == StallOrder.f_order_id)
            .where(OrderItem.f_stall_id == stall_id)
            .where(StallOrder.f_status == COMPLETED)
            .where(Order.f_status.notin_(CANCELLED_SPELLINGS))
            .where(Order.f_created_at >= start)
            .where(Order.f_created_at < end)
            .order_by(OrderItem.f_dish_id)
        )

        with Session(self._engine) as session:
            rows = session.exec(statement).all()

        return [
            {
                "dish_id": row[0],
                "dish_name": row[1],
                "quantity": row[2],
                "price": row[3],
            }
            for row in rows
        ]
