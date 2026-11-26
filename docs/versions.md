# Pinned versions

Single source of truth for versions (S0 Task 1, decision D-030). Verified 2026-11-04.
Rule: every image/tool is a release at least 14 days old on 2026-11-04 (published on or before 2026-10-21).

## Python: 3.14 (D-030)

Newest CPython minor where every binary dependency has both `manylinux x86_64` and `win_amd64` wheels.
Python 3.15 (final 3.15.2) is rejected: `eccodes` publishes no `cp315` wheel (only cp39-cp314 win_amd64).

| Package | Version | Linux x86_64 wheel | Windows wheel |
|---|---|---|---|
| numpy | 2.5.4 | numpy-2.5.4-cp314-cp314-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl | numpy-2.5.4-cp314-cp314-win_amd64.whl |
| eccodes | 2.50.0 | py3-none-any (eccodes-2.50.0-py3-none-any.whl) + binary via eccodeslib | eccodes-2.50.0-cp314-cp314-win_amd64.whl |
| eccodeslib | 2.50.0.33 | eccodeslib-2.50.0.33-cp314-cp314-manylinux_2_28_x86_64.whl | n/a (Windows binary is inside the eccodes wheel) |
| shapely | 2.2.0 | shapely-2.2.0-cp314-cp314-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl | shapely-2.2.0-cp314-cp314-win_amd64.whl |
| psycopg-binary | 3.3.8 | psycopg_binary-3.3.8-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.whl | psycopg_binary-3.3.8-cp314-cp314-win_amd64.whl |
| pydantic-core | 2.50.2 | pydantic_core-2.50.2-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.whl | pydantic_core-2.50.2-cp314-cp314-win_amd64.whl |
| xarray | 2026.9.0 | pure Python: xarray-2026.9.0-py3-none-any.whl | same |
| cfgrib | 0.9.15.1 | pure Python: cfgrib-0.9.15.1-py3-none-any.whl | same |

Source: `https://pypi.org/pypi/<package>/json`.

- `.python-version`: `3.14` (latest 3.14 patch at time of check: 3.14.10, released 2026-10-25).
- Docker base image uses 3.14.8 (the newest 3.14 patch image at least 14 days old).

## Images and toolchain

Dates are the Docker Hub / quay.io `last_updated` of the tag (registry tags are rebuilt, so this is the last push).

| Item | Pinned tag | Published | Notes |
|---|---|---|---|
| PostGIS | own image `infra/postgis` on `postgres:17.12-trixie` (index digest `87c8b42f...`), `postgresql-17-postgis-3` + `-scripts` 3.5.2+dfsg-1 | 2026-11-24 (base), 2026-02 (PostGIS) | Multi-arch (amd64 + arm64), B6-R02. Base is < 14 days old by R14 (17.11 has fixable PostgreSQL, krb5 and zlib CVEs); zstd is upgraded in the image until the base ships 1.5.7+dfsg-1+deb13u1. PGDG only has 3.6+ for trixie; 3.5.2 comes from Debian main. gosu (Go 1.24.6 stdlib CVEs) is replaced by a setpriv wrapper. Trivy clean. GEOS 3.13.1, PROJ 9.6.0, GDAL 3.10.3, SFCGAL 2.0.0 all from Debian main, pinned exactly, PGDG geo builds blocked. |
| Keycloak | `quay.io/keycloak/keycloak:26.8.0` | 2026-10-10 | 26.8.1 tags pushed 2026-10-13 / 2026-10-31 (too recent). |
| Node (LTS "Krypton", v24) | `node:24.22.0-alpine` | 2026-10-14 | Node 24.22.0 released 2026-10-14. Node 26 became LTS 2026-10-28 (too recent). |
| nginx | `nginxinc/nginx-unprivileged:1.30.6-alpine` | 2026-10-19 | Stable 1.30 branch. |
| Python image | `python:3.14.10-slim-trixie` | 2026-11-02 | Debian 13 (trixie). **Security exception (R14, 2026-11-04):** newer than 14 days, chosen over 3.14.8 because it is the newest rebuild of the same minor; digest `sha256:930e1abb...`. |
| pnpm | `12.15.0` | 2026-10-21 | From registry.npmjs.org publish time. |
| uv (engine image build) | `0.13.4` | 2026-10-20 | PyPI upload time. 0.13.5+ are newer than 14 days on 2026-11-04. |

## Security exceptions (2026-11-04)

Controller ruling R14: security beats the 14-day rule. Trivy (HIGH/CRITICAL, fixes available) was run against both images.
- Engine: base moved 3.14.8 -> 3.14.10 (digest `fbecd461...` -> `930e1abb...`); pip (with vendored certifi/msgpack/urllib3/setuptools) is deleted from the runtime stage. Remaining findings are Debian 13.7 OS packages (util-linux family CVE-2026-76642/78408/78409/78410, ncurses CVE-2025-69720, libsqlite3 CVE-2026-119373, systemd CVE-2026-16742, libacl1 CVE-2026-54369, perl-base CVE-2026-9538). Debian's tracker marks them `affected`/`fix_deferred` with no fixed version, so no package upgrade exists yet (checked 2026-11-04 with a targeted `apt-get install --only-upgrade` in a trial build: versions unchanged, so the step was not kept). Trivy passes with `--ignore-unfixed`; revisit when Debian ships fixes.
- Web: no newer `nginx-unprivileged` tag exists (1.30.6-alpine and 1.31.7-alpine3.24 carry the same alpine 3.24.2 findings), so curl, libcurl, freetype, fontconfig, brotli-libs and libexpat (unused for static serving) are removed with `apk del`. Trivy: clean.

B6 ruling R2 (2026-11-06): the PostGIS image base `postgres:17.11-trixie` (pushed 2026-11-05, under 14 days) is kept, following S0 ruling R14 (security beats the 14-day rule). `17.10` has 17 CVEs fixed in 17.11 (PostgreSQL 17.11 security release) and runs on Debian 13.6, whose OS packages 13.7 has already fixed; staying on 17.10 would need unpinned PGDG upgrades over a pinned digest. Digest-pinned (index `748a18a5...`). Superseded 2026-11-26 by `postgres:17.12-trixie` (index `87c8b42f...`, pushed 2026-11-24) on the same R14 grounds: 17.11 has fixable HIGH CVEs (PostgreSQL 17.12 security release, krb5, zlib), and the nightly backup-image scan failed from 2026-11-13.

B6 ruling R5 (2026-11-06): the Caddy edge image `caddy:2.11.9-alpine` (pushed 2026-11-05, under 14 days; digest `0bbb055b...`) is kept, extending the R2 security exception. The older tags 2.11.6 and 2.11.7 carry 10-13 fixable HIGH/CRITICAL findings (Go stdlib, x/net, go-jose, Alpine libs); 2.11.9 has one left, CVE-2026-78661 (golang.org/x/net v0.60.0, HTTP/2 DoS, fixed in 0.62.0, not yet shipped in a Caddy image). It is ignored in `infra/caddy/.trivyignore` with `exp:2026-12-06` (30 days; CI fails again after that), and the Caddyfile sets `servers { protocols h1 }` so the HTTP/2 path is not exposed. Remove both when a Caddy with x/net >= 0.62.0 ships.

Final-review round (2026-11-07): the CI-only images `tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0` (`latest`) and `moby/buildkit@sha256:c5f8862f52499773af85bc07695b2379ef08e8002352b0df2c4864c91d78dabe` (`buildx-stable-1`) in `heavy.yml` were pinned by digest on 2026-11-06, so both are under 14 days old; they are kept under this security/tooling exception (digest-pinned, CI only, not shipped). Re-pin to a release older than 14 days when one exists.

B6 ruling R10 (2026-11-07, Task 7 minor M-5): the web image runs `apk upgrade --no-cache zlib musl musl-utils` on top of the pinned `nginx-unprivileged` digest, under the same security exception: zlib CVE-2026-85091 (fixed in 1.3.2-r1) and musl CVE-2026-107891 (fixed in 1.2.6-r3) are fixed in Alpine but not yet in the pinned base. The upgrade pulls the newest Alpine 3.24 packages at build time. Drop the line from `web/Dockerfile` once the base image ships zlib >= 1.3.2-r1 and musl >= 1.2.6-r3.

## GPL tools and system components (D-080, owner-confirmed 2026-11-07)

D-079 keeps GPL/AGPL out of our code's library dependencies (pip, pnpm; checked by `tools/check_licenses.py`). D-080 allows unmodified tools and system components that we only run, never link into our code or distribute, when they are recorded here.

| Item | Licence | Where it runs | Notes |
|---|---|---|---|
| ShellCheck (`koalaman/shellcheck`, v0.10.0, digest-pinned; also inside the actionlint image) | GPL-3.0 | CI only (`lint-scripts`) | Unmodified. |
| QEMU user-mode emulation via `tonistiigi/binfmt` (digest-pinned) | GPL-2.0 | CI only (`multiarch`, heavy workflow) | Unmodified; registers binfmt handlers for arm64 builds. |
| PostGIS 3.5.2 (Debian package in the `infra/postgis` image) | GPL-2.0-or-later | Pilot and dev database server | Unmodified, a separate server process. Also the PROJ, GEOS, GDAL and SFCGAL libraries from Debian. |
| Debian and Alpine OS packages in our images | various (GPL included) | Container base layers | Unmodified distribution packages. |

## B6 backup tooling (Task 5, B6-R06)

| Item | Pinned version | Published | Licence | Notes |
|---|---|---|---|---|
| age / age-keygen | v1.3.2, built from the release source tarball (sha256 `c160d6f9...`) | 2026-08-29 | BSD-3-Clause | R9: built with Go 1.27.3 from the vendored source. |
| rclone | v1.75.2, built from the GitHub source tarball (sha256 `68afd7f6...`) | 2026-10-09 | MIT | R9: Go 1.27.3, `golang.org/x/net` bumped 0.60.0 -> 0.62.0. v1.76.0 is from today. |
| supercronic | v0.2.51 release binary | 2026-10-21 | MIT | amd64/arm64 binaries, sha256 pinned. 16 days old on 2026-11-06. |
| Go toolchain (build stage only) | `golang:1.27.3-trixie`, digest `af1bfc26...` | 2026-11-05 | BSD-3-Clause | R9. Not in the final image. |
| pg_dump / pg_restore | 17.12 | 2026-11-24 | PostgreSQL | From the same `postgres:17.12-trixie` digest as `infra/postgis` (ruling R2). |
| SeaweedFS (CI only) | `chrislusf/seaweedfs:4.48`, digest `4e61d15f...` | 2026-09-28 | Apache-2.0 | R8. S3 stand-in for Oracle Object Storage in the backup test; never deployed. |
| aws-cli (CI only) | `amazon/aws-cli:2.38.4`, digest `de807aa6...` | 2026-10-21 | Apache-2.0 | R8. Sets and reads the bucket lifecycle rule (`put/get-bucket-lifecycle-configuration`) and inspects objects in the test. |

B6 ruling R6 (2026-11-06): the Keycloak realm, users and credentials are backed up by `pg_dump -Fc` of the `keycloak` database, next to the app database, not by `kc.sh export` or the admin partial export. In production Keycloak keeps everything (realm, users, password hashes) in that database, so one dump includes users and credentials; `kc.sh export` needs a stopped Keycloak or a second container, and the admin partial export leaves out credentials. Cost: the two dumps are separate snapshots (taken seconds apart) and a restore needs the same Keycloak major version; both are acceptable at pilot scale. Restores run as the superuser into an empty database whose roles (`nd_owner`, `nd_app`, `keycloak`) were created by the db init scripts from the same `infra/.env.prod`, so owners and grants come back with the dump and RLS policies are part of it. Tested: the restored stack passes the smoke test, `nd_app` without an organization still sees no rows, and a user created in Keycloak after the realm import still logs in.

B6 ruling R7 (2026-11-06): `infra/backup/age-recipients.txt` holds a throwaway placeholder public key whose private key was discarded at creation, marked `NOT-FOR-PRODUCTION-PLACEHOLDER`. `backup.sh` and `restore.sh` refuse to run while the file contains that marker, so a production backup can never be encrypted to a key anybody could hold. The CI test generates its own key pair at test time (`age-keygen` from the backup image) and points `ND_AGE_RECIPIENTS` at it; no private key is committed (gitleaks stays clean), and the test asserts the refusal on the committed file. The runbook step that replaces the file comes in Task 7.

B6 ruling R8 (2026-11-06, controller; replaces the implementer's first R8): the CI S3 stand-in must not be AGPL (D-037, D-079). MinIO and mc are removed. The test runs SeaweedFS (Apache-2.0, `chrislusf/seaweedfs:4.48`, digest-pinned, 39 days old) as the S3 server and the Apache-2.0 `amazon/aws-cli:2.38.4` (digest-pinned) as the client. A spike confirmed that SeaweedFS accepts and returns an Expiration-Days lifecycle configuration through the S3 API; the test sets a 14-day rule with `put-bucket-lifecycle-configuration` and asserts it with `get-bucket-lifecycle-configuration`. rclone (the real client of the backup scripts) talks to SeaweedFS over the same S3 API. This proves only that the S3 API accepts and returns the rule; the real Oracle bucket rule is a runbook step.

B6 ruling R9 (2026-11-06): age and rclone are compiled from pinned, checksummed source in the backup Dockerfile instead of using the upstream release binaries. The release binaries carry fixable Go stdlib CVEs (CVE-2026-111943 crypto/x509 certificate validation, plus net/http and crypto/tls DoS) and rclone's x/net 0.60.0 (CVE-2026-78661); Trivy fails the image on them. The Go toolchain `golang:1.27.3-trixie` (pushed 2026-11-05, under 14 days) is used under the same security exception as R2/R5; `golang.org/x/net` v0.62.0 (published 2026-10-27, 10 days old) is explicitly covered by the same security exception: it is the first x/net release that fixes CVE-2026-78661. The Trivy result of the final image is clean (HIGH and CRITICAL, fixes available) with no ignore file. Cost: rclone and age are no longer byte-identical to upstream releases; the source checksums are pinned, and the build is about one minute. Revert to the release binaries once upstream rebuilds with a fixed Go.
