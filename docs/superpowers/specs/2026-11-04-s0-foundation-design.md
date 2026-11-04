# S0 Foundation — Specification

- **Status:** Approved by owner 2026-11-04 (including proposed decisions D-030–D-041)
- **Date:** 2026-11-04
- **Parent:** [Program specification](2026-11-04-nautical-deliverance-program-design.md), build step 1
- **Goal:** A repository, CI and runtime skeleton in which every quality gate required by E1–E11 is enforced automatically on trivial code, so every later sub-project inherits the gates instead of adding them.

## 1. Decisions

Confirmed in the interview:

| ID | Decision |
|---|---|
| D-027 | Private GitHub repository with GitHub Actions as CI. `main` is protected: no direct pushes, every change via pull request requiring green CI. Dependabot and CodeQL enabled. |
| D-028 | Repository `n00rp/nautical-deliverance`; local working copy `C:\Programing\nautical deliverence`. |
| D-029 | Monorepo with top-level `engine/`, `web/`, `infra/`, `reference-suite/`, `docs/`. |
| D-043 | The account is on GitHub Free, where branch protection and rulesets do not apply to private repositories. Until the account is upgraded: CI runs every gate but cannot block a merge; "never merge with red CI" is a binding working rule for owner and Claude. Branch protection (original S0-R12) is restored on upgrade. Amends D-027 and D-013. |
| D-044 | License allow-list (D-037) extended with MIT-0, CC0-1.0, BlueOak-1.0.0 and Python-2.0. GPL/AGPL remain blocked. |
| D-045 | GitHub code scanning is unavailable for private repositories on GitHub Free, so the CodeQL workflow stays in the repository but runs only on manual dispatch until the account is upgraded; then it runs on every PR (amends S0-R10). |
| D-046 | Trivy in CI blocks HIGH/CRITICAL findings that have a fix available (`--ignore-unfixed`). A scheduled weekly workflow reports all findings, including unfixed ones, so they stay visible. Amends D-037 for container images. |

**Proposed — confirmed by the owner's approval of this spec:**

| ID | Decision | Rationale |
|---|---|---|
| D-030 | **Python version:** the newest minor version for which every base-stack dependency (D-014) publishes wheels for Linux x86-64 and Windows x86-64, verified in the first plan step and pinned in `.python-version`. Python is managed by uv; the system Python (3.12.8) is not used. | D-014 says "latest stable"; a version the stack cannot install is not usable. |
| D-031 | **Engine tooling:** uv (dependencies, lockfile `uv.lock`), Ruff (lint + format), mypy `--strict`, pytest, pytest-cov (line + branch), Hypothesis, import-linter (layer rules), vulture (dead code). | One tool per job, all de facto standard. |
| D-032 | **Web tooling:** pnpm (lockfile), Vite, React, TypeScript `strict`, ESLint (typescript-eslint, jsx-a11y), Prettier, Vitest, dependency-cruiser (layer rules), Knip (dead code). jscpd checks duplication across `engine/` and `web/`. Storybook and Playwright are added in the sub-projects that first need them (design system, C4). | Avoids configuring tools before there is anything for them to check. |
| D-033 | **Database:** PostgreSQL with PostGIS. Schema migrations with Alembic; data access with SQLAlchemy 2. | PostGIS is the standard for geodata needed by C3/C5. |
| D-034 | **Organization isolation (D-021) is enforced by PostgreSQL Row-Level Security.** Every org-scoped table has an RLS policy on `organization_id`; the engine sets the current organization per transaction from the authenticated token; the application database role cannot bypass RLS. | A forgotten `WHERE` clause in application code can then never leak data; the database refuses it. |
| D-035 | **Coverage threshold (E7):** ≥ 90 % line and ≥ 90 % branch coverage for `engine/` and `web/` each. Excluded only: generated code and the composition root (`main`/entry point), listed explicitly in config. | Strict but achievable for logic-heavy code. |
| D-036 | **Traceability (E2):** every requirement in every spec has an ID `<SPEC>-R<nn>` (e.g. `S0-R07`). Python tests reference it with `@pytest.mark.req("S0-R07")`; TypeScript tests with `[S0-R07]` in the test name; CI checks (non-test) by name in workflow config. A script `tools/trace.py` fails CI if any requirement has no test, or any test references an unknown ID, and writes the matrix to `docs/traceability.md`. | Machine-checked, not hand-maintained. |
| D-037 | **Supply chain and secrets (E9, P7):** gitleaks (secret scan), pip-audit and `pnpm audit` (dependency vulnerabilities), Trivy (container images). CI fails on any finding of severity high or critical. A license allow-list (MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0, LGPL for unmodified dynamic use) is checked in CI; any other license fails until explicitly approved. | Commercial product: GPL/AGPL dependencies must not slip in. |
| D-038 | **Repository license:** proprietary, "All rights reserved". | Commercial product (D-002). |
| D-039 | **Local hooks:** the pre-commit framework runs the fast gates (Ruff, Prettier, ESLint, gitleaks) before each commit. CI remains the authority. | Fast feedback; CI cannot be bypassed. |
| D-040 | **Commit messages:** Conventional Commits (`feat:`, `fix:`, `docs:` …), checked in CI on PR titles (squash merge). Merge method: squash only; linear history. | Readable history, changelog later for free. |
| D-041 | **Line endings:** LF for all text files, enforced by `.gitattributes`. | Windows host, Linux containers. |

## 2. Repository layout

```
.github/workflows/      CI definitions
.github/dependabot.yml
engine/                 Python package nautical_deliverance (src layout), tests/
web/                    React + TypeScript client
infra/                  docker-compose.yml, keycloak/realm-dev.json, .env.example
reference-suite/        README only in S0 (populated from C1 onward)
tools/                  trace.py (+ its test)
docs/                   specs/, plans/, traceability.md (generated)
LICENSE, README.md, .gitattributes, .pre-commit-config.yaml
```

## 3. Runtime (Docker Compose)

| Service | Image | S0 content |
|---|---|---|
| `engine` | Built from `engine/Dockerfile` (multi-stage, non-root user) | FastAPI app: `GET /api/v1/health` (public), `GET /api/v1/me` (authenticated: returns user id, organization id, roles). |
| `web` | Built from `web/Dockerfile` (multi-stage; static build served by nginx, non-root) | One page: product name, sign-in via Keycloak, shows the result of `/api/v1/me`. Unstyled beyond a minimal reset; no design-system work in S0. |
| `db` | `postgis/postgis`, pinned tag | Schema: `organization`, `app_user`; RLS mechanism (D-034). |
| `keycloak` | `quay.io/keycloak/keycloak`, pinned tag | Dev realm imported from `infra/keycloak/realm-dev.json`: two organizations, one user per role (D-020: Admin, Route Analyst, Viewer) in each. Test credentials only; documented in the realm file, never real ones. |

All image tags are pinned to exact versions (no `latest`). Configuration via environment variables; `infra/.env.example` is committed, `infra/.env` is git-ignored.

## 4. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| S0-R01 | One-command start | From a clean clone with only Docker installed, `docker compose -f infra/docker-compose.yml up --wait` brings all four services to healthy in ≤ 180 s on a GitHub-hosted `ubuntu-latest` runner. |
| S0-R02 | Health endpoint | `GET /api/v1/health` returns `200` with `{"status":"ok","version":"<git sha>"}` and needs no authentication. |
| S0-R03 | Authentication | `GET /api/v1/me` returns `401` without a token, with an expired token, with a token from a different issuer and with a tampered signature; returns `200` with user id, organization id and roles for a valid Keycloak token. |
| S0-R04 | Organization isolation | With RLS active, a session for organization A gets zero rows from org-scoped tables belonging to organization B on `SELECT`, and `UPDATE`/`DELETE` affect zero rows of B. Verified on a test-only org-scoped table created by the test suite. A session without an organization set gets zero rows. The application DB role is verified to have neither `BYPASSRLS` nor table ownership. |
| S0-R05 | Engine is UI-agnostic (D-009/D-010) | import-linter contracts: the domain layer (`nautical_deliverance.domain`) imports neither `fastapi`, `sqlalchemy` nor `nautical_deliverance.api`/`.persistence`; `.persistence` does not import `.api`. dependency-cruiser: no file in `web/` imports a path outside `web/`. Each contract is proven to fail CI by a deliberately violating fixture in the checker's test. |
| S0-R06 | Static checks | CI fails on any Ruff, mypy `--strict`, `tsc --noEmit`, ESLint or Prettier finding. |
| S0-R07 | Tests and coverage | CI runs all engine and web tests and fails if coverage is below D-035 thresholds. |
| S0-R08 | Dead code and duplication | CI fails on any vulture (confidence ≥ 80) or Knip finding, and on duplicated blocks ≥ 50 tokens reported by jscpd across `engine/` and `web/`. |
| S0-R09 | Traceability | `tools/trace.py` fails CI per D-036 and regenerates `docs/traceability.md`; CI fails if the committed file differs from the regenerated one. |
| S0-R10 | Security gates | CI fails per D-037 (gitleaks, pip-audit, pnpm audit, Trivy on both built images, license allow-list). CodeQL runs for Python and TypeScript. Dependabot is configured for pip/uv, npm, Docker and GitHub Actions. |
| S0-R11 | Images | Both built images run as a non-root user and contain no build toolchain (multi-stage). CI produces images tagged with the git SHA; the compose smoke test runs those exact images. |
| S0-R12 | Merge settings (D-043) | Repository allows squash merge only (merge commits and rebase merge disabled), which yields linear history on `main`. Verified by `gh api` reading the repository settings in a documented check. Branch protection (PR required, required checks, no force push/deletion) is added when the account is upgraded. |
| S0-R13 | PR title convention | CI fails on a PR title that does not follow Conventional Commits. |
| S0-R14 | CI duration | Full CI on a PR completes in ≤ 15 min wall time. |
| S0-R15 | Reproducibility | Lockfiles (`uv.lock`, `pnpm-lock.yaml`) are committed; CI installs with frozen lockfiles and fails if they are out of date. |
| S0-R16 | Developer docs | `README.md` documents prerequisites (Docker Desktop with WSL2, uv, Node + pnpm), how to start the system, run all checks locally, and the dev-realm test users. Following it on a clean Windows 11 machine reaches S0-R01. |

## 5. Out of scope for S0

- Any domain logic (C1–C9).
- Design system, Storybook, visual regression, Playwright (design-system and C4 sub-projects).
- Production hosting, TLS, backups (planned for P6; specified when the first deployment target is decided).
- The final role list and permissions beyond reading `/me` (D-020 says it is fixed in its own spec).

## 6. Risks

| Risk | Mitigation |
|---|---|
| Newest Python lacks wheels for ecCodes/cfgrib | D-030 chooses the version by verification, not by date. |
| GitHub branch protection on a private repo requires a paid plan | Confirmed: account is Free. Owner chose D-043 (no enforced protection until upgrade). |
| RLS mistakes give false confidence | S0-R04 tests the negative cases, including "no organization set" and role privileges. |
