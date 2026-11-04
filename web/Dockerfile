# syntax=docker/dockerfile:1
FROM node:26.12.0-alpine@sha256:6f08a523443ddedf52941874c203475b0ad503e859ad70cb26ab8be9a517dbd5 AS build
RUN npm install --global pnpm@12.15.0
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# Same-origin API (nginx proxies /api/) and the browser-facing Keycloak issuer.
ARG VITE_API_BASE_URL=""
ARG VITE_OIDC_AUTHORITY=http://localhost:8081/realms/nautical-deliverance
ARG VITE_OIDC_CLIENT_ID=nd-web
RUN pnpm build

FROM nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
# Static serving needs none of the image-filter/curl stack; removing it drops its vulnerable libs.
USER root
RUN apk del --no-cache curl libcurl freetype fontconfig brotli-libs libexpat
USER 101
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
