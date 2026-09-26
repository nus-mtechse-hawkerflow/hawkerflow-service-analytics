"""Create sample orders through the order service HTTP API.

Run by hand only. This is never invoked at application startup, and it never
deletes, resets or modifies orders it did not create. Every run adds another
batch on top of whatever is already there.

Orders go through the order service's own API rather than straight into
PostgreSQL, so sample data takes exactly the path a real order takes.

Usage:
    python scripts/seed_sample_orders.py --stall 1 --orders 5
    python scripts/seed_sample_orders.py --stall 1 --orders 3 --leave-pending
    python scripts/seed_sample_orders.py --stall 1 --dry-run
"""

import argparse
import random
import sys
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import httpx

ORDER_API = "http://127.0.0.1:8082/hawkerflow"
SINGAPORE = ZoneInfo("Asia/Singapore")

SAMPLE_DISHES = [
    {"dish_id": 1, "dish_name": "Chicken Rice", "price": 4.50},
    {"dish_id": 2, "dish_name": "Iced Kopi", "price": 1.80},
    {"dish_id": 3, "dish_name": "Char Kway Teow", "price": 5.50},
    {"dish_id": 4, "dish_name": "Laksa", "price": 6.00},
    {"dish_id": 5, "dish_name": "Soya Bean", "price": 1.50},
]


def _money(value) -> float:
    """Match the analytics service: two places, half away from zero."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_order_payload(stall_id: int, dishes: list[dict]) -> dict:
    """Build an OrderDetails body for POST /v1/order/orders."""
    subtotal = sum(Decimal(str(d["price"])) * Decimal(d["quantity"]) for d in dishes)

    return {
        "total_price": _money(subtotal),
        "orders": [{"stall_id": stall_id, "dishes": dishes}],
    }


def _random_dishes() -> list[dict]:
    """One to three distinct dishes, each with a small quantity."""
    picked = random.sample(SAMPLE_DISHES, k=random.randint(1, 3))

    return [{**dish, "quantity": random.randint(1, 3)} for dish in picked]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--stall", type=int, required=True, help="Backend numeric stall id")
    parser.add_argument("--orders", type=int, default=5, help="How many orders to create")
    parser.add_argument("--api", default=ORDER_API, help="Order service base URL")
    parser.add_argument(
        "--leave-pending",
        action="store_true",
        help="Create the orders without completing them",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print payloads, send nothing")
    args = parser.parse_args()

    if args.stall <= 0:
        parser.error("--stall must be a positive integer")
    if args.orders <= 0:
        parser.error("--orders must be a positive integer")

    created: list[int] = []
    total = Decimal("0")

    try:
        with httpx.Client(base_url=args.api, timeout=10.0) as client:
            for _ in range(args.orders):
                payload = build_order_payload(args.stall, _random_dishes())

                if args.dry_run:
                    print(f"[dry-run] POST /v1/order/orders {payload}")
                    continue

                response = client.post("/v1/order/orders", json=payload)
                response.raise_for_status()
                order_id = response.json()["order_id"]
                created.append(order_id)
                total += Decimal(str(payload["total_price"]))

                if not args.leave_pending:
                    patch = client.patch(
                        f"/v1/order/stalls/{args.stall}/orders/{order_id}",
                        json={"status": "COMPLETED"},
                        headers={"X-Stall-ID": str(args.stall)},
                    )
                    patch.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"Order service request failed: {exc}", file=sys.stderr)
        print(f"Is the order service running at {args.api}?", file=sys.stderr)
        if created:
            print(f"Orders created before the failure: {created}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("Dry run complete. Nothing was sent.")
        return 0

    today = datetime.now(SINGAPORE).date().isoformat()
    print(f"Created order ids : {created}")
    print(f"Stall             : {args.stall}")
    print(f"Singapore date    : {today}")
    print(f"Status            : {'PENDING' if args.leave_pending else 'COMPLETED'}")
    print(f"Total value       : {_money(total):.2f}")
    print()
    print("Re-running adds another batch; it does not replace this one.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
