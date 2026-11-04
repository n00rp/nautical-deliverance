# Nautical Deliverance

Weather-routing product: Python engine, React web client, Docker Compose.

> **Not for navigation.** This is a planning tool. Final route verification is the responsibility of the vessel's ECDIS and master (D-018).

## Prerequisites

Versions are pinned in [docs/versions.md](docs/versions.md).

- Docker Desktop with the WSL2 backend
- [uv](https://docs.astral.sh/uv/) 0.13.4 or newer (installs Python 3.14 itself)
- Node 24 (22 works for local development)
- pnpm 12.15.0
- [pre-commit](https://pre-commit.com/) (`uvx pre-commit install`)

## Start the system

```bash
docker compose -f infra/docker-compose.yml up --wait
```

No `infra/.env` is needed. Then open:

- Web: http://localhost:8080
- Engine: http://localhost:8000
- Keycloak: http://localhost:8081

The compose file is a dev/CI stack: dev passwords and a dev realm, not a production deployment.

## Run all checks

CI (`.github/workflows/ci.yml`) is the authority; these are the same commands.

Engine, from `engine/`:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run lint-imports
uv run vulture src --min-confidence 80
uv run pytest --cov
```

The database tests need a running `db` service (`docker compose -f infra/docker-compose.yml up --detach --wait db`) and these variables. Use `127.0.0.1`, not `localhost`, on Windows:

```bash
export ND_REQUIRE_DB=1
export ND_DATABASE_URL=postgresql+psycopg://nd_app:dev-app-password@127.0.0.1:5432/nd
export ND_MIGRATION_DATABASE_URL=postgresql+psycopg://nd_owner:dev-owner-password@127.0.0.1:5432/nd
```

Web, from `web/` (after `pnpm install --frozen-lockfile`):

```bash
pnpm run typecheck
pnpm run lint
pnpm run format:check
pnpm run depcruise
pnpm run knip
pnpm run test --coverage
pnpm run duplication
```

Repository, from the root:

```bash
uv run --frozen --project engine pytest tools -v
uv run --frozen --project engine python tools/trace.py --check
bash tools/smoke.sh        # needs the stack from "Start the system"
uvx pre-commit run --all-files
```

## Development test users

Realm `nautical-deliverance` in `infra/keycloak/realm-dev.json`. Test-only credentials: the password is the username.

| Username / password | Organisation | Role |
|---|---|---|
| `admin@acme.test` | Acme | admin |
| `route_analyst@acme.test` | Acme | route_analyst |
| `viewer@acme.test` | Acme | viewer |
| `admin@borealis.test` | Borealis | admin |
| `route_analyst@borealis.test` | Borealis | route_analyst |
| `viewer@borealis.test` | Borealis | viewer |
