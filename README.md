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

After a `git pull`, rebuild the images with `docker compose -f infra/docker-compose.yml up --wait --build`.

No `infra/.env` is needed. Then open:

- Web: http://localhost:8080
- Engine: http://localhost:8000
- Keycloak: http://localhost:8081

The compose file is a dev/CI stack: dev passwords and a dev realm, not a production deployment. Known gaps are listed in [docs/known-limitations.md](docs/known-limitations.md).

Local UI development goes through the compose stack on http://localhost:8080: sign-in redirects are registered for that origin only, so `pnpm dev` on :5173 cannot sign in.

## Run all checks

CI (`.github/workflows/ci.yml`) is the authority; these are the same commands. Run them in Git Bash or WSL (they use `export` and `bash`).

Engine, from `engine/`:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run lint-imports
uv run vulture src --min-confidence 80
uv run pytest --cov
uv run coverage json -o coverage.json
uv run python ../tools/check_coverage.py coverage.json   # line AND branch >= 90 % (D-035)
uv run ruff check ../tools
uv run ruff format --check ../tools
uv run mypy --strict ../tools
```

The database tests need a running `db` service (`docker compose -f infra/docker-compose.yml up --detach --wait db`) and these variables. Use `127.0.0.1`, not `localhost`, on Windows:

```bash
export ND_REQUIRE_DB=1
export ND_DATABASE_URL=postgresql+psycopg://nd_app:dev-app-password@127.0.0.1:5432/nd
export ND_MIGRATION_DATABASE_URL=postgresql+psycopg://nd_owner:dev-owner-password@127.0.0.1:5432/nd
```

PowerShell equivalent: `$env:ND_REQUIRE_DB = "1"`, `$env:ND_DATABASE_URL = "..."`, `$env:ND_MIGRATION_DATABASE_URL = "..."` with the same values.

Web, from `web/` (after `pnpm install --frozen-lockfile`):

```bash
pnpm run typecheck
pnpm run lint
pnpm run format:check
pnpm run depcruise
pnpm run knip
pnpm run test --coverage
pnpm run duplication
pnpm run stylelint
pnpm run build-storybook
pnpm run test:visual:docker                       # visual regression + axe, light and dark
```

The visual baselines (`web/tests/visual/__screenshots__/`) are Linux-only and are produced only in the digest-pinned Playwright image used by CI (`web/scripts/visual-docker.sh`; needs Docker). After an intended visual change, regenerate and commit them with:

```bash
pnpm --dir web run test:visual:docker --update-snapshots
```

Pixel tolerance: at most 0.1 % of pixels may differ (`maxDiffPixelRatio` in `web/playwright.config.ts`). `pnpm run storybook` starts Storybook for development.

Repository, from the root:

```bash
uv run --locked --project engine pytest tools -v
uv run --locked --project engine python tools/trace.py --check
bash tools/smoke.sh        # needs the stack from "Start the system"
uvx pre-commit run --all-files
```

## Repository settings check

After any change to the GitHub repository settings, run `bash tools/check_branch_protection.sh`. It asserts squash-only merging (`allow_squash_merge` true, `allow_merge_commit` and `allow_rebase_merge` false) on `n00rp/nautical-deliverance`; set `ND_REPO` to check another slug. It needs `gh auth login` with an account that has admin rights on the repo, because GitHub only returns these fields to admins, so it cannot run in CI with `GITHUB_TOKEN`. GitHub Free has no branch protection, so none is asserted (D-043).

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
