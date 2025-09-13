.PHONY: install lint test format up

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
