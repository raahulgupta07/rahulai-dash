# PLAN — Faster Rebuilds, Keep All Features  ✅ DONE (2026-06-19)

> **⚠️ SUPERSEDED by v1.11.0 (2026-06-25):** the external `cityagent-base:dev` image described
> below is now folded INTO the main `Dockerfile` as an internal `AS base` stage, so a clean machine
> can `docker compose up -d --build` with no pre-step (fixes "cityagent-base:dev pull access denied"
> on fresh prod boxes). `Dockerfile.base` + `scripts/build.sh` are kept only as an optional fast-dev
> path. See README "Deploy (one command)" + `deploy.sh`. The plan below is the historical record of
> the original split-base refactor.

## RESULTS (verified live)
- Baseline: app image 6.42GB, full build ~20min (~1200s).
- After refactor: `cityagent-base:dev` 1.31GB (built once) + app `cityagent-analytics:dev` 6.33GB.
- **Fast-rebuild proof: backend `.py` change → `bash scripts/build.sh` = 40.9s** (~29× faster, 0 dep re-download; mostly image export/unpack).
- B5 verify (3 parallel sub-agents):
  - render: chromium headless ✅, Impress→PDF ✅, poppler ✅ (Writer/Calc absent = same as original, not a regression).
  - skills baked: 5/5 ✅ (alembic head `sk3skillfiles1` survived recreate, 6 cols + skill_files, S1-S5 grep in image, e2e smoke 7/0/1, import 457 routes).
  - deps/vendored: 8/8 ✅ (qvd2parquet runs, msodbcsql18 registered on arm64, tiktoken loads offline, vendored JS libs incl babel 7.x, RDS cert).
- Phase 1B (durable bake) achieved by this build: S1-S5 baked into image, deployed via force-recreate, DB volume persisted.
- `Dockerfile.orig` retained for rollback.

---


Branch `hybrid-brain`. Goal: code-change rebuild from ~20min (re-downloads
everything) → seconds–2min, **zero feature loss**, resilient to `registry EOF`.
Strategy: heavy stable stuff → **base image**; language deps → **BuildKit cache
mounts**; tiny assets → **vendored in git**; fix **cache ordering**.
User intent (2026-06-19): keep all features (PDF/slides/QlikView/SQL Server),
build/install from local instead of re-downloading every build.

## Constraints (CLAUDE.md)
Own image only (RULE 1), pre-pull bases (RULE 2), minimal core touch (RULE 3).
Keep original `Dockerfile` as `Dockerfile.orig` for rollback.

## Root cause (current Dockerfile)
- Source copied BEFORE deps install: `COPY ./backend` (L22) → `pip install` (L31);
  `COPY ./frontend` (L75) → `yarn install` (L85). Any code edit busts the dep layer
  → full reinstall/redownload.
- No BuildKit cache mounts → pip/yarn/cargo/apt re-download on every clean build.
- Heavy runtime apt (LibreOffice ~450MB, MS ODBC, lines 109-127) + Playwright
  chromium (L38/L147/L150) reinstall on most builds.

## What is downloaded today (all features kept — none removed)
| item | Dockerfile | source | keep via |
|---|---|---|---|
| pip (213 pkgs) | L31 | PyPI | cache mount + manifest-order |
| yarn deps | L85 | npm | cache mount + manifest-order |
| Playwright chromium | L38 `--with-deps` | playwright CDN | **base image** |
| LibreOffice+poppler | L125 | apt | **base image** |
| MS ODBC 17/18 | L112-123 | MS apt repo | **base image** |
| rust crates (qvd) | L40-51 | crates.io | cache mount (opt: `cargo vendor`) |
| vendor JS libs | L89 | CDN curl | **commit to repo** |
| tiktoken encodings | L34 | openai | **commit to repo** |
| RDS CA pem | L169 | aws | **commit to repo** |

## Phases
- **B0 Baseline** — time current full build + record image size (so speedup is provable). No change.
- **B1 Runtime base image** — `Dockerfile.base` → `cityagent-base:dev`: ubuntu24.04 +
  runtime apt (curl, ca-certs, python3/venv, tini, libpq5, openssh, git, vim-tiny) +
  **MS ODBC 17+18 + unixodbc/tds** + **LibreOffice-impress + poppler** + **Playwright
  chromium browser + system deps** + RDS CA cert. Built ONCE (~15-20min), cached.
  Rebuilds only when system deps change.
- **B2 Refactor app Dockerfile** —
  - Final stage `FROM cityagent-base:dev`; delete moved apt/odbc/libreoffice/playwright
    blocks (≈ L109-127, 147, 150, 167-170). Final stage becomes mostly COPY = fast.
  - Cache-order fix: backend `COPY requirements_versioned.txt` → pip → then `COPY ./backend`;
    frontend `COPY package.json yarn.lock` → yarn install → then `COPY ./frontend`.
  - BuildKit cache mounts on pip, yarn, cargo (`RUN --mount=type=cache,...`).
  - Keep multi-stage incl. rust qvd stage (QlikView kept).
- **B3 Vendor tiny assets into git** — `vendor/js-libs/` (tailwind/react/react-dom/babel/echarts,
  ~few MB) → COPY into `public/libs`, drop curl; `vendor/certs/rds-combined-ca-bundle.pem`
  → COPY; `vendor/tiktoken/` (cl100k/o200k ~3MB) → COPY + `TIKTOKEN_CACHE_DIR`. (Big binaries
  NOT committed — base image + cache mounts handle them.)
- **B4 Wire composes + flow + docs** — `scripts/build.sh` (build base if missing w/ pre-pull
  retry, then compose build app); document base dependency in 3 composes; update CLAUDE.md
  build section + pre-pull list (cityagent-base instead of raw bases).
- **B5 Verify** — build base once → app cold build (record time). Edit a `.py` → rebuild
  (expect no pip, seconds). Edit a `.vue` → rebuild (expect no yarn install, only `yarn generate`).
  Boot + `/health`. **Feature smoke (proves no loss):** PDF export (playwright), slide artifact
  (libreoffice), chinook demo query (core), confirm `qvd2parquet` binary + odbc drivers present.
  Record final image size + build times here.

## Expected outcome
| | now | after |
|---|---|---|
| code-edit rebuild | ~20min, full re-download | seconds–2min, 0 dep network |
| features | all | all kept |
| registry-EOF flake | every build | base-only, once |
| git growth | — | ~5-8MB (JS+cert+tiktoken) |

## Optional — full airgap (only if hard requirement)
Commit big artifacts too: `cargo vendor` (tools/qvd2parquet/vendor + `.cargo/config.toml`
offline), yarn offline-mirror, pip wheelhouse (`pip download` → `--no-index --find-links`).
100s of MB git bloat — do only if offline builds are mandatory.

## Rollback
`Dockerfile.orig` retained → swap back + rebuild.
