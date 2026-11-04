# S0 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A monorepo whose CI enforces every gate of E1–E11 on a trivial engine + web client + Postgres/RLS + Keycloak stack started by one `docker compose up`.

**Architecture:** `engine/` is a FastAPI app in src layout with three layers (`domain`, `persistence`, `api`) whose import rules are machine-enforced. Organization isolation lives in PostgreSQL RLS; the engine only sets `app.organization_id` per transaction. `web/` is a Vite/React/TS SPA signing in to Keycloak via OIDC. GitHub Actions runs static checks, tests, traceability, security scans and a compose smoke test on the exact images it built.

**Tech Stack:** Python (uv, FastAPI, SQLAlchemy 2, psycopg 3, Alembic, PyJWT), PostgreSQL + PostGIS, Keycloak, TypeScript (pnpm, Vite, React, oidc-client-ts, Vitest), Docker Compose, GitHub Actions.

**Spec:** [docs/superpowers/specs/2026-11-04-s0-foundation-design.md](../specs/2026-11-04-s0-foundation-design.md) (parent: [program spec](../specs/2026-11-04-nautical-deliverance-program-design.md)).

## Global Constraints

- All code, identifiers, UI text, docs in English (D-000).
- Python version per D-030, pinned in `.python-version`; managed by uv only.
- mypy `--strict`; TypeScript `strict: true`.
- Coverage ≥ 90 % line and ≥ 90 % branch for `engine/` and `web/` each (D-035). Exclusions only: `engine/src/nautical_deliverance/main.py`, `web/src/main.tsx`, generated code.
- Every requirement test is tagged: Python `@pytest.mark.req("S0-Rnn")`; TS test name contains `[S0-Rnn]`; CI-only checks carry a `# req: S0-Rnn` comment on the workflow job (D-036).
- All Docker image tags and GitHub Action refs pinned to exact versions (actions pinned by commit SHA). No `latest`.
- Images run as non-root, multi-stage (S0-R11).
- Security gates fail on severity high or critical (D-037). License allow-list: MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, PSF-2.0, MPL-2.0, LGPL (unmodified dynamic use).
- LF line endings (D-041). Conventional Commits; squash merge only (D-040).
- Repository license: proprietary, "All rights reserved" (D-038).
- Test credentials only in `infra/keycloak/realm-dev.json`; never real ones.
- The local folder path contains a space (`C:\Programing\nautical deliverence`): every script and documented command must quote paths.

## Review Focus

1. **Keycloak unreachable or still starting when the engine needs JWKS** → engine must not crash; `/api/v1/me` returns `503` with a JSON error, `/api/v1/health` stays `200`. Test in Task 5.
2. **Valid signature but missing `org_id` claim or malformed roles** → `403`, never `500`. Test in Task 5.
3. **Token's `org_id` not present in the `organization` table** → `403`. Test in Task 5.
4. **Token expired just beyond the leeway (leeway 10 s; token expired 60 s ago)** → `401`. Test in Task 5.
5. **Repo path containing a space on Windows** → compose start and all `README` commands work from `C:\Programing\nautical deliverence`. Manual verification step in Task 9.

## File Structure

```
.gitattributes .gitignore LICENSE README.md .pre-commit-config.yaml .jscpd.json
.github/dependabot.yml
.github/workflows/ci.yml          static checks, tests, traceability, security, smoke
.github/workflows/codeql.yml
.github/workflows/pr-title.yml
engine/pyproject.toml uv.lock .python-version Dockerfile alembic.ini
engine/src/nautical_deliverance/
  __init__.py
  main.py                         composition root: create_app()
  settings.py                     Settings (env-driven, pydantic-settings)
  domain/__init__.py
  domain/identity.py              Principal dataclass
  persistence/__init__.py
  persistence/db.py               engine/session factory, org_session()
  persistence/models.py           Organization, AppUser
  persistence/migrations/         Alembic env + versions/0001_identity_rls.py
  api/__init__.py
  api/health.py                   GET /api/v1/health
  api/auth.py                     token verification, get_principal dependency
  api/me.py                       GET /api/v1/me
engine/tests/                     unit/, db/ (needs Postgres), conftest.py
web/package.json pnpm-lock.yaml tsconfig.json vite.config.ts eslint.config.js .prettierrc
web/.dependency-cruiser.cjs knip.json Dockerfile nginx.conf
web/src/main.tsx App.tsx auth.ts api.ts  (+ *.test.ts[x])
infra/docker-compose.yml .env.example keycloak/realm-dev.json db/init/01-roles.sql
tools/trace.py tools/test_trace.py tools/check_licenses.py tools/check_branch_protection.sh
reference-suite/README.md
docs/traceability.md              generated
```

---

### Task 1: Verify prerequisites and initialize the repository

**Files:**
- Create: `.gitattributes`, `.gitignore`, `LICENSE`, `README.md` (title + one line; completed in Task 9), `reference-suite/README.md`, `docs/versions.md`

**Interfaces:**
- Produces: `docs/versions.md` — the single list of pinned versions (Python, Postgres/PostGIS image, Keycloak image, Node, pnpm) every later task copies from.

- [x] **Step 1: Check GitHub plan.** Done by controller: account is Free; owner chose D-043 (no branch protection until upgrade).
- [ ] **Step 2: Choose the Python version (D-030).** For the newest released CPython minor, check PyPI for wheels `cp3XX-manylinux*_x86_64` and `cp3XX-win_amd64` of: numpy, xarray (pure), eccodes / eccodeslib, cfgrib (pure), shapely, psycopg-binary, pydantic-core. Pick the newest minor where all exist. Record evidence (package → wheel filename) in `docs/versions.md`.
- [ ] **Step 3: Pin images and toolchain.** Record exact tags in `docs/versions.md`: `postgis/postgis:<pg>-<postgis>`, `quay.io/keycloak/keycloak:<x.y.z>`, `node:<lts>-alpine`, `nginxinc/nginx-unprivileged:<x.y.z>-alpine`, `python:<ver>-slim-<debian>`, pnpm version. Choose releases ≥ 14 days old.
- [ ] **Step 4: Write base files.** `.gitattributes`: `* text=auto eol=lf`. `.gitignore`: Python, Node, `infra/.env`, coverage outputs. `LICENSE`: `Copyright (c) 2026 Nautical Deliverance. All rights reserved.` plus a no-license-granted sentence.
- [ ] **Step 5: Init and commit.**
```bash
git init -b main
git add -A
git commit -m "chore: initialize repository"
```
Expected: one commit containing the files above plus existing `docs/superpowers/`.

---

### Task 2: Engine skeleton, health endpoint and engine gates

**Files:**
- Create: `engine/pyproject.toml`, `engine/.python-version`, `engine/src/nautical_deliverance/{__init__,main,settings}.py`, `domain/__init__.py`, `persistence/__init__.py`, `api/__init__.py`, `api/health.py`
- Test: `engine/tests/conftest.py`, `engine/tests/unit/test_health.py`, `engine/tests/unit/test_layers.py`

**Interfaces:**
- Produces: `create_app(settings: Settings | None = None) -> FastAPI` in `main.py`; `Settings` (pydantic-settings) fields `git_sha: str = "dev"`, `database_url: str`, `oidc_issuer: str`, `oidc_audience: str`, `oidc_jwks_url: str`; pytest marker `req(id: str)` registered in `pyproject.toml`.

- [ ] **Step 1: Create the uv project** with dependencies fastapi, uvicorn, pydantic-settings; dev: pytest, pytest-cov, hypothesis, httpx, mypy, ruff, import-linter, vulture. Configure in `pyproject.toml`: Ruff (`select = ["ALL"]` minus explicitly listed conflicts, line length 100), mypy strict, pytest `--strict-markers` with `req` marker, coverage `branch = true`, `fail_under = 90`, omit `main.py`.
- [ ] **Step 2: Write failing test** `test_health_returns_ok_and_version` (`@pytest.mark.req("S0-R02")`): `TestClient(create_app(Settings(git_sha="abc123", ...)))` → `GET /api/v1/health` → status 200, JSON `{"status": "ok", "version": "abc123"}`, no `Authorization` header sent.
- [ ] **Step 3: Run** `uv run pytest engine/tests/unit/test_health.py -v` → FAIL (import error).
- [ ] **Step 4: Implement** `api/health.py` router and `create_app`.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Layer contracts (S0-R05).** In `pyproject.toml` `[tool.importlinter]`: contract 1 forbidden — `nautical_deliverance.domain` ✗ `fastapi`, `sqlalchemy`, `nautical_deliverance.api`, `nautical_deliverance.persistence`; contract 2 forbidden — `nautical_deliverance.persistence` ✗ `nautical_deliverance.api`. Test `test_layer_contracts_reject_violation` (`req("S0-R05")`): copies the package to `tmp_path`, adds `import fastapi` to `domain/__init__.py`, runs `lint-imports` there via subprocess, asserts non-zero exit; and asserts zero exit on the unmodified tree.
- [ ] **Step 7: Run all engine gates:** `uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run lint-imports && uv run vulture src --min-confidence 80 && uv run pytest --cov` → all pass, coverage ≥ 90 %.
- [ ] **Step 8: Commit** `feat(engine): add skeleton with health endpoint and layer contracts`.

---

### Task 3: Traceability tool

**Files:**
- Create: `tools/trace.py`, `tools/conftest.py` (registers the `req` marker for `tools/` tests)
- Test: `tools/test_trace.py`

**Interfaces:**
- Produces: CLI `python tools/trace.py [--check]`. Reads requirement IDs from every `docs/superpowers/specs/*.md` table row matching `^\| (S\d\w*|C\d+)-R\d{2} \|`; collects references from `engine/tests/**/*.py` (`req("ID")`), `tools/test_*.py` (same), `web/src/**/*.test.ts(x)` (`[ID]` in test names), `.github/workflows/*.yml` (`# req: ID`). Writes `docs/traceability.md` (table: requirement → referencing locations). Exit 1 if: a requirement has no reference, a reference names an unknown ID, or with `--check` the committed file differs from the regenerated output.

- [ ] **Step 1: Write failing tests** (all `req("S0-R09")`), each building a fake repo in `tmp_path`:
  - `test_passes_when_every_requirement_has_a_test` → exit 0, matrix contains `S0-R01 | engine/tests/x.py`.
  - `test_fails_on_requirement_without_test` → exit 1, stderr contains `S0-R02: no test`.
  - `test_fails_on_unknown_reference` → exit 1, stderr contains `S0-R99: unknown requirement`.
  - `test_check_fails_when_committed_matrix_is_stale` → exit 1, stderr contains `docs/traceability.md is out of date`.
- [ ] **Step 2: Run** `uv run --project engine pytest tools/test_trace.py -v` → FAIL.
- [ ] **Step 3: Implement** with stdlib only (`re`, `pathlib`, `argparse`); repo root passed as `--root` (default: parent of `tools/`). Output sorted by ID for deterministic diffs.
- [ ] **Step 4: Run** → PASS. Run against the real repo: expect failures listing every S0 requirement not yet covered — this is correct at this point and is not committed as `--check` in CI until Task 8.
- [ ] **Step 5: Commit** `feat(tools): add requirement traceability checker`.

---

### Task 4: Database schema and Row-Level Security

**Files:**
- Create: `engine/alembic.ini`, `persistence/db.py`, `persistence/models.py`, `persistence/migrations/env.py`, `persistence/migrations/versions/0001_identity_rls.py`, `infra/db/init/01-roles.sql`, `infra/docker-compose.yml` (db service only for now), `infra/.env.example`
- Test: `engine/tests/db/conftest.py`, `engine/tests/db/test_rls.py`

**Interfaces:**
- Produces:
  - Tables: `organization(id uuid pk, name text not null)`, `app_user(id uuid pk = Keycloak sub, organization_id uuid fk not null, last_seen_at timestamptz not null)`. Both RLS-enabled with `FORCE ROW LEVEL SECURITY`; policy `organization_id = current_setting('app.organization_id', true)::uuid` (for `organization` the column is `id`). Missing setting → `NULL` → zero rows.
  - DB roles (in `01-roles.sql`): `nd_owner` (owns schema, runs migrations), `nd_app` (`LOGIN`, `NOBYPASSRLS`, `SELECT, INSERT, UPDATE, DELETE` only).
  - `org_session(organization_id: UUID) -> ContextManager[Session]` in `db.py`: opens a transaction and runs `SELECT set_config('app.organization_id', :id, true)` (transaction-local) before yielding.
  - Python dependencies added: sqlalchemy, psycopg[binary], alembic.

- [ ] **Step 1: Write failing tests** (all `req("S0-R04")`), running as `nd_app` against compose Postgres (`DATABASE_URL` env; tests skip with a clear message only when the env var is absent, and CI sets it so they never skip there). Fixture creates a test-only table `_rls_probe(id serial, organization_id uuid, note text)` with the same policy, as `nd_owner`, inserts one row for org A and one for org B:
  - `test_select_sees_only_own_org` → under `org_session(A)`: exactly A's row.
  - `test_update_and_delete_cannot_touch_other_org` → under `org_session(A)`: `UPDATE ... WHERE organization_id = B` and `DELETE` of B's row report `rowcount == 0`; B's row unchanged when read under `org_session(B)`.
  - `test_no_org_set_sees_nothing` → plain session: zero rows from `_rls_probe`, `organization`, `app_user`.
  - `test_app_role_cannot_bypass_rls` → `pg_roles.rolbypassrls` is false for `nd_app`; `nd_app` owns no tables (`pg_tables.tableowner`).
- [ ] **Step 2: Run** `docker compose -f infra/docker-compose.yml up -d --wait db` then `uv run pytest engine/tests/db -v` → FAIL.
- [ ] **Step 3: Implement** roles SQL, migration `0001`, models, `org_session`.
- [ ] **Step 4: Run** → PASS. Run all engine gates from Task 2 Step 7 → pass.
- [ ] **Step 5: Commit** `feat(engine): add identity schema with row-level security`.

---

### Task 5: Authentication and `/api/v1/me`

**Files:**
- Create: `domain/identity.py`, `api/auth.py`, `api/me.py`
- Modify: `main.py` (include router)
- Test: `engine/tests/unit/test_auth.py`, `engine/tests/db/test_me.py`

**Interfaces:**
- Consumes: `Settings`, `org_session` (Task 4), `create_app` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class Principal: user_id: UUID; organization_id: UUID; roles: frozenset[Role]` and `class Role(StrEnum): ADMIN = "admin"; ROUTE_ANALYST = "route_analyst"; VIEWER = "viewer"` in `domain/identity.py`.
  - Token contract (configured in Task 7's realm): RS256, claims `iss` = `oidc_issuer`, `aud` contains `oidc_audience`, `sub` (UUID), `org_id` (UUID string), `roles` (list of `Role` values; unknown values ignored).
  - `get_principal(...) -> Principal` FastAPI dependency in `api/auth.py`. JWKS via `jwt.PyJWKClient(oidc_jwks_url, cache_keys=True)`; leeway 10 s.
  - `GET /api/v1/me` → `{"user_id", "organization": {"id", "name"}, "roles": [sorted]}`; upserts `app_user.last_seen_at` under `org_session`.
  - Errors are JSON `{"detail": "<message>"}`.

- [ ] **Step 1: Write failing unit tests** in `test_auth.py`; a fixture generates an RSA key pair and patches the JWKS client to return its public key:
  - `req("S0-R03")`: `test_missing_token_401`, `test_expired_token_401` (exp = now − 60 s), `test_wrong_issuer_401`, `test_tampered_signature_401` (flip one char in signature), `test_wrong_audience_401`, `test_valid_token_yields_principal` (asserts exact `Principal`).
  - Review Focus: `test_missing_org_id_claim_403`, `test_non_uuid_org_id_403`, `test_roles_not_a_list_403`, `test_jwks_unreachable_503` (JWKS client raises `PyJWKClientConnectionError`; also asserts `/api/v1/health` still 200 in the same app).
- [ ] **Step 2: Write failing DB tests** in `test_me.py` (`req("S0-R03")`): `test_me_returns_principal_and_org_name`; `test_me_records_last_seen`; Review Focus `test_me_org_not_in_db_403`.
- [ ] **Step 3: Run** → FAIL.
- [ ] **Step 4: Implement** `domain/identity.py`, `api/auth.py` (add PyJWT[crypto] dependency), `api/me.py`. Mapping: `jwt.InvalidTokenError` → 401; claim shape errors → 403; `PyJWKClientConnectionError` → 503; org row missing under RLS → 403.
- [ ] **Step 5: Run** → PASS; all engine gates pass.
- [ ] **Step 6: Commit** `feat(engine): add OIDC authentication and /me endpoint`.

---

### Task 6: Web client skeleton and web gates

**Files:**
- Create: `web/package.json`, `pnpm-lock.yaml`, `tsconfig.json`, `vite.config.ts`, `eslint.config.js`, `.prettierrc`, `.dependency-cruiser.cjs`, `knip.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/auth.ts`, `src/api.ts`, `src/productName.ts`
- Test: `src/App.test.tsx`, `src/api.test.ts`, `src/architecture.test.ts`

**Interfaces:**
- Consumes: `GET /api/v1/me` response shape (Task 5).
- Produces:
  - `PRODUCT_NAME = "Nautical Deliverance"` in `src/productName.ts` — the only place the display name appears (D-026).
  - `fetchMe(accessToken: string): Promise<Me>` in `api.ts`, `type Me = { user_id: string; organization: { id: string; name: string }; roles: string[] }`; throws `ApiError { status: number }` on non-2xx.
  - `auth.ts`: `UserManager` from oidc-client-ts configured from `import.meta.env.VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID`; authorization code + PKCE.
  - Vite env: `VITE_API_BASE_URL`.

- [ ] **Step 1: Scaffold** with pnpm (pinned version from `docs/versions.md`); dependencies react, react-dom, oidc-client-ts; dev: typescript, vite, vitest, @vitest/coverage-v8, @testing-library/react, jsdom, eslint, typescript-eslint, eslint-plugin-jsx-a11y, prettier, dependency-cruiser, knip. Vitest coverage thresholds 90 lines / 90 branches; exclude `src/main.tsx`.
- [ ] **Step 2: Write failing tests:**
  - `api.test.ts`: `[S0-R03] fetchMe sends bearer token and parses response`; `[S0-R03] fetchMe throws ApiError with status on 401`.
  - `App.test.tsx`: `[S0-R03] shows sign-in button when signed out`; `[S0-R03] shows user organization name and roles when signed in`; `[S0-R03] shows error message when /me fails` (no blank screen).
  - `architecture.test.ts`: `[S0-R05] dependency-cruiser rejects import outside web/` — writes a temp file importing `../../engine/x`, runs depcruise, expects non-zero exit; expects zero on the clean tree.
- [ ] **Step 3: Run** `pnpm --dir web test` → FAIL.
- [ ] **Step 4: Implement** `api.ts`, `auth.ts`, `App.tsx`, `main.tsx`. UI is plain semantic HTML (heading with `PRODUCT_NAME`, button, definition list); no styling beyond a CSS reset.
- [ ] **Step 5: Run all web gates:** `pnpm --dir web exec tsc --noEmit && pnpm --dir web lint && pnpm --dir web exec prettier --check . && pnpm --dir web exec depcruise src && pnpm --dir web exec knip && pnpm --dir web test --coverage` → all pass.
- [ ] **Step 6: Commit** `feat(web): add client skeleton with OIDC sign-in`.

---

### Task 7: Containers, Keycloak realm and compose smoke test

**Files:**
- Create: `engine/Dockerfile`, `web/Dockerfile`, `web/nginx.conf`, `infra/keycloak/realm-dev.json`, `tools/smoke.sh`
- Modify: `infra/docker-compose.yml` (all four services), `infra/.env.example`

**Interfaces:**
- Consumes: env vars of `Settings` (Task 2), `VITE_*` (Task 6), DB roles (Task 4), token contract (Task 5).
- Produces:
  - Images `nautical-deliverance/engine:<tag>` and `nautical-deliverance/web:<tag>`; compose reads `ND_IMAGE_TAG` (default `dev`) so CI runs the exact SHA-tagged images.
  - Engine container entrypoint runs `alembic upgrade head` as `nd_owner`, then a dev-only seed inserting organizations `Acme Shipping` and `Borealis Tankers` with the UUIDs used in the realm (seed gated by `ND_SEED_DEV_DATA=true`, default false), then `uvicorn` serving as `nd_app`.
  - Realm `nautical-deliverance`: public client `nd-web` (PKCE, redirect to web origin), audience `nd-api`; protocol mappers emitting `org_id` (user attribute) and `roles` (realm roles `admin`, `route_analyst`, `viewer`) as top-level claims; six users `<role>@acme.test` / `<role>@borealis.test`, passwords = username (test-only, stated in a `description` field).
  - Healthchecks on all four services; ports: web 8080, engine 8000, keycloak 8081, db not published.
  - `tools/smoke.sh`: `docker compose up --wait` with a 180 s timeout, then checks `/api/v1/health` = 200, obtains a token for `route_analyst@acme.test` via the password grant on a dev-only test client `nd-smoke`, checks `/api/v1/me` returns organization `Acme Shipping`, checks `/api/v1/me` with Borealis user returns `Borealis Tankers`, checks both images run as non-root (`docker inspect` `.Config.User` non-empty and not `0`/`root`) and contain no compiler (`docker run --rm --entrypoint sh <img> -c 'command -v gcc'` fails). Exit non-zero on any failure.

- [ ] **Step 1: Write** Dockerfiles (multi-stage; engine: uv build stage → slim runtime with venv only; web: node build stage → nginx-unprivileged).
- [ ] **Step 2: Write** realm, compose, `.env.example`, `smoke.sh`.
- [ ] **Step 3: Run** `docker compose -f infra/docker-compose.yml build` then `bash tools/smoke.sh` → expect all checks pass and total `up --wait` time printed ≤ 180 s.
- [ ] **Step 4: Manual check in browser:** open `http://localhost:8080`, sign in as `viewer@borealis.test`, page shows `Borealis Tankers` and role `viewer`.
- [ ] **Step 5: Commit** `feat(infra): add containers, dev realm and smoke test`.

---

### Task 8: CI workflows, security gates and local hooks

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/codeql.yml`, `.github/workflows/pr-title.yml`, `.github/dependabot.yml`, `.pre-commit-config.yaml`, `.jscpd.json`, `tools/check_licenses.py`
- Test: `tools/test_check_licenses.py`

**Interfaces:**
- Consumes: every gate command from Tasks 2, 3, 6; `tools/smoke.sh` (Task 7).
- Produces: required status check names (used by Task 9): `engine`, `web`, `traceability`, `security`, `smoke`, `pr-title`, `CodeQL`.

- [ ] **Step 1: Write failing tests** for `tools/check_licenses.py` (`req("S0-R10")`): input is the JSON of `pip-licenses --format=json` and `pnpm licenses list --json`; `test_allows_listed_licenses`, `test_rejects_gpl` (exit 1, names the package), `test_rejects_unknown_license_string`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (stdlib only; allow-list from Global Constraints; `--approved <file>` for owner-approved exceptions, empty in S0). **Step 4: Run** → PASS.
- [ ] **Step 5: Write `ci.yml`** jobs, each with its `# req:` comment, all installs frozen (`uv sync --frozen`, `pnpm install --frozen-lockfile`):
  - `engine` (`# req: S0-R06 S0-R07 S0-R15`): Postgres service; Task 2 Step 7 gate list with `DATABASE_URL` set.
  - `web` (`# req: S0-R06 S0-R07 S0-R15`): Task 6 Step 5 gate list.
  - `traceability` (`# req: S0-R09`): `python tools/trace.py --check`.
  - `duplication` folded into `engine` job (`# req: S0-R08`): `npx jscpd@<pinned> --min-tokens 50 engine/src web/src` with threshold 0.
  - `security` (`# req: S0-R10`): gitleaks (full history), `uv run pip-audit`, `pnpm audit --audit-level high`, license check.
  - `smoke` (`# req: S0-R01 S0-R11`), needs `engine`, `web`: build both images tagged `${{ github.sha }}`, Trivy scan both (`--severity HIGH,CRITICAL --exit-code 1`), `ND_IMAGE_TAG=${{ github.sha }} bash tools/smoke.sh`.
  - Workflow-level: `# req: S0-R14` with `timeout-minutes: 15` on every job, and a final `ci-duration` job that fails if `now − workflow start > 15 min` (reads `run_started_at` via `gh api`).
- [ ] **Step 6: Write `pr-title.yml`** (`# req: S0-R13`): `amannn/action-semantic-pull-request` pinned by SHA.
- [ ] **Step 7: Write `codeql.yml`** (python, javascript-typescript) and `dependabot.yml` (ecosystems `uv`, `npm`, `docker`, `github-actions`; weekly) — `# req: S0-R10`.
- [ ] **Step 8: Write `.pre-commit-config.yaml`** (D-039): ruff, ruff-format, prettier, eslint (local hook via pnpm), gitleaks. Run `pre-commit run --all-files` → pass.
- [ ] **Step 9: Run** `python tools/trace.py` → exit 0 except `S0-R12` and `S0-R16` (covered in Task 9). Commit `ci: add quality, security and smoke pipelines`.

---

### Task 9: GitHub repository, branch protection and README

**Files:**
- Create: `tools/check_branch_protection.sh`, `.github/workflows/protection.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: status check names (Task 8), repo name `n00rp/nautical-deliverance` (D-028).

- [ ] **Step 1: Write `README.md`** (S0-R16): prerequisites with versions from `docs/versions.md` (Docker Desktop + WSL2, uv, Node, pnpm); start: `docker compose -f infra/docker-compose.yml up --wait`; run checks locally (the gate lists of Tasks 2, 6, 3); dev-realm users table; "Not for navigation" note (D-018).
- [ ] **Step 2: Write `tools/check_branch_protection.sh`** (`# req: S0-R12` at top; referenced by `protection.yml`, a `workflow_dispatch` + weekly workflow): reads `gh api repos/n00rp/nautical-deliverance` and asserts `allow_squash_merge == true`, `allow_merge_commit == false`, `allow_rebase_merge == false` (D-043: no branch-protection assertions on GitHub Free). Exit non-zero listing each mismatch.
- [ ] **Step 2b: Add a `readme` job to `ci.yml`** (`# req: S0-R16`): fails unless `README.md` contains the headings `## Prerequisites`, `## Start the system`, `## Run all checks`, `## Development test users`, and `docker compose -f infra/docker-compose.yml config` succeeds. The "works on a clean Windows machine" half of S0-R16 is Step 6.
- [ ] **Step 3: Create the repo and push** (ask the owner before running — creates an external resource):
```bash
gh repo create n00rp/nautical-deliverance --private --source . --push
```
- [ ] **Step 4: Apply merge settings** via `gh api -X PATCH repos/n00rp/nautical-deliverance -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false`. Run `bash tools/check_branch_protection.sh` → exit 0.
- [ ] **Step 5: Prove the gate:** open a PR with title `bad title` → `pr-title` check fails (merge is not blocked on Free, D-043); rename to `docs: add readme` → all checks green. Record CI wall time from the run (must be ≤ 15 min, S0-R14).
- [ ] **Step 6: Review Focus 5 — manual:** on the owner's Windows machine, from `C:\Programing\nautical deliverence`, follow `README.md` exactly from a fresh clone; `docker compose up --wait` succeeds and sign-in works.
- [ ] **Step 7: Final verification:** `python tools/trace.py --check` → exit 0 (every S0-R01…R16 covered); merge the PR.

---

## Spec coverage

| Req | Task |
|---|---|
| S0-R01 | 7, 8 (smoke) |
| S0-R02 | 2 |
| S0-R03 | 5, 6 |
| S0-R04 | 4 |
| S0-R05 | 2, 6 |
| S0-R06, R07, R15 | 2, 6, 8 |
| S0-R08 | 2, 6, 8 |
| S0-R09 | 3, 8 |
| S0-R10 | 8 |
| S0-R11 | 7, 8 |
| S0-R12 | 9 |
| S0-R13 | 8 |
| S0-R14 | 8, 9 |
| S0-R16 | 9 |
