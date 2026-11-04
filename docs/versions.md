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
| PostGIS | `postgis/postgis:17-3.5` | 2026-08-31 | PostgreSQL 17 + PostGIS 3.5. `18-3.6` exists but was pushed 2026-10-26 (< 14 days); revisit later. |
| Keycloak | `quay.io/keycloak/keycloak:26.8.0` | 2026-10-10 | 26.8.1 tags pushed 2026-10-13 / 2026-10-31 (too recent). |
| Node (LTS "Krypton", v24) | `node:24.22.0-alpine` | 2026-10-14 | Node 24.22.0 released 2026-10-14. Node 26 became LTS 2026-10-28 (too recent). |
| nginx | `nginxinc/nginx-unprivileged:1.30.6-alpine` | 2026-10-19 | Stable 1.30 branch. |
| Python image | `python:3.14.8-slim-trixie` | 2026-10-21 | Debian 13 (trixie). 3.14.9 pushed 2026-10-24 (too recent). |
| pnpm | `12.15.0` | 2026-10-21 | From registry.npmjs.org publish time. |
