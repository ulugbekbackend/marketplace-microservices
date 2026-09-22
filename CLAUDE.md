# Marketplace monorepo

Multi-vendor marketplace, microservices in a monorepo (portfolio project).
The full specification, the task list and the progress journal are kept locally, outside
version control.

**Current phase:** P0 — foundation: shared contracts, infrastructure, service skeletons.

## Commands
Toolchain is project-local (no global installs): `source .tools/env.sh` (bash) or `. .\.tools\env.ps1` first.
```
make up / down / logs s=<svc> / ps
make up-full           # + search, monitoring profiles
make migrate / seed / reindex
make test / test-<svc> / test-e2e / load-test
make lint / fmt / typecheck
make gen-api
```

## Layout
```
libs/contracts   event schemas (Pydantic), enums, money
libs/py-common   outbox, consumer base, idempotency, logging, health, auth headers
services/        auth, catalog, order (Django) | cart, search, payment, notification (FastAPI)
frontend/        pnpm workspace: packages/{ui,api-client}, apps/{shop,seller}
tools/           payme-simulator, click-simulator, seed
tests/           e2e (Playwright), integration (compose), load (k6)
infra/           docker-compose*, postgres, traefik, rabbitmq, monitoring
```

## Conventions
- Code, comments, commits, API names: English. Local working notes: Uzbek (Latin).
- Money = integer tiyin. IDs = UUID. Time = UTC `timestamptz`.
- Services never touch another service's DB. Events via `marketplace.events` topic exchange + outbox.
- Error format: `{"error": {"code", "message", "details"}}`. Pagination: `{items, total, page, page_size}`.
- Python deps: `uv`, env via `decouple.config()`; Django settings in single `config/settings.py`.
- Commits: Conventional Commits, no AI attribution; work on `feature/*` branches, never push to main.

## Repo scope
Only the app and what production needs is committed, together with the agent definitions
and skills under `.claude/`. Dev configs, virtual environments and `.tools/` are ignored.

Planning notes, test reports and screenshots are kept locally and never committed; apart
from `.gitignore`, no committed file refers to them by name.
