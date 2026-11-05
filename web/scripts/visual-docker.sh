#!/usr/bin/env bash
# Runs the visual suite in the pinned Playwright image (baselines are Linux-only).
# Usage: bash scripts/visual-docker.sh [--update-snapshots]
set -euo pipefail
IMAGE="mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f"
cd "$(dirname "$0")/.."
# MSYS_NO_PATHCONV stops Git Bash rewriting the container paths.
MSYS_NO_PATHCONV=1 docker run --rm --ipc=host -v "$PWD:/work" -v /work/node_modules -w /work "$IMAGE" bash -c '
  set -euo pipefail
  npm install --global pnpm@12.15.0 >/dev/null
  # /work/node_modules is an anonymous volume: the Windows host install is never touched.
  pnpm install --frozen-lockfile
  pnpm run build-storybook
  pnpm exec playwright test '"$*"'
'
