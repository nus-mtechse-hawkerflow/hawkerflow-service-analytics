from datetime import datetime

from analytics.aggregation import (
    hourly_orders,
    is_cancelled,
    money,
    summarise,
    top_items,
)


def partition(
    order_id,
    stall_order_id,
    stall_status="COMPLETED",
    parent_status="COMPLETED",
    subtotal=10.0,
    hour_utc=4,
):
    """Build a partition row. hour_utc 4 == 12:00 Singapore."""
    return {
        "order_id": order_id,
        "stall_order_id": stall_order_id,
        "stall_status": stall_status,
        "parent_status": parent_status,
        "subtotal": subtotal,
        "created_at": datetime(2026, 9, 26, hour_utc, 0, 0),
    }


# ---------------------------------------------------------------- money


# Review Focus 1: money must round half UP, not to even.
def test_money_rounds_half_up_not_to_even():
    assert money(12.345) == 12.35
    assert money(12.355) == 12.36
    assert money(2.675) == 2.68
    assert money(0.125) == 0.13


def test_money_handles_whole_numbers_and_zero():
    assert money(0) == 0.0
    assert money(10) == 10.0
    assert money(10.0) == 10.0


def test_money_does_not_inherit_binary_float_error():
    # 0.1 + 0.2 is 0.30000000000000004 in binary floating point.
    assert money(0.1 + 0.2) == 0.30


# ------------------------------------------------------------ cancelled


def test_cancelled_accepts_both_spellings_and_any_case():
    assert is_cancelled("CANCELLED")
    assert is_cancelled("CANCELED")
    assert is_cancelled("cancelled")
    assert is_cancelled("Canceled")
    assert not is_cancelled("COMPLETED")
    assert not is_cancelled("PENDING")
    assert not is_cancelled(None)
    assert not is_cancelled("")


# ------------------------------------------------------------- summarise


def test_counts_and_value_for_a_simple_completed_day():
    rows = [
        partition(1, 11, subtotal=12.50),
        partition(2, 12, subtotal=7.50),
    ]

    result = summarise(rows)

    assert result["totalOrders"] == 2
    assert result["completedOrders"] == 2
    assert result["cancelledOrders"] == 0
    assert result["completedOrderValue"] == 20.00
    assert result["averageCompletedOrderValue"] == 10.00


def test_pending_partitions_count_as_orders_but_not_as_value():
    rows = [
        partition(1, 11, stall_status="COMPLETED", subtotal=12.00),
        partition(2, 12, stall_status="PENDING", parent_status="PENDING", subtotal=99.00),
    ]

    result = summarise(rows)

    assert result["totalOrders"] == 2
    assert result["completedOrders"] == 1
    assert result["completedOrderValue"] == 12.00


def test_a_completed_partition_under_a_cancelled_parent_is_not_completed():
    rows = [partition(1, 11, stall_status="COMPLETED", parent_status="CANCELLED", subtotal=30.0)]

    result = summarise(rows)

    assert result["completedOrders"] == 0
    assert result["cancelledOrders"] == 1
    assert result["completedOrderValue"] == 0.0


def test_a_parent_with_two_partitions_for_this_stall_counts_the_order_once():
    rows = [
        partition(1, 11, subtotal=10.0),
        partition(1, 12, subtotal=5.0),
    ]

    result = summarise(rows)

    assert result["totalOrders"] == 1
    assert result["completedOrders"] == 1
    # The order counts once, but both partitions contribute their value.
    assert result["completedOrderValue"] == 15.00


def test_average_is_null_when_nothing_completed():
    rows = [partition(1, 11, stall_status="PENDING", parent_status="PENDING")]

    result = summarise(rows)

    assert result["completedOrders"] == 0
    assert result["averageCompletedOrderValue"] is None


def test_no_orders_gives_confident_zeros_not_nulls():
    result = summarise([])

    assert result["totalOrders"] == 0
    assert result["completedOrders"] == 0
    assert result["cancelledOrders"] == 0
    assert result["completedOrderValue"] == 0.0
    assert result["averageCompletedOrderValue"] is None


def test_the_alternate_cancelled_spelling_is_counted():
    rows = [partition(1, 11, stall_status="CANCELED", parent_status="CANCELED")]

    result = summarise(rows)

    assert result["cancelledOrders"] == 1
    assert result["completedOrders"] == 0


def test_average_of_three_rounds_half_up_rather_than_truncating():
    rows = [
        partition(1, 11, subtotal=10.00),
        partition(2, 12, subtotal=10.00),
        partition(3, 13, subtotal=10.01),
    ]

    result = summarise(rows)

    assert result["completedOrderValue"] == 30.01
    # 30.01 / 3 == 10.00333..., rounds to 10.00
    assert result["averageCompletedOrderValue"] == 10.00


# ------------------------------------------------------------- top_items


def test_top_items_ranks_by_quantity_and_caps_at_six():
    items = [
        {"dish_id": i, "dish_name": f"Dish {i}", "quantity": i, "price": 2.0}
        for i in range(1, 10)
    ]

    result = top_items(items)

    assert len(result) == 6
    assert [r["dishId"] for r in result] == [9, 8, 7, 6, 5, 4]


def test_top_items_merges_repeated_dishes():
    items = [
        {"dish_id": 1, "dish_name": "Chicken Rice", "quantity": 2, "price": 4.50},
        {"dish_id": 1, "dish_name": "Chicken Rice", "quantity": 3, "price": 4.50},
    ]

    result = top_items(items)

    assert len(result) == 1
    assert result[0]["quantity"] == 5
    assert result[0]["completedItemValue"] == 22.50


# Review Focus 4: ties must not reorder between refreshes.
def test_top_items_breaks_ties_deterministically():
    items = [
        {"dish_id": 3, "dish_name": "Cee", "quantity": 5, "price": 1.0},
        {"dish_id": 1, "dish_name": "Aye", "quantity": 5, "price": 1.0},
        {"dish_id": 2, "dish_name": "Bee", "quantity": 5, "price": 1.0},
    ]

    first = [r["dishId"] for r in top_items(items)]
    second = [r["dishId"] for r in top_items(list(reversed(items)))]

    assert first == second == [1, 2, 3]


def test_top_items_of_nothing_is_an_empty_list():
    assert top_items([]) == []


def test_top_items_carries_the_dish_name_and_value():
    items = [{"dish_id": 4, "dish_name": "Laksa", "quantity": 2, "price": 6.00}]

    result = top_items(items)

    assert result[0] == {
        "dishId": 4,
        "name": "Laksa",
        "quantity": 2,
        "completedItemValue": 12.00,
    }


# --------------------------------------------------------- hourly_orders


def test_hourly_orders_always_has_24_buckets():
    result = hourly_orders([])

    assert len(result) == 24
    assert [r["hour"] for r in result] == list(range(24))
    assert all(r["orderCount"] == 0 for r in result)
    assert all(r["completedOrderValue"] == 0.0 for r in result)


def test_hourly_orders_places_an_order_in_its_singapore_hour():
    # 04:00 UTC == 12:00 SGT
    result = hourly_orders([partition(1, 11, hour_utc=4, subtotal=8.0)])

    noon = next(r for r in result if r["hour"] == 12)
    assert noon["orderCount"] == 1
    assert noon["completedOrderValue"] == 8.00
    assert sum(r["orderCount"] for r in result) == 1


def test_hourly_orders_counts_a_multi_partition_order_once_per_hour():
    rows = [partition(1, 11, hour_utc=4), partition(1, 12, hour_utc=4)]

    result = hourly_orders(rows)

    noon = next(r for r in result if r["hour"] == 12)
    assert noon["orderCount"] == 1


def test_hourly_orders_counts_a_pending_order_but_not_its_value():
    rows = [
        partition(1, 11, hour_utc=4, stall_status="PENDING", parent_status="PENDING", subtotal=9.0)
    ]

    result = hourly_orders(rows)

    noon = next(r for r in result if r["hour"] == 12)
    assert noon["orderCount"] == 1
    assert noon["completedOrderValue"] == 0.0
