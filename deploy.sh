#!/usr/bin/env bash
# =============================================================================
# CityAgent Analytics — one-command deploy
# =============================================================================
# Friendly, foolproof deploy for a clean machine. No pre-step, no external
# image: the runtime base is folded into the Dockerfile, so this just runs
# `docker compose up -d --build` after a couple of safety checks.
#
# Usage:
#   bash deploy.sh
#
# NOTE: make it executable once so you can run `./deploy.sh` directly:
#   chmod +x deploy.sh
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "============================================================"
echo "  CityAgent Analytics — deploy"
echo "============================================================"

# --- 1. Docker present & running -------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed."
  echo "       Install Docker Desktop / Engine: https://docs.docker.com/get-docker/"
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is installed but not running."
  echo "       Start Docker Desktop (or 'sudo systemctl start docker') and re-run."
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' (v2) is not available."
  echo "       Update Docker Desktop, or install the compose plugin."
  exit 1
fi

# --- 2. .env bootstrap ------------------------------------------------------
if [ ! -f .env ]; then
  if [ ! -f .env.example ]; then
    echo "ERROR: no .env and no .env.example to copy from. Cannot continue."
    exit 1
  fi
  cp .env.example .env
  echo
  echo "Created .env — edit it (set DASH_ENCRYPTION_KEY, DASH_ADMIN_EMAIL,"
  echo "DASH_ADMIN_PASSWORD) then re-run."
  echo
  echo "  Generate an encryption key with:"
  echo "    python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
  echo
  exit 0
fi

# --- 3. Warn (don't fail) on empty encryption key ---------------------------
ENC_KEY_LINE="$(grep -E '^[[:space:]]*DASH_ENCRYPTION_KEY[[:space:]]*=' .env || true)"
ENC_KEY_VAL="${ENC_KEY_LINE#*=}"
ENC_KEY_VAL="$(printf '%s' "$ENC_KEY_VAL" | tr -d '[:space:]')"
if [ -z "$ENC_KEY_VAL" ]; then
  echo
  echo "WARNING: DASH_ENCRYPTION_KEY is empty in .env."
  echo "         Stored credentials cannot be encrypted until you set it."
  echo "         Generate one with:"
  echo "           python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
  echo "         (continuing anyway)"
  echo
fi

# --- 4. Build + start -------------------------------------------------------
echo "Building and starting (this can take ~5-20 min on the FIRST run while the"
echo "runtime base + frontend compile; later rebuilds are seconds-to-minutes)..."
echo
docker compose up -d --build

# --- 5. Report where it lives ----------------------------------------------
echo
echo "============================================================"
echo "  Up. Service status:"
echo "============================================================"
docker compose ps

# Show the published host port(s). The default docker-compose.yaml fronts the
# app with Caddy on 80/443; the build compose publishes the app on 3007.
PUBLISHED="$(docker compose ps --format '{{.Service}} -> {{.Publishers}}' 2>/dev/null || true)"
echo
if [ -n "$PUBLISHED" ]; then
  echo "Published ports:"
  echo "$PUBLISHED"
fi
echo
echo "Open the app:"
echo "  - default (this compose, Caddy):  http://localhost  (and https://<your DOMAIN>)"
echo "  - if you used docker-compose.build.yaml:  http://localhost:3007"
echo
echo "First sign-in: the DASH_ADMIN_EMAIL / DASH_ADMIN_PASSWORD from .env become"
echo "the first owner automatically. Then set your OpenRouter key in"
echo "Settings -> Models."
echo "============================================================"
