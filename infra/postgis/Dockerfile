# syntax=docker/dockerfile:1
# Own multi-arch (amd64 + arm64) PostgreSQL 17 + PostGIS 3.5 image (B6-R02). The stock postgis/postgis
# image is amd64-only; the Oracle ARM VM needs arm64. Base: official postgres 17.12 (trixie), pinned
# by its multi-arch index digest. R14: security beats the 14-day rule; 17.11 carries fixable
# PostgreSQL (17.12 security release), krb5 and zlib CVEs that 17.12 (Debian 13.8) has fixed.
# zstd: CVE-2026-124851 fixed in 1.5.7+dfsg-1+deb13u1; drop the upgrade once the base ships it.
FROM postgres:17.12-trixie@sha256:87c8b42f423b45d5247e6aa8fdb2e7762fec164c68a50fe3eb07e7bfcaf4dbcf
# PostGIS 3.5.2 is the newest 3.5 build: PGDG (already configured in the base) only carries 3.6+ for
# trixie, Debian main carries 3.5.2. Everything PostGIS links against (GEOS, PROJ, GDAL, SFCGAL) comes
# from Debian main too, matching what 3.5.2 was built against: the preferences file blocks PGDG's newer
# geo builds (which would mix GDAL 3.10 with gdal-data 3.13 and GEOS 3.15 under a 3.13-built PostGIS),
# and every geo package is pinned to an exact version so a rebuild cannot drift. The -scripts package
# is pinned as well (unpinned it would come from PGDG as 3.7 and refuse the 3.5 library).
# gosu is a Go binary built with go1.24.6: Trivy reports fixable stdlib CVEs and the base has no newer
# gosu. The entrypoint only uses it to drop root, so it is deleted here and replaced below by a setpriv
# wrapper (util-linux) in a separate layer: Trivy keeps reporting a Go binary that a later layer
# overwrites instead of deleting. The wrapper supports only the plain user-name form that the base
# entrypoint uses (`gosu postgres cmd...`), not `user:group` or numeric ids.
RUN printf '%s\n' 'Package: libgeos* libproj* proj-data gdal-* libgdal* libsfcgal*' \
        'Pin: origin apt.postgresql.org' 'Pin-Priority: -1' > /etc/apt/preferences.d/geo \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-17-postgis-3=3.5.2+dfsg-1 postgresql-17-postgis-3-scripts=3.5.2+dfsg-1 \
        libgeos-c1t64=3.13.1-1 libgeos3.13.1=3.13.1-1 libproj25=9.6.0-1 proj-data=9.6.0-1 \
        libgdal36=3.10.3+dfsg-1 gdal-data=3.10.3+dfsg-1 gdal-plugins=3.10.3+dfsg-1 libsfcgal2=2.0.0-1 \
    && apt-get install -y --only-upgrade --no-install-recommends zstd libzstd1 \
    && rm -rf /var/lib/apt/lists/* /usr/local/bin/gosu
RUN printf '%s\n' '#!/bin/sh' \
        'u=$1; shift' \
        'exec env HOME="$(getent passwd "$u" | cut -d: -f6)" setpriv --reuid="$u" --regid="$u" --init-groups "$@"' \
        > /usr/local/bin/gosu \
    && chmod 0755 /usr/local/bin/gosu
