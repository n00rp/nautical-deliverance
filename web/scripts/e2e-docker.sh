#!/usr/bin/env bash
# B6-R08: runs the E2E purchase flow in the pinned Playwright image against a stack that is already
# up on the host (host networking: the browser must reach web on :8080 and Keycloak on :8081).
# Needs ND_E2E_USER and ND_E2E_PASSWORD (optionally ND_E2E_BASE_URL, ND_E2E_OPERATOR_USER and
# ND_E2E_OPERATOR_PASSWORD, ND_E2E_OPERATOR_NAME). Traces of a failure land in test-results/e2e.
set -euo pipefail
IMAGE="mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f"
cd "$(dirname "$0")/.."
# MSYS_NO_PATHCONV stops Git Bash rewriting the container paths. -e NAME passes the value through.
MSYS_NO_PATHCONV=1 docker run --rm --ipc=host --network host \
  -e ND_E2E_BASE_URL -e ND_E2E_USER -e ND_E2E_PASSWORD -e ND_E2E_OPERATOR_USER -e ND_E2E_OPERATOR_PASSWORD -e ND_E2E_OPERATOR_NAME \
  -v "$PWD:/work" -v /work/node_modules -w /work "$IMAGE" bash -c '
  set -euo pipefail
  npm install --global pnpm@12.15.0 >/dev/null
  pnpm install --frozen-lockfile
  pnpm run test:e2e '"$*"'
'
