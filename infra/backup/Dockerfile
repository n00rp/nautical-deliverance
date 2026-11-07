# syntax=docker/dockerfile:1
# Backup image (B6-R06): pg_dump/pg_restore 17 (same pinned base as infra/postgis, so the client
# matches the server), age, rclone and supercronic. Licences: PostgreSQL, BSD-3-Clause, MIT, MIT.
# Multi-arch: TARGETARCH selects the amd64 or arm64 build.
#
# age and rclone are built from their pinned, checksummed source with Go 1.27.3 (ruling R9, security
# exception like R2/R5): the upstream release binaries are built with Go 1.26.9/1.27.0 and Trivy
# reports fixable stdlib CVEs in them (crypto/x509 certificate validation, net/http, crypto/tls);
# rclone additionally carries golang.org/x/net 0.60.0 (CVE-2026-78661), bumped here to 0.62.0.
# The build runs on the build platform and cross-compiles (no QEMU). supercronic's release binary
# is clean in Trivy and is used as published, with its sha256 pinned.
FROM --platform=$BUILDPLATFORM golang:1.27.3-trixie@sha256:af1bfc2614ebb1dbd31af514b78740fd678850e76498762b425ecee4c5c6ea80 AS gobuild
ARG TARGETARCH
ARG AGE_VERSION=1.3.2
ARG AGE_SRC_SHA256=c160d6f907992561413a28818f7d7585b35977cdbc449f3e96c4f8c99d22d21e
ARG RCLONE_VERSION=1.75.2
ARG RCLONE_SRC_SHA256=68afd7f68c84bd978966feae2116339aa7bf454b39c573910c462e87c3774d5a
ENV CGO_ENABLED=0 GOARCH=$TARGETARCH GOFLAGS=-trimpath
WORKDIR /src
RUN curl -fsSLo age.tgz "https://github.com/FiloSottile/age/releases/download/v$AGE_VERSION/age-v$AGE_VERSION-source.tar.gz" \
    && echo "$AGE_SRC_SHA256  age.tgz" | sha256sum -c - \
    && tar -xzf age.tgz \
    && cd age \
    && go build -mod=vendor -ldflags "-s -w -X main.Version=v$AGE_VERSION" -o /out/ ./cmd/age ./cmd/age-keygen
RUN curl -fsSLo rclone.tgz "https://github.com/rclone/rclone/archive/refs/tags/v$RCLONE_VERSION.tar.gz" \
    && echo "$RCLONE_SRC_SHA256  rclone.tgz" | sha256sum -c - \
    && tar -xzf rclone.tgz \
    && cd "rclone-$RCLONE_VERSION" \
    && go get golang.org/x/net@v0.62.0 \
    && go build -ldflags "-s -w -X github.com/rclone/rclone/fs.Version=v$RCLONE_VERSION" -o /out/rclone .

FROM --platform=$BUILDPLATFORM postgres:17.11-trixie@sha256:748a18a54d3842d43bc156f0840d78029b8d349e0feca98c12b9c4ce3404a6b3 AS fetch
ARG TARGETARCH
ARG SUPERCRONIC_VERSION=0.2.51
ARG SUPERCRONIC_SHA256_AMD64=cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123
ARG SUPERCRONIC_SHA256_ARM64=4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) SHA=$SUPERCRONIC_SHA256_AMD64 ;; \
      arm64) SHA=$SUPERCRONIC_SHA256_ARM64 ;; \
      *) echo "unsupported $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /usr/local/bin/supercronic "https://github.com/aptible/supercronic/releases/download/v$SUPERCRONIC_VERSION/supercronic-linux-$TARGETARCH"; \
    echo "$SHA  /usr/local/bin/supercronic" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/supercronic

FROM postgres:17.11-trixie@sha256:748a18a54d3842d43bc156f0840d78029b8d349e0feca98c12b9c4ce3404a6b3
# gosu is a Go binary with fixable stdlib CVEs and this image never needs it (no entrypoint switch).
RUN rm -f /usr/local/bin/gosu
COPY --from=gobuild /out/age /out/age-keygen /out/rclone /usr/local/bin/
COPY --from=fetch /usr/local/bin/supercronic /usr/local/bin/
COPY --chmod=0755 common.sh backup.sh restore.sh check_fresh.sh /usr/local/bin/
COPY crontab age-recipients.txt /etc/nd-backup/
ENV TZ=UTC
USER postgres
ENTRYPOINT []
CMD ["supercronic", "/etc/nd-backup/crontab"]
