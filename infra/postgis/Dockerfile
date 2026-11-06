# syntax=docker/dockerfile:1
# Own multi-arch (amd64 + arm64) PostgreSQL 17 + PostGIS 3.5 image (B6-R02). The stock postgis/postgis
# image is amd64-only; the Oracle ARM VM needs arm64. Base: official postgres 17.11 (trixie), pinned
# by its multi-arch index digest. R14: security beats the 14-day rule; 17.10 carries 17 fixable
# PostgreSQL CVEs plus Debian 13.6 findings that 17.11 (Debian 13.7) has already fixed.
FROM postgres:17.11-trixie@sha256:748a18a54d3842d43bc156f0840d78029b8d349e0feca98c12b9c4ce3404a6b3
# PostGIS 3.5.2 is the newest 3.5 build: PGDG (already configured in the base) only carries 3.6+ for
# trixie, Debian main carries 3.5.2, so apt resolves it from there. Exact pins on the library and the scripts
# package (unpinned, the scripts would come from PGDG as 3.7 and refuse the 3.5 library).
# gosu is a Go binary built with go1.24.6: Trivy reports fixable stdlib CVEs and the base has no newer
# gosu. The entrypoint only uses it to drop root, so it is deleted here and replaced below by a setpriv
# wrapper (util-linux) in a separate layer: Trivy keeps reporting a Go binary that a later layer
# overwrites instead of deleting.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3=3.5.2+dfsg-1 \
        postgresql-17-postgis-3-scripts=3.5.2+dfsg-1 \
    && rm -rf /var/lib/apt/lists/* /usr/local/bin/gosu
RUN printf '%s\n' '#!/bin/sh' \
        'u=$1; shift' \
        'exec env HOME="$(getent passwd "$u" | cut -d: -f6)" setpriv --reuid="$u" --regid="$u" --init-groups "$@"' \
        > /usr/local/bin/gosu \
    && chmod 0755 /usr/local/bin/gosu
