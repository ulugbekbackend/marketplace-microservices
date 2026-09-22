SHELL := /bin/sh
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
PY_SERVICES := auth catalog order cart search payment notification

.DEFAULT_GOAL := help
.PHONY: help up up-full down logs ps build migrate seed reindex \
        test test-libs lint fmt typecheck gen-rabbit keys clean

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk -F':.*?## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

keys: ## Create the RS256 key pair auth signs tokens with (kept out of git)
	@mkdir -p infra/secrets
	@test -f infra/secrets/jwt_private.pem || openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out infra/secrets/jwt_private.pem
	@openssl rsa -in infra/secrets/jwt_private.pem -pubout -out infra/secrets/jwt_public.pem 2>/dev/null
	@echo "keys ready in infra/secrets/"

up: keys ## Start the stack (infrastructure + services)
	$(COMPOSE) up -d --build

up-full: keys ## Start everything including search and monitoring profiles
	$(COMPOSE) --profile full --profile search --profile monitoring up -d --build

down: ## Stop the stack and remove containers
	$(COMPOSE) down

logs: ## Tail logs of one service: make logs s=catalog
	$(COMPOSE) logs -f --tail=200 $(s)

ps: ## Show container status
	$(COMPOSE) ps

build: ## Rebuild images
	$(COMPOSE) build

migrate: ## Apply database migrations in running containers
	@for s in auth catalog order; do $(COMPOSE) exec -T $$s python manage.py migrate --noinput; done
	$(COMPOSE) exec -T payment alembic upgrade head

seed: ## Load demo data
	$(COMPOSE) exec -T catalog python -m tools.seed

reindex: ## Rebuild the search index from the catalog
	$(COMPOSE) exec -T search python -m app.reindex

# Tests run on the host against the dev stack (make up exposes these ports locally).
test test-libs $(addprefix test-,$(PY_SERVICES)): export POSTGRES_HOST = localhost
test test-libs $(addprefix test-,$(PY_SERVICES)): export REDIS_URL = redis://localhost:6379/0
test test-libs $(addprefix test-,$(PY_SERVICES)): export REDIS_HOST = localhost
test test-libs $(addprefix test-,$(PY_SERVICES)): export RABBITMQ_HOST = localhost

test: ## Run every Python test suite (shared libs + each service)
	uv run pytest libs
	@for s in $(PY_SERVICES); do echo "== $$s"; (cd services/$$s && uv run --project . pytest) || exit 1; done

test-libs: ## Run the shared library tests only
	uv run pytest libs

$(addprefix test-,$(PY_SERVICES)): test-%: ## Run one service suite: make test-catalog
	cd services/$* && uv run --project . pytest

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Format the code
	uv run ruff format .
	uv run ruff check . --fix

typecheck: ## Type check with mypy
	uv run mypy libs
	@for s in $(PY_SERVICES); do echo "== $$s"; (cd services/$$s && uv run --project . mypy .) || exit 1; done

gen-rabbit: ## Regenerate the broker topology from the contracts
	uv run python -m contracts.topology > infra/rabbitmq/definitions.json

clean: ## Remove containers, volumes and local caches
	$(COMPOSE) down -v
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
