#!/usr/bin/env bash
# Manual deploy helper — mirrors what .github/workflows/deploy.yml runs
# over SSH. Useful for the first deploy, or a manual redeploy without
# waiting on CI. Run this ON the Truehost VPS, from /var/www/tweakhub.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Pulling latest main"
git fetch origin main
git reset --hard origin/main

echo "==> Rebuilding and restarting containers"
cd infrastructure/docker
docker compose --env-file ../../.env.production build
docker compose --env-file ../../.env.production up -d

echo "==> Status"
docker compose ps
