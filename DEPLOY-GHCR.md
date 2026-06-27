# Deploy CityAgent Analytics — pull a prebuilt image (no build)

**Goal:** stop building from source on every machine. You (owner) build the image **once** and
push it to GitHub Container Registry (GHCR). Anyone deploying just `docker pull`s it — like
OpenWebUI. No repo clone, no `npm`/`yarn`, no 20-minute compile, no arch-mismatch.

This guide uses a **PUBLIC** package first (simplest — zero login on the install side). Switch to
private later if you want access control (see the last section).

```
Build path (old, slow)                 Pull path (this guide)
──────────────────────                 ──────────────────────
clone repo                             download 2 files
docker compose up --build   ─────►     docker compose pull
  → npm/yarn/nuxt compile                docker compose up -d
  → 5–20 min, flaky                      → seconds
```

You need **2 files** on the server, nothing else:
- `docker-compose.ghcr.yaml`
- `.env`

---

## PART A — Owner: build & publish the image (one time, then per release)

Run on your dev machine (where the repo lives). The image is built for **linux/amd64** (EC2's arch).

### 1. Make a GitHub token (PAT, classic) with `write:packages`
GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)** →
Generate new token → check **`write:packages`** (and `read:packages`) → copy it.

> "Password" for GHCR is **always this token**, never your GitHub account password.

### 2. Log in to GHCR
```bash
echo <YOUR_WRITE_PAT> | docker login ghcr.io -u raahulgupta07 --password-stdin
```

### 3. Build + push
```bash
cd "/Users/rahulgupta/Desktop/CityAI-Final-Project/CityAgent/CityAgent-Data/CityAgent Analytics"
bash scripts/release.sh           # tag = current VERSION_HYBRID + :latest
# or pin a tag:  bash scripts/release.sh 1.39.0
```
Pushes `ghcr.io/raahulgupta07/cityagent-analytics:<version>` and `:latest`. Born **PRIVATE**.

### 4. Make the package PUBLIC (so installers need no login)
GitHub → your profile → **Packages** → `cityagent-analytics` → **Package settings** →
**Danger Zone → Change visibility → Public**.

> Public = the **image/code** is pullable by anyone with the name. It does **NOT** expose your
> database, `.env`, encryption key, or OpenRouter key — those live outside the image.

### 5. Verify the image actually boots (catch errors before your engineer does)
```bash
cd /tmp && mkdir ca-test && cd ca-test
# copy docker-compose.ghcr.yaml + a filled .env here, then:
docker compose -f docker-compose.ghcr.yaml pull
docker compose -f docker-compose.ghcr.yaml up -d
curl localhost:3007/health        # expect ok
docker compose -f docker-compose.ghcr.yaml down   # cleanup
```

**Re-run Part A steps 2–3 every time you ship a new version.** (Visibility stays public; do step 4 once.)

---

## PART B — Engineer: install on AWS EC2 (public image, NO login)

### 1. One-time: install Docker on the EC2 box
```bash
# Amazon Linux 2023
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker $USER        # log out & back in after this

# Ubuntu (alternative)
# curl -fsSL https://get.docker.com | sudo sh
# sudo usermod -aG docker $USER
```
Confirm: `docker compose version` (must be v2).

### 2. One-time: open the port in the EC2 Security Group
AWS console → EC2 → the instance → Security → Security Groups → Inbound rules → **Add rule**:
Custom TCP, port **3007**, source = your office IP (or `0.0.0.0/0` for open — less safe).

### 3. Put the 2 files on the server
Copy `docker-compose.ghcr.yaml` and `.env` into a folder, e.g. `~/cityagent/`.
(SCP, paste, or `curl` them — your choice. No git clone needed.)

### 4. Fill in `.env` (see template below). Generate a real encryption key:
```bash
docker run --rm python:3.12-slim python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Paste the output as `DASH_ENCRYPTION_KEY`. **Keep it stable** — change it and everyone gets logged out.

### 5. Pull & start
```bash
cd ~/cityagent
docker compose -f docker-compose.ghcr.yaml pull
docker compose -f docker-compose.ghcr.yaml up -d
curl localhost:3007/health          # expect ok
```

### 6. Open the app
`http://<EC2-public-IP>:3007`
Log in with `DASH_ADMIN_EMAIL` / `DASH_ADMIN_PASSWORD` from `.env`.
Then set the OpenRouter API key in **Settings → Models**.

That's the whole install. No build, ever.

---

## `.env` template (minimum)

```ini
# --- security (REQUIRED, must stay constant across restarts) ---
DASH_ENCRYPTION_KEY=        # paste output of the Fernet generator (step B4)

# --- first super-admin (auto-created on first boot) ---
DASH_ADMIN_EMAIL=admin@cityagent.io
DASH_ADMIN_PASSWORD=Admin12345
DASH_ADMIN_NAME=Admin

# --- ports / image ---
APP_PORT=3007
APP_IMAGE=ghcr.io/raahulgupta07/cityagent-analytics:latest   # pin :1.39.0 for stability

# --- database (defaults are fine; change password for prod) ---
POSTGRES_USER=dash
POSTGRES_PASSWORD=dashpassword
POSTGRES_DB=dash
POSTGRES_PORT=5439

# OpenRouter key is NOT set here — enter it in the UI: Settings → Models
```

---

## Day-2 operations

**Upgrade to a new version** (after you push a new image):
```bash
docker compose -f docker-compose.ghcr.yaml pull
docker compose -f docker-compose.ghcr.yaml up -d      # recreates app, keeps DB volume
```
DB migrations run automatically on boot (`alembic upgrade head`).

**Logs:**
```bash
docker compose -f docker-compose.ghcr.yaml logs -f app
```

**Restart / stop:**
```bash
docker compose -f docker-compose.ghcr.yaml restart app
docker compose -f docker-compose.ghcr.yaml down       # stop (KEEPS data volumes)
```

**Pin a version instead of `:latest`** — set `APP_IMAGE=ghcr.io/raahulgupta07/cityagent-analytics:1.39.0`
in `.env`. Predictable; no surprise upgrades.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `pull access denied` / `manifest unknown` | Package still **private** (do Part A step 4) or wrong tag — check `APP_IMAGE`. |
| `docker: command not found` | Docker not installed — Part B step 1. |
| App up but browser can't reach it | Security Group port 3007 not open — Part B step 2. Use the EC2 **public** IP. |
| Logged out after every restart | `DASH_ENCRYPTION_KEY` empty or changed — set a stable one. |
| `/health` not ok after boot | First boot runs migrations; wait ~90s. Then check `logs -f app`. |
| Can't log in | Admin only seeded if `DASH_ADMIN_EMAIL`+`DASH_ADMIN_PASSWORD` were set on **first** boot. |

---

## Later: switch to PRIVATE (access control)

When you want only named people to pull:
1. Package settings → Change visibility → **Private**.
2. Manage access → invite each engineer's GitHub username as **Read**.
3. Each engineer makes a `read:packages` PAT and logs in **before** pulling:
   ```bash
   echo <THEIR_READ_PAT> | docker login ghcr.io -u <their_github_user> --password-stdin
   ```
   Then Part B steps 3–6 are unchanged.

For more than ~3 people, make a free **GitHub Org**, move the package there, and grant a **team**
Read once instead of inviting individuals.
