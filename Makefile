SHELL := /bin/sh

.PHONY: install run test check format compose-up compose-down

install:
	uv sync --dev

run:
	uv run poe run

test:
	uv run poe test

check:
	uv run poe check

format:
	uv run poe format

compose-up:
	docker compose up --build

compose-down:
	docker compose down
