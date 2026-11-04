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

FROM nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
