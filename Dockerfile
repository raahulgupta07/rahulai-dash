# syntax=docker/dockerfile:1.7
FROM ubuntu:24.04 AS backend-builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
      python3-venv \
      python3-dev \
      build-essential \
      libpq-dev \
      gcc \
      unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container for the backend
WORKDIR /app/backend

# Create and use a virtual environment for dependencies
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies first (manifest before source) so this layer only
# rebuilds when requirements change. BuildKit cache mount keeps pip wheels
# across rebuilds.
COPY ./backend/requirements_versioned.txt /app/backend/
RUN --mount=type=cache,target=/root/.cache/pip python3 -m pip install --upgrade pip setuptools wheel && \
    python3 -m pip install --prefer-binary -r requirements_versioned.txt

# Install Playwright browser binary only (system deps are baked into the base image)
RUN playwright install chromium

# Copy the backend source last so source-only changes don't bust the pip layer
COPY ./backend /app/backend
RUN rm -f /app/backend/db/app.db

FROM rust:1-slim-bookworm AS qvd2parquet-builder

WORKDIR /build/qvd2parquet
COPY ./tools/qvd2parquet/Cargo.toml ./tools/qvd2parquet/Cargo.lock ./
# Pre-build dependencies against a stub main so cargo caches the dep graph.
RUN --mount=type=cache,target=/usr/local/cargo/registry mkdir src && echo 'fn main() {}' > src/main.rs && \
    cargo build --release --locked && \
    rm -rf src target/release/qvd2parquet target/release/qvd2parquet.d \
           target/release/deps/qvd2parquet-* 2>/dev/null || true
COPY ./tools/qvd2parquet/src ./src
RUN --mount=type=cache,target=/usr/local/cargo/registry cargo build --release --locked && \
    strip target/release/qvd2parquet

FROM ubuntu:24.04 AS frontend-builder

ENV DEBIAN_FRONTEND=noninteractive

# Install Node.js 22 and prepare environment
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs git && \
    npm install --global yarn@1.22.22 && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container for the frontend
WORKDIR /app

# Copy the VERSION and config file first so they can be used by Nuxt
COPY ./VERSION /app/VERSION
COPY ./dash-config.yaml /app/dash-config.yaml

# Install frontend dependencies first (manifest before source). BuildKit cache
# mount keeps the yarn cache across rebuilds; this layer only rebuilds when
# package.json / yarn.lock change.
COPY ./frontend/package.json ./frontend/yarn.lock /app/frontend/
WORKDIR /app/frontend
RUN --mount=type=cache,target=/usr/local/share/.cache/yarn yarn install --frozen-lockfile

# `frontend/plugins/i18n.ts` imports `../../locales/*.json` at build time,
# so the repo-root `locales/` dir must be present for Rollup to resolve them.
COPY ./locales /app/locales

# Copy the frontend source last so source-only changes don't bust the yarn layer
COPY ./frontend /app/frontend

# Overlay vendored CDN JS libraries for airgapped artifact rendering. These
# replace the old download-vendor-libs.sh network fetch; they merge into
# public/libs alongside artifact-globals.js (which comes from ./frontend).
COPY ./vendor/js-libs/ /app/frontend/public/libs/

# `nuxt generate` produces a fully static SPA under .output/public, which
# FastAPI serves directly in production (see backend/app/core/spa.py).
# This replaces the previous `yarn build` + Node runtime pattern.
# Raise Node heap: the default (~2GB) OOMs (exit 134/SIGABRT) on this build.
RUN NODE_OPTIONS=--max-old-space-size=6144 yarn generate

FROM cityagent-base:dev

ENV DEBIAN_FRONTEND=noninteractive

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Copy Python virtual environment and application code
COPY --from=backend-builder --chown=app:app /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=backend-builder --chown=app:app /app/backend /app/backend

# Streaming QVD → Parquet converter (bounded RAM; replaces in-process qvdrs wheel)
COPY --from=qvd2parquet-builder /build/qvd2parquet/target/release/qvd2parquet /usr/local/bin/qvd2parquet

# Vendored pre-cached tiktoken encodings for airgapped environments
COPY --chown=app:app ./vendor/tiktoken /opt/tiktoken_cache
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache

# Copy Playwright browser binaries from builder
COPY --from=backend-builder --chown=app:app /root/.cache/ms-playwright /home/app/.cache/ms-playwright

# Copy demo data sources (SQLite/DuckDB files for demo databases)
COPY --chown=app:app ./backend/demo-datasources /app/backend/demo-datasources

# Copy the native skill packs (SKILL.md + scripts/) so a fresh install can
# self-seed via `python scripts/import_skill.py /app/skills_library`.
COPY --chown=app:app ./skills_library /app/skills_library

# Copy the desktop Folder Sync agent source so GET /api/sync/download/{os} can
# zip + serve it (HYBRID_FOLDER_SYNC). Without this a fresh build returns 503.
COPY --chown=app:app ./folder-sync-agent /app/folder-sync-agent

# Copy the generated static SPA (nuxt generate output includes all public/
# assets — libs, artifact-sandbox.html, icons, etc. — copied automatically).
COPY --from=frontend-builder --chown=app:app /app/frontend/.output/public /app/frontend/dist

# Keep the legacy public paths available for backend headless browser
# rendering code that reads files from disk (not over HTTP).
COPY --from=frontend-builder --chown=app:app /app/frontend/public/artifact-sandbox.html /app/frontend/public/artifact-sandbox.html
COPY --from=frontend-builder --chown=app:app /app/frontend/public/libs /app/frontend/public/libs

# Copy runtime configs and scripts
COPY --chown=app:app ./backend/requirements_versioned.txt /app/backend/

# Vendored RDS/Aurora CA certificate bundle for IAM auth SSL verification
COPY --chown=app:app ./vendor/certs/rds-combined-ca-bundle.pem /app/certs/rds-combined-ca-bundle.pem

# Create directories that the application needs to write to
# These paths match volume mounts in docker-compose.yaml; they must exist with
# app-user ownership so Docker seeds named volumes with writable perms on first run.
RUN mkdir -p /app/backend/uploads/files /app/backend/uploads/branding \
             /app/backend/branding_uploads /app/backend/logs && \
    chown -R app:app /app

WORKDIR /app

COPY --chown=app:app ./VERSION /app/VERSION
COPY --chown=app:app ./start.sh /app/start.sh
COPY --chown=app:app ./dash-config.yaml /app/dash-config.yaml

# Set executable permissions for start.sh
RUN chmod +x /app/start.sh

ENV ENVIRONMENT=production
ENV GIT_PYTHON_REFRESH=quiet

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8
ENV HOME=/home/app

# Tell FastAPI to serve the generated SPA from disk.
ENV SERVE_FRONTEND=1
ENV FRONTEND_DIST_DIR=/app/frontend/dist

# Expose the uvicorn port (documentational).
EXPOSE 3000

# Healthcheck against /health so failures reflect backend readiness, not
# just the static SPA index (which would always 200 even if uvicorn was wedged).
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:3000/health || exit 1

USER app

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/bin/bash", "start.sh"]
