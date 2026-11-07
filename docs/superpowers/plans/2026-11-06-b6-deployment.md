# B6 Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pilot 1 can be deployed to an owner-controlled Oracle Always Free ARM VM over HTTPS. Deployment is automatic from CI. The system has encrypted nightly backups with a restore that is proven in CI, safe pilot user creation, an end-to-end test of the full flow, a runbook and a user guide. Everything here can be verified locally and in CI. Only the runbook steps need the owner.

**Architecture:**
- The production stack is the existing compose file plus `infra/docker-compose.prod.yml`, which adds Caddy, Keycloak in production mode, the pilot realm, the backup service and server-side `.env` secrets.
- Images are built on the server (arm64 native). CI builds the PostGIS and app images for arm64 with buildx to catch architecture breakage early.
- The scripts are `tools/pilot_user.py`, `infra/backup/backup.sh` and `infra/backup/restore.sh`.
- The E2E test lives in `e2e/` and uses Playwright in the already pinned Playwright container.
- The deploy workflow is `.github/workflows/deploy.yml`.

**Tech Stack:** as B5, plus Caddy, age, rclone (S3), SeaweedFS and aws-cli (CI only).

**Spec:** [docs/superpowers/specs/2026-11-06-b6-deployment-design.md](../specs/2026-11-06-b6-deployment-design.md) covers all of B6-D1–D14 and B6-R01–R11.

## Global Constraints

- **Repo path:** exactly `C:\Programing\nautical deliverence` ("deliverence" with an e; the path contains a space). Never use the sibling folder `nautical deliverance`. The repo is **private**.
- **Gates:** all S0–B5 gates stay green. New workflow and compose changes must pass actionlint and `docker compose config`.
- **Pinning:** every new base image (Caddy, postgres, SeaweedFS, age/rclone helpers) is pinned by digest, and every tool version is pinned exactly (version at least two weeks old).
- **Licence check:** the licence allow-list check applies to every new dependency.
- **Secrets:** no secret value ever appears in git. Secrets come from `infra/.env.prod` (gitignored, documented in `infra/.env.prod.example` with placeholders) or from GitHub secrets. gitleaks must stay green.
- **Requirement tags:** use `req("B6-Rnn")` / `[B6-Rnn]`, or a `# req: B6-Rnn` comment where a CI job is the test, as for S0-R12. At the end, `python tools/trace.py --check` exits 0 and `docs/traceability.md` is regenerated.
- **Pilot hostname:** comes from `ND_PUBLIC_HOST`, for example `nd-pilot.duckdns.org`, and is never hard-coded. Locally and in CI use `localhost` with Caddy's internal CA.
- **Branch and commits:** work on `feat/b6-deploy`, which already holds the spec. Use Conventional Commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.
- **No cloud calls:** nothing in this plan calls Oracle, DuckDNS or any external account. Those steps are runbook-only.

## Review Focus

1. **A deploy of a commit whose CI failed, or whose CI ran on a PR rather than `main`.** It must never deploy. Task 7.
2. **The server rebooting.** The stack comes back by itself (`restart: unless-stopped`), and the backup timer survives too. Tasks 3 and 5.
3. **A backup run while the DB is busy.** `pg_dump` gives a consistent snapshot. A failed upload exits non-zero and leaves no partial object counted as a valid backup. Task 5.
4. **`pilot_user.py` run twice with the same e-mail.** The second run refuses and changes nothing. A typo in the role name is refused. Task 4.
5. **The E2E test aborting halfway.** Its inquiries are still cancelled by a cleanup step, or are recognisable as `E2E` and harmless. Task 6.

---

### Task 1: Multi-arch PostGIS image (B6-R02)

**Files:**
- Create `infra/postgis/Dockerfile`, starting `FROM postgres:17-<debian>@sha256:<multi-arch index digest>` and adding `apt-get install postgresql-17-postgis-3` with a pinned package version.
- Modify `infra/docker-compose.yml` so the db service builds or uses `nautical-deliverance/postgis:${ND_IMAGE_TAG:-dev}`.
- Modify `.github/workflows/ci.yml`. Every job that starts Postgres uses the new image. Add a job that does `docker buildx build --platform linux/amd64,linux/arm64` for postgis, engine and web, using QEMU and without pushing.
- Update the `infra/db/init` scripts if needed.

- [ ] **Step 1: Write the failing test** `tools/test_postgis_image.py`, tagged `req("B6-R02")`.
  - The Dockerfile's FROM is digest-pinned.
  - The compose db service references the new image.
  - Keep the existing engine `test_postgis.py` as the behavioural test.
- [ ] **Step 2: Implement.** Build locally. Run the full engine DB suite on the new image, check that `CREATE EXTENSION postgis` works, and run cold smoke.
- [ ] **Step 3:** Run the gates and actionlint. Confirm Trivy has no fixable HIGH/CRITICAL findings on the new image, and add targeted upgrades as was done for zlib.
- [ ] **Step 4: Commit** as `build(infra): add multi-arch PostGIS image`.

### Task 2: Seed modes and the pilot organization (B6-R04)

**Files:** Modify `persistence/seed.py`, `engine/docker-entrypoint.sh`, the compose files, the seed tests and `tools/smoke.sh`.

**Interfaces:**
- `ND_SEED` takes the values `dev`, `pilot` or unset. Keep `ND_SEED_DEV_DATA=true` as a deprecated alias for `dev` for one release, with a warning, or replace every use of it. Pick one and record the choice.
- `seed.seed(mode)` reuses the existing per-org seed functions for the organization **Pilot Demo Shipping**, which gets a fixed UUID.
- The pilot seed seeds no users, because the pilot realm has none. Inquiries need operator, requester and buyer user ids, which normally come from realm users. Seed a small set of **demo directory users** (invented names, `.example` e-mails, ids not in Keycloak) to own the demo inquiries. Real pilot users appear through the `/me` upsert when they log in. Record this as a ruling if you choose differently.

- [ ] **Step 1: Write the failing tests**, tagged `req("B6-R04")`.
  - `pilot` seeds exactly one organization, Pilot Demo Shipping, with the same demo coverage as the B1–B5 seeds: master data, inquiries, RFQs, offers, a nomination with an amendment, and every attention kind.
  - The seed is idempotent.
  - The denylist and `.example` checks pass.
  - `dev` is unchanged.
  - With no mode set, nothing is seeded.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** Run the full engine suite and cold smoke, which still uses `dev`.
- [ ] **Step 4: Commit** as `feat(engine): add pilot seed mode`.

### Task 3: Production overlay, Caddy and the pilot realm (B6-R01, B6-R03)

**Files:**
- Create `infra/docker-compose.prod.yml`, `infra/caddy/Caddyfile`, `infra/keycloak/realm-pilot.json`, `infra/.env.prod.example` and `tools/test_prod_config.py`.
- Modify `.gitignore` to add `infra/.env.prod`.

**Rules:**
- **Caddy:**
  - `{$ND_PUBLIC_HOST}` reverse-proxies `/` to web, `/api/` to the engine, and `/realms/` and `/resources/` to Keycloak.
  - Block `/admin/` on the public host with a 404.
  - Set the headers HSTS (`max-age=31536000`), CSP (self, plus the Keycloak origin on the same host), `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin-when-cross-origin` and `X-Frame-Options DENY`.
  - Only Caddy publishes `80:80` and `443:443`. Every other service drops its `ports`.
  - Every service gets `restart: unless-stopped`.
- **Keycloak:**
  - Command `start --import-realm` with `KC_HOSTNAME=https://${ND_PUBLIC_HOST}`, `KC_PROXY_HEADERS=xforwarded` and `KC_HTTP_ENABLED=true` (internal only).
  - The admin user and password come from `.env.prod`.
  - Mount the pilot realm, not the dev realm.
- **Web:** the build args point OIDC at `https://${ND_PUBLIC_HOST}/realms/...`.
- **Engine:** gets `ND_SEED=pilot`.
- **Pilot realm:** derive it from `realm-dev.json`. It keeps the roles, the `nd-web` client and the `org_id` mapper. It has **no users**. Its redirect URIs and web origins are only `https://${ND_PUBLIC_HOST}/*`, using realm import placeholder substitution (`${env.ND_PUBLIC_HOST}`, if supported) or a render step. Brute-force protection is on, and the password policy is at least `length(12)`.

- [ ] **Step 1: Write the failing tests** in `tools/test_prod_config.py`.
  - `req("B6-R01")`:
    - `docker compose -f … -f … config --format json`, with a dummy env, is valid;
    - only `caddy` has published ports;
    - Keycloak's command contains `start` and not `start-dev`;
    - every service has a restart policy;
    - the Caddyfile has every required header and the `/admin` block.
  - `req("B6-R03")`:
    - the pilot realm has the four roles, zero users and no wildcard redirect;
    - `.env.prod` is gitignored;
    - the example file holds placeholders only.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Smoke it locally.** Bring up the prod overlay with `ND_PUBLIC_HOST=localhost`, using Caddy's internal TLS (`tls internal` when the host is localhost). Check that `/api/v1/health` returns 200 through Caddy over HTTPS, `/admin/` returns 404, and the security headers are present. Add this as a CI job.
- [ ] **Step 4:** Run actionlint and the gates. **Step 5: Commit** as `feat(infra): add production overlay with Caddy`.

### Task 4: Pilot user script (B6-R05)

**Files:** Create `tools/pilot_user.py` and `tools/test_pilot_user.py`. Add a CI job that runs the test against a Keycloak container with the pilot realm.

**Interface:**
- Command: `python tools/pilot_user.py --url https://host --realm nautical-deliverance --admin-user … --email … --first … --last … --role bunker_buyer [--org <uuid>]`.
- The org defaults to Pilot Demo Shipping.
- The admin password is read from `ND_KC_ADMIN_PASSWORD`, or from a prompt via `getpass`. It is never taken as an argument.
- The script uses only the Keycloak admin REST API, through the standard library or httpx if it is already a dependency.
- It generates a password with `secrets.token_urlsafe(18)`, at least 16 characters, sets it as temporary, adds the `UPDATE_PASSWORD` required action and sets the `org_id` attribute.
- It prints the temporary password exactly once.

- [ ] **Step 1: Write the failing tests**, tagged `req("B6-R05")`, against a real Keycloak container.
  - The user is created with the role, org, temporary password and required action.
  - Signing in with the temporary password demands a password change.
  - An existing e-mail is refused with exit code 2 and no change (Review Focus #4).
  - An unknown role is refused.
  - The password never appears in any log line except the single output line.
- [ ] **Step 2: Implement.** **Step 3:** Run the tests and gates.
- [ ] **Step 4: Commit** as `feat(tools): add pilot user script`.

### Task 5: Backup and restore (B6-R06)

**Files:**
- Create `infra/backup/Dockerfile`, a small image with `pg_dump`/`pg_restore` matching PostgreSQL 17, `age` and `rclone`, all pinned.
- Create `infra/backup/backup.sh`, `infra/backup/restore.sh` and `infra/backup/age-recipients.txt`. The recipients file holds the owner's public key. Until the owner supplies one, use a clearly marked CI test key, together with a runbook step to replace it.
- Add a `backup` service to the prod overlay. It runs nightly from a container cron loop, for example `supercronic`, pinned, at 02:15 UTC.
- Add `tools/test_backup_restore.sh` and a CI job using SeaweedFS (S3 stand-in).

**Rules:**
- `backup.sh` does the following:
  1. Runs `pg_dump -Fc` of the app database, which is consistent by MVCC (Review Focus #3).
  2. Exports the Keycloak realm, users included, through `kc.sh export` or the admin API partial export. Pick one that includes users and record the choice.
  3. Tars both files.
  4. Encrypts the tarball with `age -R age-recipients.txt`.
  5. Uploads to `s3:${ND_BACKUP_BUCKET}/nd/YYYY/MM/DD/nd-<UTC timestamp>.tar.age`, using rclone's S3 backend with the Oracle S3-compatible endpoint from env.
  6. Writes a `.ok` marker object only after a successful upload.
  
  It exits non-zero on any failure.
- `restore.sh <key>` downloads the backup, decrypts it with the identity file given by `--identity` (the owner's private key), restores into an **empty** stack with `pg_restore --clean --if-exists`, and imports the realm.
- Retention: the runbook documents a 14-day lifecycle rule. In CI, a SeaweedFS lifecycle rule of 14 days is set and asserted with aws-cli (`s3api get-bucket-lifecycle-configuration`).

- [ ] **Step 1: Write the failing CI test** `tools/test_backup_restore.sh`, tagged `# req: B6-R06`. It must:
  1. start the stack and SeaweedFS;
  2. seed;
  3. create one inquiry through the API;
  4. run the backup;
  5. stop the stack and wipe its volumes;
  6. start an empty stack;
  7. run the restore with the CI test identity;
  8. assert that the inquiry exists, the demo data is present and smoke passes;
  9. assert that the `.ok` marker exists and the lifecycle rule exists;
  10. simulate a failed upload by stopping SeaweedFS before upload, and assert a non-zero exit and no `.ok` marker.
- [ ] **Step 2: Implement.** **Step 3:** Run the test locally and in CI, then run the gates.
- [ ] **Step 4: Commit** as `feat(infra): add encrypted backup and restore`.

### Task 6: End-to-end test (B6-R08)

**Files:**
- Create `e2e/` with `e2e/package.json` (or reuse the web Playwright setup if cleaner), `e2e/flow.spec.ts` and `e2e/playwright.config.ts`.
- Add a CI job that starts the compose stack (dev seed plus an e2e buyer and operator from the dev realm) and runs E2E in the pinned Playwright container.

**Test flow:**
1. Sign in as the buyer at `${ND_E2E_BASE_URL}` with `${ND_E2E_USER}` / `${ND_E2E_PASSWORD}`.
2. Create an inquiry with voyage `E2E-<timestamp>` and 2 lines.
3. Select suppliers using the pre-selection.
4. Create the RFQs and mark 2 of them sent. The mailto links are not followed.
5. Enter 2 offers.
6. Select the non-lowest offer with a rationale.
7. Create the nomination and mark it sent.
8. Assert that the inquiry status is Nominated and that the dashboard figures changed.
9. Sign in as the operator (`${ND_E2E_OPERATOR_*}`, optional) and assert that no `USD` text appears on the inquiry page or the dashboard, and that "Nominated: <supplier>" is shown.
10. Cleanup: in a `finally`-style afterAll, cancel every inquiry whose voyage starts with `E2E-` and is not already cancelled, through the API with the buyer token (Review Focus #5).

- [ ] **Step 1: Write the test.** Tag it with `[B6-R08]` in the test title. Run it against the local stack and confirm it passes. As a negative control, break one assertion and confirm it fails, then revert.
- [ ] **Step 2:** Add the CI job and capture a trace artifact on failure.
- [ ] **Step 3:** Run the gates and actionlint. **Step 4: Commit** as `test(e2e): add full purchase flow test`.

### Task 7: Deploy workflow, runbook, user guide and final verification (B6-R07, R09, R10, R11)

**Files:**
- Create `.github/workflows/deploy.yml`, `infra/deploy/deploy.sh` (it runs on the server), `infra/deploy/cloud-init.yaml`, `docs/deploy/oracle-runbook.md`, `docs/user-guide.md` and `tools/test_deploy_docs.py`.
- Modify the README to link the user guide and the runbook.
- Regenerate `docs/traceability.md`.

**Rules:**
- **Trigger.** `deploy.yml` runs `on: workflow_run: workflows: [CI], types: [completed], branches: [main]`, with the job condition `github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'push'` (Review Focus #1). It also allows `workflow_dispatch` with a `sha` input, for the owner to redeploy a known-good commit.
- **Concurrency group** `deploy-pilot`.
- **Deploy steps:**
  1. Load the SSH key from `secrets.ND_DEPLOY_SSH_KEY`, with `known_hosts` from `secrets.ND_DEPLOY_KNOWN_HOSTS`. Strict host checking stays on.
  2. Run `ssh deploy@${{ secrets.ND_DEPLOY_HOST }} 'infra/deploy/deploy.sh <sha>'`.
  3. Wait for `https://$HOST/api/v1/health`.
  4. Run smoke (with `ND_SMOKE_BASE_URL`) against the pilot.
  5. Run E2E against the pilot with the `ND_E2E_*` secrets.
- **`deploy.sh <sha>`** does `git fetch`, `git checkout --detach <sha>`, then `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/.env.prod build`, then `up -d --remove-orphans`, then waits for healthy. It never runs `down -v`.
- **`cloud-init.yaml`:**
  - installs Docker Engine and the compose plugin, pinned through the official apt repo;
  - creates the `deploy` user in the docker group;
  - disables password SSH;
  - clones the repo with a read-only **deploy key**, documented in the runbook;
  - opens nothing beyond 22, 80 and 443 in iptables (Oracle images ship iptables rules; document this).
- **Runbook**, which covers B6-D13 in full:
  - account creation, with the card verification noted;
  - the A1.Flex shape at 2 OCPU / 12 GB;
  - the region choice;
  - the security list;
  - DuckDNS, with the update cron in cloud-init;
  - the Object Storage bucket, customer secret key, S3 endpoint and lifecycle rule;
  - age keygen, telling the owner to keep the private key offline;
  - a table of every GitHub secret;
  - every `.env.prod` variable;
  - the first deploy;
  - creating the pilot users and the e2e users with `pilot_user.py`;
  - the restore drill (P4), with a log template to fill in;
  - tearing down and rebuilding.
- **User guide**, which covers B6-D14, uses the exact UI labels and is linked from the README.

- [ ] **Step 1: Write the failing tests.**
  - `tools/test_deploy_docs.py`, tagged `req("B6-R09")`. Every `secrets.X` referenced in `deploy.yml` and every `${VAR}` in `docker-compose.prod.yml` and `.env.prod.example` must appear in the runbook.
  - `req("B6-R07")`, a static test of `deploy.yml`:
    - the trigger is workflow_run on CI;
    - the success and push conditions are present;
    - there is a concurrency group;
    - strict host-key checking is on;
    - there is no `down -v`.
  - `req("B6-R10")`: the user guide exists, covers the required headings and is linked from the README.
- [ ] **Step 2: Implement.** Run `actionlint` and `shellcheck` on all new shell scripts, and add shellcheck to CI if it is not already there.
- [ ] **Step 3: Final verification:**
  - engine gates with the DB, coverage ≥ 90;
  - all web gates, including jscpd at 0;
  - visual tests, with the second run clean;
  - cold smoke;
  - the prod-overlay local HTTPS check;
  - backup and restore with SeaweedFS;
  - E2E against the local stack;
  - the licence check;
  - Trivy;
  - `python tools/trace.py`, then `--check` exits 0 with B6-R01–R11 covered.
- [ ] **Step 4: Commit** as `feat(deploy): add pilot deploy workflow, runbook and user guide`, including traceability.md.

## Spec coverage

| Requirement | Tasks |
|---|---|
| B6-R01 | 3 |
| B6-R02 | 1 |
| B6-R03 | 3 |
| B6-R04 | 2 |
| B6-R05 | 4 |
| B6-R06 | 5 |
| B6-R07 | 7 |
| B6-R08 | 6 |
| B6-R09 | 7 |
| B6-R10 | 7 |
| B6-R11 | 7 |
