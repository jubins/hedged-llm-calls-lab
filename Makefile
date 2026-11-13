.PHONY: install test lint up down load-plain load-timeout load-hedged simulate

install:
	pip install -r requirements-dev.txt

test:
	python -m pytest -q

lint:
	ruff check .

simulate:
	PYTHONPATH=. python scripts/simulate.py

up:
	docker compose up -d --build --wait

load-plain:
	MODE=plain docker compose --profile load run --rm k6

load-timeout:
	MODE=timeout docker compose --profile load run --rm k6

load-hedged:
	MODE=hedged docker compose --profile load run --rm k6

down:
	docker compose --profile load down -v
