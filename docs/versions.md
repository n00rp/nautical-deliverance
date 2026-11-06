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
| PostGIS | own image `infra/postgis` on `postgres:17.11-trixie` (index digest `748a18a5...`), `postgresql-17-postgis-3` + `-scripts` 3.5.2+dfsg-1 | 2026-11-05 (base), 2026-02 (PostGIS) | Multi-arch (amd64 + arm64), B6-R02. Base is < 14 days old by R14 (17.10 has 17 fixable PostgreSQL CVEs). PGDG only has 3.6+ for trixie; 3.5.2 comes from Debian main. gosu (Go 1.24.6 stdlib CVEs) is replaced by a setpriv wrapper. Trivy clean. GEOS 3.13.1, PROJ 9.6.0, GDAL 3.10.3, SFCGAL 2.0.0 all from Debian main, pinned exactly, PGDG geo builds blocked. |
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

B6 ruling R2 (2026-11-06): the PostGIS image base `postgres:17.11-trixie` (pushed 2026-11-05, under 14 days) is kept, following S0 ruling R14 (security beats the 14-day rule). `17.10` has 17 CVEs fixed in 17.11 (PostgreSQL 17.11 security release) and runs on Debian 13.6, whose OS packages 13.7 has already fixed; staying on 17.10 would need unpinned PGDG upgrades over a pinned digest. Digest-pinned (index `748a18a5...`).

B6 ruling R5 (2026-11-06): the Caddy edge image `caddy:2.11.9-alpine` (pushed 2026-11-05, under 14 days; digest `0bbb055b...`) is kept, extending the R2 security exception. The older tags 2.11.6 and 2.11.7 carry 10-13 fixable HIGH/CRITICAL findings (Go stdlib, x/net, go-jose, Alpine libs); 2.11.9 has one left, CVE-2026-78661 (golang.org/x/net v0.60.0, HTTP/2 DoS, fixed in 0.62.0, not yet shipped in a Caddy image). It is ignored in `infra/caddy/.trivyignore` with `exp:2026-12-06` (30 days; CI fails again after that), and the Caddyfile sets `servers { protocols h1 }` so the HTTP/2 path is not exposed. Remove both when a Caddy with x/net >= 0.62.0 ships.
