# syntax=docker/dockerfile:1
# The build stage runs on the build host (dist/ does not depend on the CPU), so a multi-arch build
# emulates only the nginx runtime stage under QEMU.
FROM --platform=$BUILDPLATFORM node:26.13.0-alpine@sha256:8996bb5821d62a8fd9bb27c1cb07462f3fdce6e47d640c6a881ead0b064ce216 AS build
RUN npm install --global pnpm@12.15.0
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# Same-origin API (nginx proxies /api/) and the browser-facing Keycloak issuer.
ARG VITE_API_BASE_URL=""
ARG VITE_OIDC_AUTHORITY=http://localhost:8081/realms/nautical-deliverance
ARG VITE_OIDC_CLIENT_ID=nd-web
RUN pnpm build

FROM nginxinc/nginx-unprivileged:1.31.7-alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e
# Static serving needs none of the image-filter/curl stack; removing it drops its vulnerable libs.
USER root
RUN apk del --no-cache curl libcurl freetype fontconfig brotli-libs libexpat \
 && apk upgrade --no-cache zlib musl musl-utils libxml2 libxslt  # zlib CVE-2026-85091 (1.3.2-r1), musl CVE-2026-107891 (1.2.6-r3), libxml2 CVE-2026-86144 (2.13.9-r3), libxslt CVE-2026-125350 and others (1.1.43-r4); drop once the base image ships them
USER 101
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
