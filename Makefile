# =============================================================================
# SOT Analyzer
# =============================================================================
# On Windows, run these through Git Bash / WSL, or use the raw commands shown
# in README.md. `python` is assumed to be on PATH.
# =============================================================================

SHELL := /bin/bash
COMPOSE := docker compose

# Local (non-Docker) backend interpreter.
VENV := .venv
ifeq ($(OS),Windows_NT)
	PY := $(VENV)/Scripts/python.exe
else
	PY := $(VENV)/bin/python
endif

.DEFAULT_GOAL := help
.PHONY: help init env venv install up down restart logs ps build \
        migrate revision reset-db test test-backend lint format typecheck \
        frontend-install frontend-dev frontend-typecheck frontend-lint \
        frontend-build netlify-build check

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Setup -----------------------------------------------------------------

env: ## Create .env from .env.example if it does not exist
	@test -f .env || (cp .env.example .env && echo "Created .env - edit the secrets before running")

venv: ## Create the local Python virtualenv
	python -m venv $(VENV)

install: venv ## Install backend dependencies (incl. dev extras) locally
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "backend[dev]"

frontend-install: ## Install frontend dependencies locally
	cd frontend && npm install

init: env install frontend-install ## One-shot local setup

# --- Docker ----------------------------------------------------------------

build: ## Build all images
	$(COMPOSE) build

up: env ## Start the full stack (db + backend + frontend)
	$(COMPOSE) up -d
	@echo "API      -> http://localhost:8000/api/health"
	@echo "API docs -> http://localhost:8000/docs"
	@echo "Web      -> http://localhost:3000"

down: ## Stop the stack (keeps the database volume)
	$(COMPOSE) down

restart: down up ## Restart the stack

logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

# --- Database --------------------------------------------------------------

migrate: ## Apply all Alembic migrations (inside the backend container)
	$(COMPOSE) exec backend alembic upgrade head

revision: ## Autogenerate a migration:  make revision m="add x"
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(m)"

reset-db: ## DESTRUCTIVE: drop the database volume and re-migrate
	$(COMPOSE) down -v
	$(COMPOSE) up -d db
	@sleep 5
	$(COMPOSE) up -d backend
	@sleep 5
	$(COMPOSE) exec backend alembic upgrade head

# --- Quality ---------------------------------------------------------------

test: test-backend ## Run all tests

test-backend: ## Run the backend test suite locally
	$(PY) -m pytest backend/tests -v

lint: ## Lint the backend
	$(PY) -m ruff check backend

format: ## Auto-format the backend
	$(PY) -m ruff format backend
	$(PY) -m ruff check --fix backend

typecheck: ## Type-check the backend
	$(PY) -m mypy backend/app

frontend-typecheck: ## Type-check the frontend
	cd frontend && npm run typecheck

frontend-lint: ## Lint the frontend
	cd frontend && npm run lint

frontend-build: ## Build the frontend for a normal production target
	cd frontend && npm run build

netlify-build: ## Simulate Netlify (requires NEXT_PUBLIC_API_BASE_URL=https://.../api)
	cd frontend && NETLIFY=true npm run build:netlify

check: lint typecheck test frontend-typecheck frontend-lint frontend-build ## Run every quality gate
