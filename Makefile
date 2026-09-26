.PHONY: install lint test run seed

install:
	.venv/Scripts/pip install -r requirements-dev.txt

lint:
	.venv/Scripts/ruff check .

test:
	.venv/Scripts/python -m pytest -q

run:
	.venv/Scripts/python src/main.py

seed:
	.venv/Scripts/python scripts/seed_sample_orders.py --stall 1 --orders 5
