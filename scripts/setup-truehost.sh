#!/usr/bin/env bash
# One-time bootstrap for a fresh Truehost Cloud VPS (this project uses
# truehost.co.za's Cloud VPS 2: 2 vCPU / 4 GB / 100 GB SSD / 10 TB, paid
# by card via Stripe — NOT the Kenya-market KVM1/KVM2 M-Pesa plans an
# earlier version of this comment assumed). Run this once, logged in as
# root, after the VPS is provisioned and you've pointed DNS at it. See
# docs/tweakhub-master-plan.md for account setup (plan choice, payment),
# which happens on truehost.co.za, not here. Note: truehost.co.za's own
# site states it has no physical servers inside South Africa (Europe/USA
# data centers) — factor that into latency expectations.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/yourusername/tweakhub.git}"
APP_DIR="/var/www/tweakhub"
DOMAIN="${DOMAIN:-tweakhub.co.za}"

# Suppresses two interactive prompts that otherwise stop this script cold
# on a fresh VPS image: (1) debconf's "a config file you modified has a
# newer version available" dialog -- DEBIAN_FRONTEND=noninteractive plus
# --force-confold tells it to always keep the file already on disk rather
# than asking, which matters here because it's *sshd_config* that
# triggers it on Truehost's images, and silently overwriting a VPS
# provider's baked-in SSH hardening would be a worse default than a
# script pause; (2) needrestart's "which services should be restarted"
# checklist after apt upgrades their libraries -- mode "a" (automatic)
# just restarts all of them non-interactively instead of asking, which is
# safe here since this is a fresh box with nothing else running yet.
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

echo "==> Updating system packages"
apt update && apt -o Dpkg::Options::="--force-confold" upgrade -y

echo "==> Installing Docker, Docker Compose, nginx, git, certbot"
# NOT the "docker.io" + "docker-compose-plugin" packages from Ubuntu's
# own repos -- docker-compose-plugin doesn't exist there on 22.04 at all
# ("E: Unable to locate package"), only in Docker's own apt repo, added
# below. Using Docker's official repo end-to-end (not mixing docker.io
# with Docker's own compose plugin) avoids the two packages disagreeing
# about the containerd/runc versions underneath them.
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin nginx git certbot python3-certbot-nginx
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
echo "     (POSTGRES_PASSWORD, DPO_COMPANY_TOKEN, JWT_SECRET, etc. -- .env.example's own"
echo "     comments document each one and where its value comes from)"
echo "  2. cd ${APP_DIR}/infrastructure/docker && docker compose --env-file ../../.env.production up -d --build"
echo "  3. Point ${DOMAIN} and www.${DOMAIN} A records at this server's IP"
echo "  4. Once DNS resolves: certbot --nginx -d ${DOMAIN} -d www.${DOMAIN}"
echo "  5. Add TRUEHOST_HOST / TRUEHOST_USERNAME / TRUEHOST_PASSWORD / TRUEHOST_PORT"
echo "     as GitHub Actions secrets so .github/workflows/deploy.yml can redeploy on push"
