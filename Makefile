service ?= web

.PHONY: install lint test format up down logs migrate seed-rss

install:
	pip install -r requirements.txt

lint:
	ruff check .

format:
	black .

test:
	pytest

up:
        docker compose up --build

down:
        docker compose down

logs:
        docker compose logs -f $(service)

migrate:
        docker compose run --rm web alembic upgrade head

seed-rss:
        docker compose run --rm web python scripts/seed_sources.py
