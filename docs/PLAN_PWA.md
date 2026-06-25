# PLAN — PWA (installable desktop/mobile app)

Make CityAgent Analytics installable from the browser (own window, dock/home icon, offline
shell, one-click Install button) — the "Add to Home Screen / Installable app" pattern.

Low risk, additive: a Nuxt module + manifest + service worker + one small Install button.
No backend change. Reuses the existing `nuxt generate` static bundle.

## Why this is easy here
- Frontend is already a pure SPA (`nuxt.config.ts` `ssr: false`) → no SSR/PWA conflict.
- Icons exist: `public/assets/logo-mark-512.png` (512) + `logo-mark-128.png`. Need a 192.
- Served by the baked image on `:3007`; prod just needs HTTPS (localhost is exempt for testing).

---

## Phase 1 — add the PWA module

### 1a dependency
- `frontend/package.json`: add `@vite-pwa/nuxt` (yarn add -D @vite-pwa/nuxt). Lazy, build-time only.

### 1b nuxt.config.ts (backup first)
- Add `'@vite-pwa/nuxt'` to `modules`.
- Add a `pwa: {}` block:
  - `registerType: 'autoUpdate'` (new SW activates → app reloads to latest bake).
  - `manifest`:
    - `name: 'CityAgent Analytics'`, `short_name: 'CityAgent'`
    - `description`, `lang: 'en'`
    - `display: 'standalone'` (no browser chrome), `start_url: '/'`, `scope: '/'`
    - `background_color: '#ffffff'`, `theme_color: '#C2683F'` (clay)
    - `icons`: 192 + 512 (+ a 512 `purpose: 'maskable'`)
  - `workbox`:
    - `navigateFallback: '/'` (SPA deep links resolve to the shell)
    - `globPatterns: ['**/*.{js,css,html,png,svg,woff2}']` (precache app shell)
    - **runtimeCaching — CRITICAL:** `/api/**` = `NetworkOnly` (NEVER cache API/auth/data →
      else stale answers + token bugs). Cache only static assets (CacheFirst for `_nuxt/*`,
      images). Be explicit: deny-list `/api`.
  - `client: { installPrompt: true }` (enables the prompt hook).
  - `devOptions: { enabled: false }` (don't run SW in dev — it caches and confuses hot-reload).

---

## Phase 2 — icons + meta

### 2a icons
- Generate `public/pwa-192x192.png` + `pwa-512x512.png` (+ a maskable 512 with padding) from
  `public/assets/logo-mark-512.png` (PIL resize). Point manifest at them.

### 2b iOS / head meta (`app.vue` or `nuxt.config app.head`)
- `apple-touch-icon` (180), `apple-mobile-web-app-capable=yes`,
  `apple-mobile-web-app-status-bar-style`, `theme-color #C2683F`.
- iOS Safari can't auto-prompt → users use Share → Add to Home Screen (document it).

---

## Phase 3 — one-click Install button

### 3a `components/InstallApp.vue` (new)
- Listen for `beforeinstallprompt` (capture event, `e.preventDefault()`, stash it).
- Show a small **Install** button (clay, near the 🔔 bell in `TopNav.vue`, or a dismissible
  banner) ONLY when the event fired AND not already installed
  (`window.matchMedia('(display-mode: standalone)')` false).
- Click → `prompt.prompt()` → await `userChoice` → hide on accept.
- Hide forever after install (`appinstalled` event + localStorage flag).
- **Reality:** browsers forbid silent auto-install — this button = the closest to "automatic"
  (1 click). Chrome/Edge desktop also show a ⊕ in the address bar automatically.

### 3b wire into TopNav (backup)
- Explicit import (Nuxt path-prefix landmine), place left of the bell. Mobile → in the sheet.

---

## Phase 4 — build / deploy / verify
- `yarn generate` now also emits `sw.js` + `manifest.webmanifest` + workbox into `.output/public`.
- `docker cp .output/public/. ca-app:/app/frontend/dist` → `docker commit` (same bake flow).
- **HTTPS in prod is required** for install + SW (set `PUBLIC_URL` to an https origin; behind
  ALB/Caddy/nginx TLS). `http://localhost:3007` works for local install testing (browser exempts
  localhost).
- Verify: Chrome DevTools → Application → Manifest (no errors) + Service Workers (activated) +
  Lighthouse PWA audit ✓; address-bar ⊕ appears; Install → opens standalone window with our icon;
  kill network → app shell still loads (API calls fail gracefully, not the shell).

---

## Risks / landmines
- **API caching = data-staleness/auth bugs** → `/api/**` MUST be `NetworkOnly`. Single biggest trap.
- **Stale app after deploy** → `registerType:'autoUpdate'` + a "new version, reload" toast (optional;
  ties in with the changelog version chip).
- **SW in dev** → keep `devOptions.enabled:false`; a stale dev SW serves old files (hard-refresh /
  unregister to recover).
- **No HTTPS in prod = no install, no SW** (silent). Confirm TLS first.
- **iOS** = manual Add-to-Home-Screen (no programmatic prompt) — expected, document it.

## Build order / fan-out
- Small enough for 1 agent, but cleanly: Agent A = module config + icons + meta (Phase 1-2),
  Agent B = InstallApp.vue (Phase 3a). Parent = wire TopNav + generate + bake + verify.
- No migration, no backend. Backups for `nuxt.config.ts` + `TopNav.vue`.
