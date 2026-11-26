# Pilot runbook: Oracle Cloud Always Free (B6-D13)

Owner's manual. Every step that needs an account, a secret or a click in a cloud console is here, in
order. Nothing in the repository calls Oracle, DuckDNS or GitHub secrets for you.

Where a command runs (the prompt in front of it tells you):

| Prompt | Where | How to get there |
|---|---|---|
| `$` | your own computer (Git Bash or WSL) | |
| `ubuntu$` | the server, as the admin user `ubuntu` (has `sudo`) | `ssh ubuntu@<server-ip>` with the admin key you gave Oracle in section 2 |
| `deploy$` | the server, as the `deploy` user (no `sudo`) | from `ubuntu$`: `sudo -iu deploy` (leave with `exit`) |

To run several `deploy$` lines from `ubuntu$` in one paste, use a heredoc:
`sudo -u deploy -H bash <<'EOF'`, the lines, then `EOF`. `sudo -iu deploy bash -c '...'` joins the
lines into one, so a multi-line command breaks.

The `deploy` user's own key (`nd-deploy`) belongs to GitHub only. You never log in with it, so you can
delete your local copy once it is stored as a GitHub secret, and everything you do by hand goes
through `ubuntu`. Never delete the admin key: it is your way in (and the SSH tunnel in section 11).

On Windows in **Git Bash**, `docker run` arguments that start with `/` are rewritten to Windows
paths. Put `MSYS_NO_PATHCONV=1` in front of such a command (the scripts in `tools/` already do).

After the one-time setup the deploy is automatic: every green merge to `main` redeploys
(`.github/workflows/deploy.yml`).

Passwords and tokens you generate yourself always use `openssl rand -hex 24`: hexadecimal is safe in
URLs and in `.env` files (base64 can contain `/`, `+` and `=`).

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
11. Operations: password rotation, reboots, rollback, rebuild and restore (17 to 19)

**Fast path for a demo with invented data only.** Sections 1 to 4, 7 (the repo deploy key and the
clone), 9 with the five `ND_BACKUP_*` values set to `not-configured-yet`, then the first deploy by hand
on the server (section 10, "By hand on the server") and the pilot users (section 12). This skips the
backups (5, 6, 14 to 16), GitHub secrets and automatic deploys (8, 13), and the named Keycloak admin
(11). Nothing is backed up and every update is a manual deploy. Do all the skipped sections before
the pilot holds real data.

What runs when: CI (`.github/workflows/ci.yml`, the fast gates) runs on every push and pull request.
The heavy gates (`.github/workflows/heavy.yml`: arm64 builds, browser E2E, backup/restore, prod overlay,
Keycloak user script) run nightly on `main`, on demand (Actions > Heavy > Run workflow), and on pushes
and pull requests that change `infra/`, a Dockerfile, the E2E, a backup, smoke or pilot script. The
deploy workflow waits for **CI only**, not for the heavy run; its own E2E step tests the pilot after
every deploy. A red nightly heavy run is a reason to look before the next merge.

## 1. Oracle account

1. Sign up at oracle.com/cloud/free. **Card verification:** Oracle asks for a credit or debit card to
   verify identity (a small authorization is made and released). Always Free resources are not
   charged.
2. **Upgrade to Pay As You Go (D-081).** On a free-trial account, A1 capacity is often unavailable
   ("Out of capacity"). Pay As You Go accounts get capacity first and are still not charged for Always
   Free resources. Upgrade under Billing > Upgrade and Manage Payment. If that page fails to load, try a
   private window or later. Then set a **budget alert**: Billing > Budgets > Create budget, amount 1
   (in your billing currency), alert at 100 % of actual spend to your e-mail. Create only resources
   marked "Always Free eligible".
3. **Region choice:** pick the home region when you register; it cannot be changed later. Choose one
   close to the users, and check that the Ampere A1 shape is offered there (Frankfurt, Amsterdam
   and Stockholm usually are). If "Out of capacity" appears, retry later or in another availability
   domain.
4. **Network:** Networking > Virtual cloud networks > Start VCN Wizard > "Create VCN with Internet
   Connectivity", name for example `nd-pilot-vcn`. It creates the public subnet that section 2 uses.

## 2. The VM (A1.Flex, 2 OCPU / 12 GB)

Console: Compute > Instances > Create instance.

| Setting | Value |
|---|---|
| Image | Canonical Ubuntu 24.04 Minimal (aarch64); the full image works too. `cloud-init.yaml` installs `gnupg`, which Minimal lacks |
| Shape | Ampere, `VM.Standard.A1.Flex`, **2 OCPU, 12 GB** memory (the Always Free A1 allowance) |
| Boot volume | 100 GB (the free allowance is 200 GB) |
| Network | the VCN's public subnet (section 1), "Assign a public IPv4 address" on |
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
   ubuntu$ sudo iptables -S INPUT | grep -E 'dport (22|80|443)'
   ```
   Nothing else is opened. Postgres, Keycloak and the engine are not published; only Caddy is. The
   Keycloak admin console listens on `127.0.0.1:8081` and is reached by SSH tunnel only.

## 4. DuckDNS

1. Log in at duckdns.org, create a subdomain (this is `<pilot-host>`), set its IP to `<server-ip>`,
   and copy the token.
2. **Update cron (on the server).** cloud-init installed `/etc/cron.d/nd-duckdns`, which calls
   `https://www.duckdns.org/update` every five minutes. It needs the token file (mode 600):
   ```
   ubuntu$ sudo install -d -m 700 /etc/nd
   ubuntu$ printf 'DUCKDNS_DOMAIN=nd-pilot\nDUCKDNS_TOKEN=<token>\n' | sudo tee /etc/nd/duckdns.env >/dev/null
   ubuntu$ sudo chmod 600 /etc/nd/duckdns.env
   ubuntu$ sudo /usr/local/sbin/nd-duckdns && echo updated
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
| Read-only repo **deploy key** (the server pulls the code) | `~deploy/.ssh/id_repo` on the server | GitHub: repository Settings > Deploy keys > Add deploy key; leave "Allow write access" **off** |

```
$ ssh-keygen -t ed25519 -N '' -C nd-deploy -f nd-deploy       # login key
$ ssh-keygen -t ed25519 -N '' -C nd-repo-read -f nd-repo      # repo deploy key
```

In Windows PowerShell 5.1 an empty passphrase is written `-N '""'`. Keep the keys outside the
repository, for example in `~/.ssh/nd/`.

Once the VM is up (`cloud-init status --wait` shows `done`):

```
$ scp nd-repo ubuntu@<server-ip>:/tmp/id_repo
$ ssh ubuntu@<server-ip>
ubuntu$ sudo install -m 600 -o deploy -g deploy /tmp/id_repo ~deploy/.ssh/id_repo && rm /tmp/id_repo
ubuntu$ sudo -iu deploy nd-clone git@github.com:<owner>/<repo>.git
```

On the first connection compare the host key fingerprint with the one in the Oracle console
(instance > console connection) before you accept it. `nd-clone` pins GitHub's published SSH host
key (fingerprint `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`; if the check fails, compare it
with docs.github.com, "GitHub's SSH key fingerprints") and clones into `~deploy/nd`. Afterwards delete
`nd-repo` on your computer, and `nd-deploy` as soon as it is stored as the GitHub secret (section 8).
Keep your admin key: every later step uses it.

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
| `ND_DEPLOY_ENABLED` | variable (Variables tab) | `true`, set **after** the first manual deploy and sections 11 to 13 (section 10). It switches on only the automatic deploy after each green merge; a manual "Run workflow" deploy never needs it |
| `ND_E2E_OPERATOR_NAME` | variable (optional) | display name of the e2e operator as shown in the inquiry form's Operator list (section 13). Unset: the demo operator |

Strict host checking stays on: the workflow connects only to the key in `ND_DEPLOY_KNOWN_HOSTS`.
After a rebuild the host key changes, so update that secret.

## 9. `infra/.env.prod` (on the server, mode 600, never in git)

```
ubuntu$ sudo -iu deploy
deploy$ cd ~/nd && cp infra/.env.prod.example infra/.env.prod && chmod 600 infra/.env.prod
deploy$ openssl rand -hex 24        # run once per secret below, one different value each
deploy$ nano infra/.env.prod
```

Use `openssl rand -hex 24` for every password. The engine also encodes its database passwords before
it builds the connection URLs, so a password you chose yourself with `/`, `@` or `:` works, but
generate them anyway: a `.env` value with spaces, quotes, `#` or `$` is still misread.

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

Preconditions: DNS resolves (4), `age-recipients.txt` replaced and merged (6), secrets set (8),
`.env.prod` written (9). `ND_DEPLOY_ENABLED` stays **unset** for now.

**The Keycloak database is created only on an empty volume.** `infra/db/init/02-keycloak.sh` runs
when Postgres initialises a new data directory, and never again. The first deploy must therefore
start on a **fresh volume**: a server where the stack was never started. If it was started once with
wrong passwords, tear down as in section 19 (this deletes the data: acceptable only before the pilot
has data).

**From GitHub (needs section 8).** Run it from GitHub: Actions > "Deploy pilot" > Run workflow (branch `main`), `sha` = the full
40-character hash of a commit on `main` whose push CI run is green. The workflow checks that run,
the server checks that the commit is on `main`, and neither needs `ND_DEPLOY_ENABLED`.
`allow_rollback` stays off. Later deploys run by themselves after every green CI run on `main` once
you set `ND_DEPLOY_ENABLED` (never for a pull request, never for a failed CI). The workflow waits for
CI only, not for the heavy workflow.

Two things are expected to be red or yellow on this first run:

- the **E2E step fails** because the e2e users do not exist yet (section 13);
- the **backup freshness step only warns** ("no backup .ok marker yet"): the first nightly backup has
  not happened. A missing backup is allowed for the first 26 h after the first deploy; after that a
  missing backup fails the deploy, and from the first backup on an old newest backup fails too (section 15).

The first deploy takes 10 to 20 minutes (native arm64 builds). To watch on the server (as `deploy`,
after the `nd` helper from section 14 is defined):
`nd logs -f caddy`.

**The first Let's Encrypt issuance is the first live test of `protocols h1`.** Caddy runs with
HTTP/1.1 only (`protocols h1` in `infra/caddy/Caddyfile`, a workaround for an HTTP/2 vulnerability
until a patched Caddy ships, ruling R5). Every local check used Caddy's internal CA, so issuance from
Let's Encrypt with h1 only has not run before. If no certificate arrives within a few minutes, read
the Caddy log (ACME errors), check DNS and the security list, and report it; do not change the
setting without a decision.

Then open `https://<pilot-host>`: the sign-in page must appear. The workflow's smoke step
(`tools/pilot_smoke.sh`) should pass. Re-run the workflow after sections 11 to 13, then set
`ND_DEPLOY_ENABLED=true` (section 8) so that every green merge deploys.

**By hand on the server (fast path, no GitHub secrets).** Use the full 40-character hash of a
commit on `main`:

```
ubuntu$ sudo -u deploy -H bash -c 'cd ~/nd && nohup infra/deploy/deploy.sh <sha> > ~/deploy.log 2>&1 &'
ubuntu$ sudo tail -f /home/deploy/deploy.log
```

It is done when the log ends with `deployed <sha>`. Ctrl+C stops only the `tail`. If the build stops
on a network error while downloading a package (for example `stream error` from `proxy.golang.org`),
run the same command again: the finished layers are cached.

A change to `deploy.sh` itself takes effect one deploy late: the server runs the copy that was
checked out by the previous deploy, and replaces it only while checking out the new commit.

## 11. Keycloak admin console and a named permanent admin

The admin console is **not** on the internet (`/admin` returns 404). Reach it by SSH tunnel through
the admin user:

```
$ ssh -L 8081:127.0.0.1:8081 ubuntu@<server-ip>
```

Keep that session open and browse to `http://localhost:8081/admin/master/console/`. Sign in as
`admin` with `ND_KEYCLOAK_ADMIN_PASSWORD`: the **bootstrap admin**, meant to be temporary. (The host
port 8081 must be free on your computer: stop a local dev stack first.)

1. Master realm > Users > Add user: your name, username = your e-mail, e-mail verified on.
2. Credentials > Set password with "Temporary" off; use a long unique password.
3. Role mapping > Assign role > `admin`.
4. Sign out, sign in as the new named admin, and check that Users is visible.
5. **Delete the bootstrap admin:** Users > `admin` > Delete. Keycloak creates a bootstrap admin only
   while the master realm has no admin, so it stays gone. `ND_KEYCLOAK_ADMIN_PASSWORD` stays in
   `.env.prod` because compose requires it, but it no longer opens anything.
6. Optional: add OTP to your named admin (Credentials > Configure OTP). **OTP breaks
   `tools/pilot_user.py`:** the script signs in with a password grant that sends no one-time code,
   so it fails for an account with OTP. Either skip OTP on the account that runs the script, or keep
   OTP on your named admin and create a second admin `pilot-script` (same steps 1 to 3, a long
   `openssl rand -hex 24` password, **no OTP**) that you use only for `pilot_user.py` and disable in
   between (Users > pilot-script > Enabled off).

## 12. Pilot users (`tools/pilot_user.py`)

The pilot realm has **no users**. Create each one with the script, through the tunnel from section
11 (Keycloak's loopback port is the script's default `--url`):

```
$ ND_KC_ADMIN_PASSWORD='<password of the admin that has no OTP>' \
  uv run --project engine python tools/pilot_user.py --admin-user <that admin's username> \
  --email buyer1@example.org --first Ada --last Buyer --role bunker_buyer
```

The script uses the Python standard library only, so it also runs **on the server** with no tunnel
and no `uv`. This form reads the password of the bootstrap `admin` (fast path) from `.env.prod`
without showing it:

```
ubuntu$ sudo -u deploy -H bash <<'EOF'
cd ~/nd
export ND_KC_ADMIN_PASSWORD="$(grep '^ND_KEYCLOAK_ADMIN_PASSWORD=' infra/.env.prod | cut -d= -f2-)"
python3 tools/pilot_user.py --admin-user admin --email buyer@pilot.test --first Bea --last Buyer --role bunker_buyer
EOF
```

Several roles: repeat `--role`. To give an existing user more roles (the password is not touched):

```
ubuntu$ sudo -u deploy -H bash <<'EOF'
cd ~/nd
export ND_KC_ADMIN_PASSWORD="$(grep '^ND_KEYCLOAK_ADMIN_PASSWORD=' infra/.env.prod | cut -d= -f2-)"
python3 tools/pilot_user.py --admin-user admin --email buyer@pilot.test --first Bea --last Buyer --role bunker_buyer --role admin
python3 tools/pilot_user.py --admin-user admin --email <her e-mail> --add-role --role admin
EOF
```

After section 11 has removed the bootstrap admin, use the named admin and its password instead.
The pilot sends no e-mail, so the address is only the sign-in name: an invented address under
`.test` works.

Roles: `admin`, `bunker_buyer`, `operator`, `viewer`. The organisation is Pilot Demo Shipping by
default. The script prints a **temporary password once** (on stdout, nowhere else): send it to the
user over a different channel than the one that carries the e-mail address. A repeat for an existing
e-mail is refused (exit code 2) and changes nothing; an unknown role is refused; `--add-role` for an e-mail with no user exits 2. The user must set
a new password at the first sign-in.

## 13. The e2e users

The E2E test needs a real `bunker_buyer` and, optionally, an `operator` in the pilot organisation.
Create them like any pilot user (section 12), for example `e2e-buyer@<your domain>` and
`e2e-operator@<your domain>`. Then:

**Each one must sign in once in a browser and set a permanent password before E2E can use them.**
The temporary password forces an "update password" screen that the test cannot pass. After setting
the permanent password, store the e-mail and password as `ND_E2E_USER`/`ND_E2E_PASSWORD` and
`ND_E2E_OPERATOR_USER`/`ND_E2E_OPERATOR_PASSWORD` (section 8). The inquiry form lists operators by
name, and the pilot also has real colleagues in that list: set the variable `ND_E2E_OPERATOR_NAME`
to the e2e operator's first and last name so the test picks exactly that one (unset, it picks the
demo operator). The inquiries the test creates have a voyage starting with `E2E-` and are cancelled
at the end, even when the test aborts.

Re-run the deploy workflow (a new manual run of a commit on `main`): smoke and E2E must now pass.
Then set `ND_DEPLOY_ENABLED` (section 8).

## 14. Test-decrypt the first real backup

Server commands in sections 14 to 19 run as `deploy` (`ssh ubuntu@<server-ip>`, then
`sudo -iu deploy`). Define the `nd` helper once per session; it is the compose command for the
production stack:

```
deploy$ cd ~/nd
deploy$ nd() { docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/.env.prod "$@"; }
```

The backup runs nightly at 02:15 UTC. To get the first one at once:

```
deploy$ nd exec backup backup.sh
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
cannot decrypt is not a backup.

## 15. Backup staleness check

Every deploy ends with `infra/backup/check_fresh.sh`, run inside the running backup container
through `infra/deploy/deploy.sh --check-backup`. It fails the workflow when the newest `.ok`
marker in the bucket is **26 hours old or older** (the nightly run plus margin). **A missing backup
is allowed for the first 26 h after the first deploy** (`deploy.sh` records the time once in
`/srv/nd/FIRST_DEPLOYED`; the check prints a warning and passes); after that a missing backup fails
the deploy, as does a missing `FIRST_DEPLOYED`. A missing or inaccessible bucket (for example a typo
in `ND_BACKUP_BUCKET`) and a failed listing (credentials, network) always fail. By hand,
any time:

```
deploy$ ~/nd/infra/deploy/deploy.sh --check-backup
newest backup marker: 2026/11/07/nd-20261107T021500Z.tar.age.ok (3 h old, limit 26 h)
```

A red check means the nightly job failed: read `nd logs backup`. A green check does not prove that a
backup can be restored; only the drill (section 16) does.

## 16. Restore drill (P4)

Do it once before the pilot starts and after any change to the backup scripts. It restores into a
throw-away database on **your own computer** (Docker Desktop), never over the live server. You need
the private key, the five `ND_BACKUP_*` values and this repository.

Export the values first, in the same shell (do not write them into files):

```
$ git clone git@github.com:<owner>/<repo>.git && cd <repo>
$ export ND_BACKUP_BUCKET=... ND_BACKUP_S3_ENDPOINT=... ND_BACKUP_S3_REGION=...
$ export ND_BACKUP_S3_ACCESS_KEY=... ND_BACKUP_S3_SECRET_KEY=...
$ export ND_DRILL_IDENTITY=/path/to/nd-backup-identity.txt
$ bash tools/restore_drill.sh <BACKUP_KEY>
RESTORED <BACKUP_KEY>
inquiries in the restored database:
12
Keycloak users in the restored database:
...
```

The script builds the backup image, starts a database of its own (project `nd-drill`, with the
production role layout from `infra/docker-compose.drill.yml`, so the `keycloak` role and database
exist, and **no published port**, so it cannot collide with a dev stack), runs `restore.sh` in the
backup image with a temporary copy of your key, prints the inquiry count and the Keycloak users, and
removes the temporary copy and the throw-away stack when it ends, even on an error. It sets
`MSYS_NO_PATHCONV=1` itself for Git Bash. Run by hand, any `docker run` with `-v ...:/work/...` needs
`MSYS_NO_PATHCONV=1` in front.

The restore refuses a non-empty target without `--force`, refuses a key without an `.ok` marker, and
verifies the sha256 before decrypting. The inquiry count and the Keycloak user list must match the
live pilot (compare with its dashboard and Keycloak's Users page).

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
the server, as `deploy`, with `nd` defined as in section 14):

```
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
ubuntu$ systemctl is-enabled docker
enabled
ubuntu$ sudo reboot
$ curl -fsS https://<pilot-host>/api/v1/health            # after a minute or two
```

If it says `disabled`: `sudo systemctl enable docker.service containerd.service`. A backup that
would have run while the VM was down is not made up afterwards; the staleness check (section 15)
shows it.

## 19. Rollback, restore onto the server, rebuild, tear down

### Roll back to a known-good commit

A deploy is a checkout of one commit, so going back is deploying an older one. The server refuses an
older commit than the one running (recorded in `/srv/nd/DEPLOYED_SHA`) and any commit that is not on
`main`, unless you say so on purpose: Actions > Deploy pilot > Run workflow, `sha` = the known-good
commit, **`allow_rollback` ticked** (this passes `--allow-rollback` to `deploy.sh`). The workflow still wants a green push CI run for that commit.
Before rolling back, set the variable `ND_DEPLOY_ENABLED=false`, so that a green merge (or a re-run of
the bad commit's CI) cannot deploy forward again past the rollback; set it back to `true` once the fix is on `main`.
A rollback does not undo database migrations: only go back to a commit whose schema the current
database still satisfies; otherwise restore a backup as below.

### Restore a backup onto the real server

Use this to recover from data loss or after a rebuild (the database is then not empty: the first
deploy ran the migrations, the pilot seed and the realm import, so `--force` is required). It needs the
**private key on the server for a few minutes**, a deliberate, time-boxed exception to section 6: the
key goes into RAM-backed `/dev/shm`, is never written to disk, and is shredded afterwards. The key
is created with `umask 077` (mode 600), then made readable (644) only because the container user
must read it. On **any failure**, the commands below shred it (the `trap` on the second line covers a dropped session); if the session dies, run
`shred -u /dev/shm/nd-id` yourself before doing anything else.

```
$ ssh ubuntu@<server-ip> 'umask 077; cat > /dev/shm/nd-id && chmod 644 /dev/shm/nd-id || { shred -u /dev/shm/nd-id; exit 1; }' < nd-backup-identity.txt
$ ssh ubuntu@<server-ip>
ubuntu$ trap 'shred -u /dev/shm/nd-id 2>/dev/null' EXIT
ubuntu$ sudo -iu deploy
deploy$ cd ~/nd
deploy$ nd() { docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file infra/.env.prod "$@"; }
deploy$ nd stop engine keycloak web caddy
deploy$ nd run --rm --no-deps -v /dev/shm/nd-id:/work/identity.txt:ro backup restore.sh --identity /work/identity.txt --force <BACKUP_KEY>
RESTORED <BACKUP_KEY>
deploy$ exit
ubuntu$ shred -u /dev/shm/nd-id && ls /dev/shm/nd-id
ls: cannot access '/dev/shm/nd-id': No such file or directory
ubuntu$ sudo -iu deploy
deploy$ cd ~/nd && nd up -d --wait
```

`<BACKUP_KEY>` is the object key from the bucket (or from `BACKUP_KEY=` in the backup log). `--force`
replaces the existing tables with the backup's (`pg_restore --clean`), so it destroys whatever the
database holds now: take a backup first unless the data is already lost. The restore refuses while the
engine or Keycloak is connected, which is why they are stopped. The `.env.prod` DB passwords must be
the ones the dump's roles expect (a rebuild: your saved copy of `.env.prod`). Check afterwards:
`nd ps` healthy, sign in, the dashboard counts match, and run the deploy workflow again.

### Rebuild from scratch (free-tier termination, a broken VM, a new region)

1. Create the VM from `infra/deploy/cloud-init.yaml` and repeat sections 2 to 4, 7 and 9 (restore
   `.env.prod` from your copy). Update `ND_DEPLOY_HOST` and `ND_DEPLOY_KNOWN_HOSTS`.
2. Deploy once by hand (section 10; a fresh volume and an empty database; the freshness check warns
   until a backup exists, or passes if the bucket still holds the old ones).
3. Restore the latest backup onto the server as above.
4. Run the deploy workflow again; E2E must pass (the e2e users come back with the Keycloak restore).

### Tear down a stack on purpose

This **deletes all data**: take a backup first and run the drill. The workflow and `deploy.sh` never
do this; only you, by hand:

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
| Restore drill | `tools/restore_drill.sh`, `infra/docker-compose.drill.yml` |
| Heavy CI gates | `.github/workflows/heavy.yml` |
| User guide | `docs/user-guide.md` |
