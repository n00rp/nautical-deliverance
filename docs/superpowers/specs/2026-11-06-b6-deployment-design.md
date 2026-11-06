# B6 Deployment — Specification

- **Status:** Draft for owner review
- **Date:** 2026-11-06
- **Parent:** [Bunker procurement program spec](2026-11-05-bunker-procurement-program-design.md), build step B6 (D-076); D-066 (demo data only), D-068 (free cloud environment, owner-controlled, HTTPS, our Keycloak), D-022 (portable), E9; pilot 1 readiness P1–P5 (§6).
- **Goal:** Pilot 1 runs in an owner-controlled free cloud environment over HTTPS, is redeployed automatically on every green merge, is backed up nightly with a tested restore, has its pilot users created safely, and is covered by an end-to-end test and a short user guide — completing P1–P5.

## 1. Decisions

Confirmed by the owner in the B6 interview:

| ID | Decision |
|---|---|
| B6-D1 | Pilot 1 runs on **Oracle Cloud Always Free, Ampere A1 (arm64)**, within the current free limits (2 OCPU / 12 GB RAM). The owner creates the Oracle account; no paid service is used. |
| B6-D2 | The pilot is reached on a **free DuckDNS subdomain** with a **Let's Encrypt** certificate; it can later be replaced by an owner domain without code changes. |
| B6-D3 | **Deploys run from GitHub Actions** on every merge to `main` whose CI is green: over SSH the server checks out the exact commit, builds the images natively (arm64) and restarts the stack; then smoke and E2E tests run against the server. |
| B6-D4 | **Nightly backups**: `pg_dump` (custom format) plus a Keycloak realm export, encrypted, uploaded to Oracle **Object Storage** (Always Free) through its S3-compatible API, kept **14 days**; restore is scripted and tested (P4). |
| B6-D5 | **Pilot users are created by the owner with a script** (`tools/pilot_user.py`) that sets name, e-mail, role and organization, generates a one-time temporary password shown once, and forces a password change at first login. |
| B6-D6 | The pilot uses one new demo organization, **"Pilot Demo Shipping"**, seeded with demo master data, inquiries, RFQs, offers and nominations (D-066). The dev organizations Acme and Borealis exist only in local/CI stacks. |

Proposed — confirmed by the owner's approval of this spec:

| ID | Decision | Rationale |
|---|---|---|
| B6-D7 | A production overlay `infra/docker-compose.prod.yml` adds **Caddy** as the only public service (ports 80/443; automatic HTTPS; HSTS, CSP and security headers); Keycloak runs in **production mode** (`start`, `KC_HOSTNAME` = the pilot URL, proxy headers `xforwarded`); the Keycloak admin console and Postgres are **not reachable from the internet** (admin console via SSH tunnel only). | Minimal attack surface (E9); Caddy is the simplest correct TLS. |
| B6-D8 | Our own **PostGIS image** (`infra/postgis/Dockerfile`) built from the official multi-arch `postgres:17` image plus the distribution's PostGIS 3 package, digest-pinned, used in all environments (dev, CI, pilot). | The pinned `postgis/postgis` image is amd64-only; one image everywhere avoids drift. |
| B6-D9 | A **pilot realm** (`infra/keycloak/realm-pilot.json`) with the same roles, client and org mapper as dev but **no users**; the web client's redirect URIs and web origins are the pilot URL only. Secrets (DB passwords, Keycloak admin password, DuckDNS token, Object Storage keys) live only in a server-side `.env` (mode 600) and GitHub secrets; never in git (gitleaks stays green). | No test credentials in production; D-022 portability. |
| B6-D10 | Seeding is selected by `ND_SEED` = `dev` (Acme + Borealis, as today) or `pilot` (Pilot Demo Shipping only); unset means no seed. The pilot seed is idempotent and runs at each deploy. | One seed code path, two data sets. |
| B6-D11 | Backups are encrypted with **age** to a public key committed in the repo; the private key stays with the owner. A CI job tests backup → restore end to end against **MinIO** as an S3 stand-in, so P4 is verified without the cloud. | Encryption at rest independent of the provider; restore proven continuously. |
| B6-D12 | The E2E test (Playwright) runs the full pilot 1 flow as a dedicated **e2e buyer** in the pilot organization — create inquiry → select suppliers → create and mark RFQs sent → enter offers → select winner (with rationale) → create and mark nomination sent — and checks the dashboard and the Operator view. It runs against the local compose stack in CI and against the pilot after each deploy; inquiries it creates are cancelled at the end and marked `E2E` in the voyage field. | P1 automated part; repeatable without polluting the demo data visibly. |
| B6-D13 | An owner **runbook** (`docs/deploy/oracle-runbook.md`) lists every manual step with exact values: account, VM shape, cloud-init (installs Docker, creates a deploy user, key-only SSH), security list (22, 80, 443), DuckDNS, bucket + customer secret key + lifecycle rule, GitHub secrets, first deploy, creating pilot users, restoring a backup. | The owner performs account and secret steps (D-068); nothing is guessed. |
| B6-D14 | A short English **user guide** (`docs/user-guide.md`) for pilot users: sign in, roles, the purchase flow step by step, the confidentiality rules (individual RFQs, Operator sees no prices), and demo-data notice. | P5. |

## 2. Threat model (E9, summary)

| Threat | Mitigation |
|---|---|
| Internet exposure of DB or Keycloak admin | Only Caddy listens publicly (B6-D7); security list allows 22/80/443; admin console via SSH tunnel. |
| Leaked test credentials | Pilot realm has no users (B6-D9); users created with one-time passwords and forced change (B6-D5). |
| Secrets in git or logs | `.env` and GitHub secrets only; gitleaks in CI; scripts never echo secrets except the one-time password to the owner's terminal. |
| Backup disclosure | age encryption before upload; bucket private; 14-day retention (B6-D4, D11). |
| Supply chain | Digest-pinned base images; Trivy scan unchanged; deploy builds only the merged, CI-green commit. |
| Free-tier termination | Stay under limits with margin (2 OCPU / ≤ 12 GB); backups off-instance; runbook rebuild from scratch. |

## 3. Requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| B6-R01 | Production overlay (B6-D7) | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml config` is valid; only Caddy publishes ports; Keycloak runs `start` (not `start-dev`) with the configured hostname; Caddy config sets HSTS, CSP, `X-Content-Type-Options`, `Referrer-Policy`; a CI test asserts these from the rendered config. |
| B6-R02 | Multi-arch PostGIS (B6-D8) | `infra/postgis/Dockerfile` builds for `linux/amd64` and `linux/arm64` (CI builds both, arm64 via buildx); PostGIS extension creatable; all engine DB tests pass on it (amd64 in CI); dev and CI use it. |
| B6-R03 | Pilot realm and secrets (B6-D9) | The pilot realm has the four roles, the web client and org mapper, zero users, redirect URIs only for the pilot URL; a test fails if any user or a wildcard redirect is added; no secret value appears in git (gitleaks green). |
| B6-R04 | Seed modes (B6-D10) | `ND_SEED=pilot` seeds exactly the Pilot Demo Shipping organization with demo data per B1–B5 seeds (idempotent, `.example` e-mails, denylist test); `ND_SEED=dev` unchanged; unset seeds nothing. |
| B6-R05 | Pilot user script (B6-D5) | `tools/pilot_user.py` creates a user with name, e-mail, exactly one bunker role and the pilot org id, a generated temporary password (≥ 16 chars, printed once) and the `UPDATE_PASSWORD` required action; refuses unknown roles and existing e-mails; tested against a Keycloak container in CI. |
| B6-R06 | Backup and restore (B6-D4, D11, P4) | The backup job produces an age-encrypted `pg_dump` and realm export and uploads them with a date-stamped key; the restore script downloads, decrypts and restores into an empty stack; a CI job runs backup → restore against MinIO and then passes the smoke test on the restored stack; retention is configured to 14 days (lifecycle rule documented and, for MinIO, tested). |
| B6-R07 | Deploy workflow (B6-D3) | A workflow triggered by successful CI on `main` connects with the deploy key, checks out that commit on the server, builds, runs `compose up -d`, waits for health, then runs smoke and E2E against the pilot URL; it never deploys a commit whose CI failed; secrets come from GitHub secrets only; actionlint passes. |
| B6-R08 | End-to-end test (B6-D12, P1) | The Playwright E2E test completes the full flow and the Operator check; it passes against the local compose stack in CI; it cleans up (cancels its inquiries); it is parameterized by base URL and credentials from the environment. |
| B6-R09 | Runbook (B6-D13) | `docs/deploy/oracle-runbook.md` covers every manual step in B6-D13 with exact commands and values, including first deploy, pilot users, and a restore drill; a docs check verifies that every GitHub secret and `.env` variable used by the workflow and compose files is documented in it. |
| B6-R10 | User guide (B6-D14, P5) | `docs/user-guide.md` covers the items in B6-D14, uses the UI's exact labels, and is linked from the README. |
| B6-R11 | Gates inherited | All S0–B5 gates green; coverage ≥ 90 %; `tools/trace.py --check` green. |

## 4. Pilot 1 readiness after B6

P1 automated part (B6-R08 against the pilot) + the brief author's own walkthrough · P2 confidentiality tests green (B3–B5) · P3 all gates green · P4 restore drill documented (B6-R06, runbook) · P5 user guide (B6-R10). The owner's manual steps (runbook) and the brief author's walkthrough are outside automation and are reported, not asserted.

## 5. Out of scope

Paid services; the company's own SSO or environment (later, D-022); monitoring/alerting beyond health checks; multiple environments (staging); automatic certificate for an owner domain (works by changing one variable).

## 6. Risks

| Risk | Mitigation |
|---|---|
| Oracle changes or reclaims free resources | Margin under limits; off-instance encrypted backups; full rebuild documented in the runbook. |
| ARM-only issues | Same images built for arm64 in CI (B6-R02) before they reach the server. |
| E2E test flakiness against a real network | Retries limited to navigation waits; failures leave a trace artifact; deploy is marked failed, not rolled back silently. |
