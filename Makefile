.PHONY: install test lint up down logs validate-workflows

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

lint:
	python -m ruff check .

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f flowguard-api sap-mock

validate-workflows:
	python scripts/validate_workflows.py

