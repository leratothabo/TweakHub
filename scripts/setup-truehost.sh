#!/usr/bin/env bash
# One-time bootstrap for a fresh Truehost KVM1/KVM2 VPS. Run this once,
# logged in as root, after the VPS is provisioned and you've pointed DNS
# at it. See docs/tweakhub-master-plan.md for account setup (M-Pesa
# billing, plan choice) which happens on truehost.co.ke, not here.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/yourusername/tweakhub.git}"
APP_DIR="/var/www/tweakhub"
DOMAIN="${DOMAIN:-tweakhub.com}"

echo "==> Updating system packages"
apt update && apt upgrade -y

echo "==> Installing Docker, Docker Compose, nginx, git, certbot"
apt install -y docker.io docker-compose-plugin nginx git certbot python3-certbot-nginx
systemctl enable --now docker

echo "==> Cloning repository into ${APP_DIR}"
if [ -d "${APP_DIR}/.git" ]; then
  echo "    already cloned, pulling latest"
  git -C "${APP_DIR}" pull
else
  git clone "${REPO_URL}" "${APP_DIR}"
fi

echo "==> Next steps (manual):"
echo "  1. cp ${APP_DIR}/.env.example ${APP_DIR}/.env.production and fill in real secrets"
echo "     (POSTGRES_PASSWORD, DPO_COMPANY_TOKEN, JWT_SECRET, etc. -- see the launch"
echo "     checklist for the full list and where each value comes from)"
echo "  2. cd ${APP_DIR}/infrastructure/docker && docker compose --env-file ../../.env.production up -d --build"
echo "  3. Point ${DOMAIN} and www.${DOMAIN} A records at this server's IP"
echo "  4. Once DNS resolves: certbot --nginx -d ${DOMAIN} -d www.${DOMAIN}"
echo "  5. Add TRUEHOST_HOST / TRUEHOST_USERNAME / TRUEHOST_PASSWORD / TRUEHOST_PORT"
echo "     as GitHub Actions secrets so .github/workflows/deploy.yml can redeploy on push"
