#!/usr/bin/env bash
# =============================================================================
# release.sh — build the app image for linux/amd64 and push to private GHCR.
# =============================================================================
# Prereqs (one-time):
#   1. GitHub PAT (classic) with write:packages.
#   2. echo <PAT> | docker login ghcr.io -u raahulgupta07 --password-stdin
#
# Usage:
#   bash scripts/release.sh                 # tag = VERSION_HYBRID + latest
#   bash scripts/release.sh 1.37.1          # explicit tag
#   PLATFORMS=linux/amd64,linux/arm64 bash scripts/release.sh   # multi-arch
#
# Pushes ghcr.io/<OWNER>/<NAME>:<tag> and :latest. The package is born PRIVATE.
# =============================================================================
set -euo pipefail

OWNER="${GHCR_OWNER:-raahulgupta07}"
NAME="${IMAGE_NAME:-cityagent-analytics}"
PLATFORMS="${PLATFORMS:-linux/amd64}"     # users run amd64 servers by default

cd "$(dirname "$0")/.."

TAG="${1:-$(cat VERSION_HYBRID 2>/dev/null | tr -d '[:space:]')}"
if [ -z "$TAG" ]; then
  echo "ERROR: no tag given and VERSION_HYBRID is empty" >&2
  exit 1
fi

IMAGE="ghcr.io/${OWNER}/${NAME}"
echo ">> Building ${IMAGE}:${TAG} (+latest) for ${PLATFORMS} and pushing to GHCR"

# buildx builds + pushes in one shot (no local load needed for a remote target).
# A multi-arch builder is created on first run if the default can't do it.
docker buildx inspect ca-builder >/dev/null 2>&1 || docker buildx create --name ca-builder --use
docker buildx use ca-builder

DOCKER_BUILDKIT=1 docker buildx build \
  --platform "${PLATFORMS}" \
  -t "${IMAGE}:${TAG}" \
  -t "${IMAGE}:latest" \
  --push \
  .

echo ">> Done. Users pull with:"
echo "   docker pull ${IMAGE}:${TAG}"
