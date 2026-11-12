SHELL := /bin/bash
PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: help venv install install-slim browsers dev build test lint run db-reset docker docker-slim docker-up deploy

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

venv:
	python3 -m venv .venv

install: venv browsers
	$(PIP) install -q -e '.[dev,browser]'
	cd web && npm install

install-slim: venv
	$(PIP) install -q -e '.[dev]'
	cd web && npm install

dev:
	@echo "Use: make dev-api  and  make dev-web"

dev-api:
	.venv/bin/uvicorn app.main:app --reload --port 8000

dev-web:
	cd web && npm run dev

build:
	cd web && npm run build

test:
	$(PY) -m pytest -q

run: build
	.venv/bin/uvicorn app.main:app --port 8000

db-reset:
	rm -rf data/app.db

browsers:
	$(PIP) install -q -e '.[browser]'
	PLAYWRIGHT_BROWSERS_PATH=$(CURDIR)/.playwright-browsers .venv/bin/playwright install chromium

docker:
	docker build -t pricetrack:local .

docker-slim:
	docker build --target runtime-slim -t pricetrack:slim .

docker-up: 
	docker compose up --build

deploy:
	@echo "Deployment is driven by GitHub Actions; provision infra with infra/main.bicep"
