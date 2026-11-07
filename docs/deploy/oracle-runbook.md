# Pilot runbook: Oracle Cloud Always Free (B6-D13)

Owner's manual. Every step that needs an account, a secret or a click in a cloud console is here, in
order. Nothing in the repository calls Oracle, DuckDNS or GitHub secrets for you. Commands starting
with `$` run on your own computer (Git Bash or WSL); commands starting with `deploy$` run on the
server as the `deploy` user.

After the one-time setup the deploy is automatic: every green merge to `main` redeploys
(`.github/workflows/deploy.yml`).

Placeholders: `<pilot-host>` is your DuckDNS name (for example `nd-pilot.duckdns.org`),
`<server-ip>` the VM's public IP, `<owner>/<repo>` the GitHub repository.

## 0. Order of work

1. Oracle account, VM, security list (sections 1 to 3)
2. DuckDNS name (4)
3. Object Storage bucket, access key, lifecycle rule (5)
4. age key for backups, replace `age-recipients.txt` (6)
5. Deploy key for the private repo, clone on the server (7)
6. GitHub secrets and variable (8)
7. `infra/.env.prod` (9)
8. First deploy (10)
9. Keycloak admin, pilot users, e2e users (11 to 13)
10. After the first backup: test-decrypt, staleness check, restore drill (14 to 16)
11. Operations: password rotation, reboots, teardown (17 to 19)

## 1. Oracle account

1. Sign up at oracle.com/cloud/free. **Card verification:** Oracle asks for a credit or debit card to
   verify identity (a small authorization is made and released). Always Free resources are not
   charged. Stay on the Always Free tier and do not upgrade to Pay As You Go.
2. **Region choice:** pick the home region when you register; it cannot be changed later. Choose one
   close to the users, and check that the Ampere A1 shape is offered there (Frankfurt, Amsterdam
   and Stockholm usually are). If "Out of capacity" appears, retry later or in another availability
   domain.

## 2. The VM (A1.Flex, 2 OCPU / 12 GB)

Console: Compute > Instances > Create instance.

| Setting | Value |
|---|---|
| Image | Canonical Ubuntu 24.04 (aarch64) |
| Shape | Ampere, `VM.Standard.A1.Flex`, **2 OCPU, 12 GB** memory (inside the free 4 OCPU / 24 GB, with headroom) |
| Boot volume | 100 GB (the free allowance is 200 GB) |
| Network | a public subnet, "Assign a public IPv4 address" on |
| SSH keys | paste your own admin public key here, so you can log in as `ubuntu`; the deploy key goes into cloud-init |
| Advanced options > Management > Cloud-init script | the whole of `infra/deploy/cloud-init.yaml`, after replacing `ssh-ed25519 REPLACE_WITH_THE_DEPLOY_PUBLIC_KEY` with the public key from section 7 |

Create the key pairs first (section 7), then the instance. Cloud-init takes a few minutes. It
installs Docker Engine and the compose plugin from Docker's official apt repository (the repository
key fingerprint is checked, and the packages are then held with `apt-mark hold`, so a Docker upgrade
is your decision), creates the `deploy` user (docker group, key-only login), disables password SSH,
and opens ports 22, 80 and 443 in iptables.

Reserve the address: Networking > Reserved public IPs, so it survives a rebuild.

## 3. Security list and the ARM/Oracle iptables note

Two firewalls apply and both must allow the traffic.

1. **Cloud security list** (Networking > VCN > Security Lists > Default): ingress rules, source
   `0.0.0.0/0`, TCP, destination ports **22**, **80** and **443**, nothing else. GitHub's runners
   have changing addresses, so port 22 stays open to everyone while the deploy workflow is used; SSH
   is key-only.
2. **iptables on the VM.** Oracle's Ubuntu images (arm64 included) ship iptables rules that reject
   everything but SSH, in addition to the cloud security list. `infra/deploy/cloud-init.yaml`
   (script `nd-open-ports`) inserts ACCEPT rules for 22, 80 and 443 ahead of that REJECT rule and
   saves them with `netfilter-persistent`. Check on the server:
   ```
   deploy$ sudo iptables -S INPUT | grep -E 'dport (22|80|443)'
   ```
   Nothing else is opened. Postgres, Keycloak and the engine are not published; only Caddy is. The
   Keycloak admin console listens on `127.0.0.1:8081` and is reached by SSH tunnel only.

## 4. DuckDNS

1. Log in at duckdns.org, create a subdomain (this is `<pilot-host>`), set its IP to `<server-ip>`,
   and copy the token.
2. **Update cron (on the server).** cloud-init installed `/etc/cron.d/nd-duckdns`, which calls
   `https://www.duckdns.org/update` every five minutes. It needs the token file (mode 600):
   ```
   deploy$ sudo install -d -m 700 /etc/nd
   deploy$ printf 'DUCKDNS_DOMAIN=nd-pilot\nDUCKDNS_TOKEN=<token>\n' | sudo tee /etc/nd/duckdns.env >/dev/null
   deploy$ sudo chmod 600 /etc/nd/duckdns.env
   deploy$ sudo /usr/local/sbin/nd-duckdns && echo updated
   ```
   `DUCKDNS_DOMAIN` is the subdomain without `.duckdns.org`. With a reserved IP the cron is only a
   safety net; keep it.
3. `getent hosts <pilot-host>` must answer `<server-ip>` before the first deploy, or Let's Encrypt
   cannot issue the certificate.

## 5. Object Storage for backups

1. Storage > Buckets > Create bucket, for example `nd-backups`, **Standard** tier, private (no
   public access). The name is `ND_BACKUP_BUCKET`.
2. Note the **namespace** (Tenancy details) and the region identifier (for example
   `eu-frankfurt-1`). The S3-compatible endpoint is
   `https://<namespace>.compat.objectstorage.<region>.oraclecloud.com`: that is
   `ND_BACKUP_S3_ENDPOINT`; the region identifier is `ND_BACKUP_S3_REGION`.
3. **Customer secret key:** Profile (top right) > My profile > Customer secret keys > Generate, name
   it `nd-backup`. The **secret is shown once**: copy it now. The access key is listed beside it.
   They are `ND_BACKUP_S3_SECRET_KEY` and `ND_BACKUP_S3_ACCESS_KEY`. The key acts as your user; for
   least privilege use a dedicated IAM user whose group may only manage this bucket's objects.
4. **Lifecycle rule (14 days):** bucket > Lifecycle policy rules > Create rule: name
   `expire-14-days`, action **Delete**, **14** days, all objects (no prefix filter). The Object
   Storage service needs permission once, in a tenancy policy:
   `Allow service objectstorage-<region> to manage object-family in tenancy`
   (use `compartment <name>` if the bucket is in a compartment). Without that policy the rule exists
   but deletes nothing, so look again after a few weeks: nothing older than 14 days may remain.
   Backups then stay well inside the free 20 GB.

## 6. Backup encryption key (age)

Backups are encrypted to a public key that is committed in the repository; only you hold the private
key. Until you replace the placeholder, `backup.sh` and `restore.sh` refuse to run, on purpose.

1. On your **own computer** (not the server):
   ```
   $ age-keygen -o nd-backup-identity.txt
   Public key: age1...
   ```
   age is at github.com/FiloSottile/age. Without installing it:
   `docker run --rm --entrypoint age-keygen nautical-deliverance/backup:dev` after building the image
   (`docker build -t nautical-deliverance/backup:dev infra/backup`).
2. **Keep `nd-backup-identity.txt`, the private key, offline**: a password manager's secure note and
   a copy on a USB stick in a drawer. Never commit it, never put it on the server, never put it in a
   GitHub secret. Without it no backup can ever be decrypted; with it anyone can read them.
3. Replace the contents of `infra/backup/age-recipients.txt` with the one public-key line
   (`age1...`), dropping the placeholder comment. Commit and merge. The backup image bakes the file
   in, so the next deploy rebuilds it.
4. Do the test-decrypt of the first real backup (section 14).

## 7. Deploy key and the clone (the repository is private)

Two ed25519 key pairs, both made on your own computer:

| Key | Private half | Public half |
|---|---|---|
| SSH login of the deploy workflow | GitHub secret `ND_DEPLOY_SSH_KEY` | authorized key of the `deploy` user (cloud-init) |
| Read-only repo **deploy key** (the server pulls the code) | `~/.ssh/id_repo` of `deploy` on the server | GitHub: repository Settings > Deploy keys > Add deploy key; leave "Allow write access" **off** |

```
$ ssh-keygen -t ed25519 -N '' -C nd-deploy -f nd-deploy       # login key
$ ssh-keygen -t ed25519 -N '' -C nd-repo-read -f nd-repo      # repo deploy key
```

Once the VM is up (`cloud-init status --wait` shows `done`):

```
$ scp -i nd-deploy nd-repo deploy@<server-ip>:.ssh/id_repo
$ ssh -i nd-deploy deploy@<server-ip>
deploy$ chmod 600 ~/.ssh/id_repo && nd-clone git@github.com:<owner>/<repo>.git
```

On the first connection compare the host key fingerprint with the one in the Oracle console
(instance > console connection) before you accept it. `nd-clone` pins GitHub's published SSH host
key (fingerprint `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`; if the check fails, compare it
with docs.github.com, "GitHub's SSH key fingerprints") and clones into `~/nd`. Afterwards delete
`nd-repo` on your computer; keep `nd-deploy` only until it is stored as the GitHub secret.

## 8. GitHub secrets and variable

Settings > Secrets and variables > Actions. Nothing else is read by `.github/workflows/deploy.yml`.

| Name | Kind | Value |
|---|---|---|
| `ND_DEPLOY_SSH_KEY` | secret | the whole private file `nd-deploy`, including the BEGIN/END lines |
| `ND_DEPLOY_KNOWN_HOSTS` | secret | the server's host key line from `ssh-keyscan -t ed25519 <server-ip>`; compare its fingerprint with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the server before saving |
| `ND_DEPLOY_HOST` | secret | `<server-ip>` (or a name that resolves to it) |
| `ND_PUBLIC_HOST` | secret | `<pilot-host>` (the same value as `ND_PUBLIC_HOST` in `.env.prod`) |
| `ND_E2E_USER` | secret | e-mail of the e2e buyer (section 13) |
| `ND_E2E_PASSWORD` | secret | that user's permanent password |
| `ND_E2E_OPERATOR_USER` | secret | e-mail of the e2e operator (optional: the Operator check is skipped without it) |
| `ND_E2E_OPERATOR_PASSWORD` | secret | that user's permanent password |
| `ND_DEPLOY_ENABLED` | variable (Variables tab) | `true`. Leave it unset until sections 1 to 13 are done: until then the deploy workflow is skipped instead of failing on every merge |

Strict host checking stays on: the workflow connects only to the key in `ND_DEPLOY_KNOWN_HOSTS`.
After a rebuild the host key changes, so update that secret.

## 9. `infra/.env.prod` (on the server, mode 600, never in git)

```
deploy$ cd ~/nd && cp infra/.env.prod.example infra/.env.prod && chmod 600 infra/.env.prod
deploy$ openssl rand -base64 24        # run once per secret below, one different value each
deploy$ nano infra/.env.prod
```

| Variable | Meaning / value |
|---|---|
| `ND_PUBLIC_HOST` | `<pilot-host>`; Caddy serves it with a Let's Encrypt certificate |
| `ND_DB_SUPERUSER_PASSWORD` | Postgres role `postgres`; also used by the backup container (it needs to read every row) |
| `ND_DB_OWNER_PASSWORD` | role `nd_owner` (migrations) |
| `ND_DB_APP_PASSWORD` | role `nd_app` (the engine at runtime) |
| `ND_DB_KEYCLOAK_PASSWORD` | role `keycloak` |
| `ND_KEYCLOAK_ADMIN_PASSWORD` | the bootstrap admin `admin` of Keycloak (section 11) |
| `ND_GIT_SHA` | placeholder: `deploy.sh` sets the real commit on every deploy |
| `ND_IMAGE_TAG` | image tag; compose defaults it to `dev`, leave it unset |
| `ND_BACKUP_BUCKET` | bucket name (section 5) |
| `ND_BACKUP_S3_ENDPOINT` | `https://<namespace>.compat.objectstorage.<region>.oraclecloud.com` |
| `ND_BACKUP_S3_REGION` | region identifier, for example `eu-frankfurt-1` |
| `ND_BACKUP_S3_ACCESS_KEY` | customer secret key: access key |
| `ND_BACKUP_S3_SECRET_KEY` | customer secret key: secret |

Every secret is required: compose refuses to start when one is missing (`${X:?}`). Keep a copy of the
file in your password manager: the DB passwords are needed again after a rebuild (section 19).

## 10. First deploy

Preconditions: DNS resolves (4), `age-recipients.txt` replaced and merged (6), secrets and variable
set (8), `.env.prod` written (9).

**The Keycloak database is created only on an empty volume.** `infra/db/init/02-keycloak.sh` runs
when Postgres initialises a new data directory, and never again. The first deploy must therefore
start on a **fresh volume**: a server where the stack was never started. If it was started once with
wrong passwords, tear down as in section 19 (this deletes the data: acceptable only before the pilot
has data).

Run it from GitHub: Actions > "Deploy pilot" > Run workflow, `sha` = the full 40-character hash of
the commit on `main` whose CI is green, **`first_deploy` ticked** (there is no backup yet, so the
backup freshness check is skipped). Later deploys run by themselves after every green CI run on
`main` (never for a pull request, never for a failed CI) and need no input.

The first deploy takes 10 to 20 minutes (native arm64 builds). To watch on the server:
`docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/.env.prod logs -f caddy`.

**The first Let's Encrypt issuance is the first live test of `protocols h1`.** Caddy runs with
HTTP/1.1 only (`protocols h1` in `infra/caddy/Caddyfile`, a workaround for an HTTP/2 vulnerability
until a patched Caddy ships, ruling R5). Every local check used Caddy's internal CA, so issuance from
Let's Encrypt with h1 only has not run before. If no certificate arrives within a few minutes, read
the Caddy log (ACME errors), check DNS and the security list, and report it; do not change the
setting without a decision.

Then open `https://<pilot-host>`: the sign-in page must appear. The workflow's smoke step
(`tools/pilot_smoke.sh`) should pass; the E2E step is expected to fail on this first run because the
e2e users do not exist yet (section 13). Re-run the workflow after sections 11 to 13.

## 11. Keycloak admin console and a named permanent admin

The admin console is **not** on the internet (`/admin` returns 404). Reach it by SSH tunnel:

```
$ ssh -L 8081:127.0.0.1:8081 deploy@<server-ip>
```

Keep that session open and browse to `http://localhost:8081/admin/master/console/`. Sign in as
`admin` with `ND_KEYCLOAK_ADMIN_PASSWORD`: the **bootstrap admin**, meant to be temporary.

1. Master realm > Users > Add user: your name, username = your e-mail, e-mail verified on.
2. Credentials > Set password with "Temporary" off; use a long unique password.
3. Role mapping > Assign role > `admin`.
4. Sign out, sign in as the new named admin, and check that Users is visible.
5. **Delete the bootstrap admin:** Users > `admin` > Delete. Keycloak creates a bootstrap admin only
   while the master realm has no admin, so it stays gone. `ND_KEYCLOAK_ADMIN_PASSWORD` stays in
   `.env.prod` because compose requires it, but it no longer opens anything.
6. Optional: add OTP to your admin account (Credentials > Configure OTP).

## 12. Pilot users (`tools/pilot_user.py`)

The pilot realm has **no users**. Create each one with the script, through the tunnel from section
11 (Keycloak's loopback port is the script's default `--url`):

```
$ ND_KC_ADMIN_PASSWORD='<your named admin password>' \
  uv run --project engine python tools/pilot_user.py --admin-user <your admin username> \
  --email buyer1@example.org --first Ada --last Buyer --role bunker_buyer
```

Roles: `admin`, `bunker_buyer`, `operator`, `viewer`. The organisation is Pilot Demo Shipping by
default. The script prints a **temporary password once** (on stdout, nowhere else): send it to the
user over a different channel than the one that carries the e-mail address. A repeat for an existing
e-mail is refused (exit code 2) and changes nothing; an unknown role is refused. The user must set
a new password at the first sign-in.

## 13. The e2e users

The E2E test needs a real `bunker_buyer` and, optionally, an `operator` in the pilot organisation.
Create them like any pilot user (section 12), for example `e2e-buyer@<your domain>` and
`e2e-operator@<your domain>`. Then:

**Each one must sign in once in a browser and set a permanent password before E2E can use them.**
The temporary password forces an "update password" screen that the test cannot pass. After setting
the permanent password, store the e-mail and password as `ND_E2E_USER`/`ND_E2E_PASSWORD` and
`ND_E2E_OPERATOR_USER`/`ND_E2E_OPERATOR_PASSWORD` (section 8). The inquiries the test creates have a
voyage starting with `E2E-` and are cancelled at the end, even when the test aborts.

Re-run the deploy workflow (`first_deploy` still ticked): smoke and E2E must now pass.

## 14. Test-decrypt the first real backup

The backup runs nightly at 02:15 UTC. To get the first one at once (on the server):

```
deploy$ cd ~/nd && docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/.env.prod exec backup backup.sh
BACKUP_KEY=nd/2026/11/07/nd-20261107T101500Z.tar.age
```

On your **own computer**, with the private key, download that object (OCI console > bucket > object >
Download, or an S3 client with the customer secret key) and prove that it opens:

```
$ age -d -i nd-backup-identity.txt nd-20261107T101500Z.tar.age | tar -tf -
nd.dump
keycloak.dump
```

Both names listed means the key pair works. "no identity matched" means the recipients file holds a
different public key than your private key: fix `age-recipients.txt`, redeploy, repeat. A backup you
cannot decrypt is not a backup. From now on deploys run without `first_deploy`.

## 15. Backup staleness check

Every deploy except a `first_deploy` one ends with `infra/backup/check_fresh.sh`, run inside the
running backup container through `infra/deploy/deploy.sh --check-backup`. It fails the workflow when
the newest `.ok` marker in the bucket is **26 hours old or older** (the nightly run plus margin), or
when there is none. By hand, any time:

```
deploy$ ~/nd/infra/deploy/deploy.sh --check-backup
newest backup marker: 2026/11/07/nd-20261107T021500Z.tar.age.ok (3 h old, limit 26 h)
```

A red check means the nightly job failed: read `docker compose ... logs backup`. A green check does
not prove that a backup can be restored; only the drill (section 16) does.

## 16. Restore drill (P4)

Do it once before the pilot starts and after any change to the backup scripts. It restores into a
throw-away database on **your own computer** (Docker Desktop), never over the live server. You need
the private key, the five `ND_BACKUP_*` values and this repository.

```
$ git clone git@github.com:<owner>/<repo>.git && cd <repo>
$ docker build -t nd-backup infra/backup
$ docker compose -p nd-drill -f infra/docker-compose.yml up -d --wait db
$ cp /path/to/nd-backup-identity.txt ./drill-identity.txt && chmod a+r drill-identity.txt
$ docker run --rm --network nd-drill_default -v "$PWD/drill-identity.txt:/work/identity.txt:ro" \
    -e PGHOST=db -e PGUSER=postgres -e PGPASSWORD=dev-superuser-password \
    -e ND_BACKUP_BUCKET -e ND_BACKUP_S3_ENDPOINT -e ND_BACKUP_S3_REGION \
    -e ND_BACKUP_S3_ACCESS_KEY -e ND_BACKUP_S3_SECRET_KEY \
    nd-backup restore.sh --identity /work/identity.txt <BACKUP_KEY>
RESTORED <BACKUP_KEY>
$ docker compose -p nd-drill -f infra/docker-compose.yml exec db psql -U postgres -d nd -c "select count(*) from inquiry"
$ docker compose -p nd-drill -f infra/docker-compose.yml exec db psql -U postgres -d keycloak -c "select username from user_entity order by 1"
$ rm drill-identity.txt
$ docker compose -p nd-drill -f infra/docker-compose.yml down --volumes     # the throw-away stack only
```

Export the five `ND_BACKUP_*` values in your shell first (do not write them into files). The restore
refuses a non-empty target without `--force`, refuses a key without an `.ok` marker, and verifies the
sha256 before decrypting. The inquiry count and the Keycloak user list must match the live pilot
(compare with its dashboard and Keycloak's Users page).

Restoring the real server uses the same script with the stack's database up and engine, Keycloak, web
and Caddy stopped (`docker compose ... stop engine keycloak web caddy`), then `up -d`. The
`.env.prod` DB passwords must be the ones the dump's roles expect.

### Drill log (copy, fill in, keep with your records)

```
Restore drill log
Date (UTC):                    ____-__-__
Performed by:                  ______________________
Backup key restored:           nd/____/__/__/nd-________T______Z.tar.age
Backup age at drill (hours):   ____
age-decrypt with offline key:  [ ] ok   [ ] failed
restore.sh result:             [ ] "RESTORED <key>"   [ ] error: ______________
inquiry count   live: ____   restored: ____   equal: [ ] yes  [ ] no
Keycloak users  live: ____   restored: ____   equal: [ ] yes  [ ] no
Time from start to verified:   ____ min
Problems and fixes:            ______________________________________
Result:                        [ ] PASS   [ ] FAIL (open an issue)
```

## 17. Rotating a database password

Changing `ND_DB_*_PASSWORD` in `.env.prod` alone **does not change the role in Postgres**: the roles
are created once, on an empty volume, so the stack would fail to log in. Do both, in this order (on
the server):

```
deploy$ cd ~/nd && alias nd='docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/.env.prod'
deploy$ nd exec db psql -U postgres -d nd -c '\password nd_app'      # typed twice, not echoed, not in history
deploy$ nano infra/.env.prod                                          # the same new value in ND_DB_APP_PASSWORD
deploy$ nd up -d                                                      # recreates the engine with the new URL
```

The role change is `ALTER ROLE nd_app PASSWORD '...'` underneath; `\password` avoids putting the
value in a command line. Same pattern for `nd_owner` (`ND_DB_OWNER_PASSWORD`, used at engine start for
migrations), `keycloak` (`ND_DB_KEYCLOAK_PASSWORD`; recreates keycloak) and `postgres`
(`ND_DB_SUPERUSER_PASSWORD`; also recreates the backup container). Afterwards `nd ps` must show
everything healthy and the next nightly backup must still produce an `.ok`.

## 18. Reboots

`restart: unless-stopped` brings the containers back only if the Docker daemon starts at boot, and
the nightly backup runs inside a container (supercronic), so it survives the same way. cloud-init
runs `systemctl enable --now docker`; verify once, and after any VM rebuild:

```
deploy$ systemctl is-enabled docker
enabled
deploy$ sudo reboot
$ curl -fsS https://<pilot-host>/api/v1/health            # after a minute or two
```

If it says `disabled`: `sudo systemctl enable docker.service containerd.service`. A backup that
would have run while the VM was down is not made up afterwards; the staleness check (section 15)
shows it.

## 19. Tear down and rebuild

Redeploy a known-good commit: Actions > Deploy pilot > Run workflow with that `sha` (no
`first_deploy`).

Rebuild from scratch (free-tier termination, a broken VM, a new region):

1. Create the VM from `infra/deploy/cloud-init.yaml` and repeat sections 2 to 4, 7 and 9 (restore
   `.env.prod` from your copy). Update `ND_DEPLOY_HOST` and `ND_DEPLOY_KNOWN_HOSTS`.
2. Deploy once with `first_deploy` (fresh volume, empty database).
3. Restore the latest backup as in section 16 (stop engine and Keycloak first), then `up -d`.
4. Run the deploy workflow again without `first_deploy`.

Tear down a stack on purpose (this **deletes all data**: take a backup first and run the drill).
The workflow and `deploy.sh` never do this; only you, by hand:

```
deploy$ cd ~/nd && docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/.env.prod down --volumes
```

## 20. Where things are

| What | Where |
|---|---|
| Deploy workflow | `.github/workflows/deploy.yml` |
| Server deploy script | `infra/deploy/deploy.sh` (on the server `~/nd/infra/deploy/deploy.sh`) |
| cloud-init | `infra/deploy/cloud-init.yaml` |
| Production compose overlay | `infra/docker-compose.prod.yml`, variables in `infra/.env.prod.example` |
| Backup, restore, staleness check | `infra/backup/` |
| Pilot user script | `tools/pilot_user.py` |
| User guide | `docs/user-guide.md` |
