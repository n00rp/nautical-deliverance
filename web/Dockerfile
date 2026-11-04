# syntax=docker/dockerfile:1
FROM node:24.22.0-alpine@sha256:44fce696f38ba8c987c4db89954051000bbd05ffd8d8659ba15ed4a8602e937f AS build
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

FROM nginxinc/nginx-unprivileged:1.31.7-alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e
# Static serving needs none of the image-filter/curl stack; removing it drops its vulnerable libs.
USER root
RUN apk del --no-cache curl libcurl freetype fontconfig brotli-libs libexpat
USER 101
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
