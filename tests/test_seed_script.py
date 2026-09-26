"""Tests for the sample data script.

The script is loaded by path rather than imported as a package, because
scripts/ is not on the import path and should not be.
"""

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_sample_orders.py"

spec = importlib.util.spec_from_file_location("seed_sample_orders", SCRIPT_PATH)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def test_payload_totals_match_the_dish_lines():
    dishes = [
        {"dish_id": 1, "dish_name": "Chicken Rice", "quantity": 2, "price": 4.50},
        {"dish_id": 2, "dish_name": "Iced Kopi", "quantity": 1, "price": 1.80},
    ]

    payload = seed.build_order_payload(stall_id=1, dishes=dishes)

    assert payload["total_price"] == 10.80
    assert payload["orders"][0]["stall_id"] == 1
    assert len(payload["orders"][0]["dishes"]) == 2


def test_payload_rounds_money_half_up():
    dishes = [{"dish_id": 1, "dish_name": "Odd", "quantity": 3, "price": 4.115}]

    payload = seed.build_order_payload(stall_id=1, dishes=dishes)

    # 3 * 4.115 == 12.345, which must round up to 12.35 not down to 12.34.
    assert payload["total_price"] == 12.35


def test_payload_matches_the_order_service_contract():
    """OrderDetails requires orders[].stall_id, orders[].dishes[], total_price."""
    dishes = [{"dish_id": 9, "dish_name": "Laksa", "quantity": 1, "price": 6.00}]

    payload = seed.build_order_payload(stall_id=3, dishes=dishes)

    assert set(payload) == {"orders", "total_price"}
    assert set(payload["orders"][0]) == {"stall_id", "dishes"}
    dish = payload["orders"][0]["dishes"][0]
    assert set(dish) == {"dish_id", "dish_name", "quantity", "price"}


def test_random_dishes_are_always_valid_lines():
    for _ in range(25):
        dishes = seed._random_dishes()

        assert 1 <= len(dishes) <= 3
        assert len({d["dish_id"] for d in dishes}) == len(dishes), "no repeated dish in one order"
        for d in dishes:
            assert d["quantity"] >= 1
            assert d["price"] > 0


def test_the_script_never_deletes_or_resets_data():
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    assert "truncate" not in source
    assert "drop table" not in source
    assert "delete from" not in source
    assert ".delete(" not in source


def test_the_script_carries_no_hardcoded_credential():
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    assert "password" not in source
    assert "localdev" not in source
