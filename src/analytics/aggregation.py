"""Aggregation over plain row dictionaries.

Pure module: no framework and no database imports. The repository converts
database rows to dicts; nothing here touches a connection, so a future
Lambda adapter can reuse these functions unchanged.

Two rules run through all of it:

- Order counts are per parent order and deduplicated. One parent order can
  have two partitions at the same stall, and that is still one order.
- Money is summed per partition, from stall_orders.f_subtotal. Never from
  orders.f_total_price, which covers every stall in a shared order.
"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from analytics.time_window import to_singapore_hour

# Both spellings appear in the order service. Neither is authoritative.
CANCELLED_STATUSES = frozenset({"cancelled", "canceled"})
COMPLETED_STATUS = "completed"

PartitionRow = dict[str, Any]
ItemRow = dict[str, Any]


def money(value: Any) -> float:
    """Round to two places, half away from zero.

    Decimal's default is ROUND_HALF_EVEN, which turns 12.345 into 12.34 and
    loses a cent against a till reconciliation. str() first, so we quantize
    the decimal value the caller meant rather than its binary float error:
    Decimal(0.1 + 0.2) is 0.3000000000000000444, Decimal("0.30000000000000004")
    is not.
    """
    quantized = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(quantized)


def is_cancelled(status: str | None) -> bool:
    """True for either spelling, in any case."""
    if status is None:
        return False

    return status.strip().lower() in CANCELLED_STATUSES


def _is_completed(row: PartitionRow) -> bool:
    """A partition counts as completed only if its parent order survived."""
    if is_cancelled(row.get("parent_status")):
        return False

    stall_status = (row.get("stall_status") or "").strip().lower()
    return stall_status == COMPLETED_STATUS


def _is_cancelled_partition(row: PartitionRow) -> bool:
    return is_cancelled(row.get("stall_status")) or is_cancelled(row.get("parent_status"))


def summarise(partitions: list[PartitionRow]) -> dict[str, Any]:
    """Counts, value and average for one stall on one day.

    :param partitions: stall partition rows, one per stall_order
    :return: the summary fields of the API contract
    """
    total_orders = {r["order_id"] for r in partitions}
    completed_orders = {r["order_id"] for r in partitions if _is_completed(r)}
    cancelled_orders = {r["order_id"] for r in partitions if _is_cancelled_partition(r)}

    # Summed per partition, not per order: a parent order may hold two
    # partitions at this stall and both are this stall's money.
    completed_value = sum(
        (Decimal(str(r["subtotal"])) for r in partitions if _is_completed(r)),
        Decimal("0"),
    )

    completed_count = len(completed_orders)
    average = money(completed_value / Decimal(completed_count)) if completed_count else None

    return {
        "totalOrders": len(total_orders),
        "completedOrders": completed_count,
        "cancelledOrders": len(cancelled_orders),
        "completedOrderValue": money(completed_value),
        "averageCompletedOrderValue": average,
    }


def top_items(items: list[ItemRow], limit: int = 6) -> list[dict[str, Any]]:
    """Rank dishes by quantity sold.

    Ties break by dish id, so the order is stable across refreshes rather
    than following whatever order the database happened to return rows in.
    A dashboard that reshuffles on every refresh reads as untrustworthy.
    """
    merged: dict[int, dict[str, Any]] = {}

    for row in items:
        dish_id = row["dish_id"]
        entry = merged.setdefault(
            dish_id,
            {
                "dish_id": dish_id,
                "name": row["dish_name"],
                "quantity": 0,
                "value": Decimal("0"),
            },
        )
        entry["quantity"] += row["quantity"]
        entry["value"] += Decimal(str(row["price"])) * Decimal(row["quantity"])

    ranked = sorted(merged.values(), key=lambda e: (-e["quantity"], e["dish_id"]))

    return [
        {
            "dishId": e["dish_id"],
            "name": e["name"],
            "quantity": e["quantity"],
            "completedItemValue": money(e["value"]),
        }
        for e in ranked[:limit]
    ]


def hourly_orders(partitions: list[PartitionRow]) -> list[dict[str, Any]]:
    """Exactly 24 buckets, hours 0-23 in Singapore time.

    Every hour is present even when empty, so the chart keeps a stable shape
    and an absent hour is a real measured zero rather than a missing bar.
    """
    counts: dict[int, set[int]] = defaultdict(set)
    values: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

    for row in partitions:
        hour = to_singapore_hour(row["created_at"])
        counts[hour].add(row["order_id"])
        if _is_completed(row):
            values[hour] += Decimal(str(row["subtotal"]))

    return [
        {
            "hour": hour,
            "orderCount": len(counts[hour]),
            "completedOrderValue": money(values[hour]),
        }
        for hour in range(24)
    ]
