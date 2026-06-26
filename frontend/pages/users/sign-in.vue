<template>
  <div v-if="pageLoaded" class="cai-root">

    <!-- ============ top brand bar ============ -->
    <header class="cai-header">
      <div style="display:flex; align-items:center; gap:12px;">
        <div style="width:38px; height:38px; border-radius:10px; background:linear-gradient(150deg,#D67037,#A8330F); display:flex; align-items:center; justify-content:center; box-shadow:0 6px 18px -6px rgba(168,51,15,.6);">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="#fff" stroke-width="2" opacity=".55"/><path d="M12 3a9 9 0 0 1 0 18" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="12" r="2.6" fill="#fff"/></svg>
        </div>
        <div style="line-height:1.1;">
          <div style="font-size:16px; font-weight:600; letter-spacing:-.01em;">City Agent <span style="color:#C2541E;">Insights</span></div>
          <div style="font-size:9.5px; letter-spacing:.22em; color:#9A8F80; font-weight:600; margin-top:2px;">DATA INTELLIGENCE</div>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:7px; padding:6px 12px 6px 10px; border:1px solid #E6DCCE; border-radius:999px; background:#FCFAF6; font-size:12px; color:#5C534A;">
        <span style="width:7px; height:7px; border-radius:50%; background:#3FA86B; box-shadow:0 0 0 3px rgba(63,168,107,.18);"></span>
        <span style="font-weight:600;">v{{ hybridVersion }} · {{ envLabel }}</span>
      </div>
    </header>

    <!-- ============ body ============ -->
    <main class="cai-main">

      <!-- LEFT: sign in -->
      <div class="cai-left">
        <section style="max-width:470px; width:100%;">
          <h1 class="cai-h1">
            {{ greeting }},<br>sign in to <span style="font-style:italic; color:#A8330F;">City Agent Insights</span>
          </h1>
          <p style="margin:0 0 22px; font-size:15px; line-height:1.5; color:#6E6356; max-width:390px;">
            Your data intelligence — answered with the source query, every time.
          </p>

          <p v-if="error_message" v-html="error_message" style="margin:0 0 16px; color:#C2410C; font-size:13.5px; white-space:pre-line;"></p>

          <!-- form -->
          <form v-if="showForm" @submit.prevent="signInWithCredentials()" style="display:flex; flex-direction:column; gap:10px;">
            <label class="cai-field" style="display:flex; flex-direction:column; gap:3px; background:#FFFFFF; border:1px solid #E4D9CA; border-radius:12px; padding:9px 15px;">
              <span style="font-size:11px; font-weight:600; letter-spacing:.03em; color:#9A8F80;">EMAIL</span>
              <input id="email" type="email" v-model="email" placeholder="you@company.com" autocomplete="username"
                style="border:none; outline:none; background:transparent; font-family:inherit; font-size:15px; color:#1A1611; padding:1px 0;" />
            </label>

            <label class="cai-field" style="position:relative; display:flex; flex-direction:column; gap:3px; background:#FFFFFF; border:1px solid #E4D9CA; border-radius:12px; padding:9px 15px;">
              <span style="font-size:11px; font-weight:600; letter-spacing:.03em; color:#9A8F80;">PASSWORD</span>
              <input id="password" :type="showPw ? 'text' : 'password'" v-model="password" placeholder="••••••••••" autocomplete="current-password"
                style="border:none; outline:none; background:transparent; font-family:inherit; font-size:15px; color:#1A1611; padding:1px 50px 1px 0;" />
              <button type="button" @click="showPw = !showPw"
                style="position:absolute; right:13px; top:50%; transform:translateY(-50%); border:none; background:#F4EEE5; color:#8A7F70; font-family:inherit; font-size:12px; font-weight:600; padding:5px 11px; border-radius:8px; cursor:pointer;">{{ showPw ? 'Hide' : 'Show' }}</button>
            </label>

            <div style="display:flex; align-items:center; justify-content:space-between; padding:1px 2px 3px;">
              <button type="button" @click="rememberMe = !rememberMe" style="display:flex; align-items:center; gap:9px; border:none; background:none; cursor:pointer; font-family:inherit; padding:0;">
                <span style="width:18px; height:18px; border-radius:6px; display:flex; align-items:center; justify-content:center; transition:.15s;"
                  :style="{ background: rememberMe ? '#C2541E' : '#FFFFFF', border: '1.5px solid ' + (rememberMe ? '#C2541E' : '#CFC4B4') }">
                  <svg v-if="rememberMe" width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2.5 6.2l2.2 2.3L9.5 3.5" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </span>
                <span style="font-size:13.5px; color:#5C534A;">Remember me</span>
              </button>
              <NuxtLink v-if="smtpEnabled" to="/users/forgot-password" class="cai-link" style="font-size:13.5px; color:#8A7F70; text-decoration:none; font-weight:500;">{{ $t('auth.forgotPassword') }}</NuxtLink>
            </div>

            <button type="submit" :disabled="isSubmitting" class="cai-primary"
              style="border:none; background:#1A1611; color:#fff; font-family:inherit; font-size:15px; font-weight:600; padding:14px; border-radius:12px; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:9px; box-shadow:0 10px 24px -12px rgba(26,22,17,.7);">
              <template v-if="isSubmitting"><Spinner class="h-5 w-5" />{{ $t('auth.loggingIn') }}</template>
              <template v-else>
                Continue with email
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 12h13M13 6l6 6-6 6" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </template>
            </button>
          </form>

          <!-- divider (only if at least one provider is enabled) -->
          <div v-if="showProviders" style="display:flex; align-items:center; gap:14px; margin:16px 0 12px;">
            <span style="flex:1; height:1px; background:#E6DCCE;"></span>
            <span style="font-size:11.5px; font-weight:600; letter-spacing:.06em; color:#A89C8C;">OR CONTINUE WITH</span>
            <span style="flex:1; height:1px; background:#E6DCCE;"></span>
          </div>

          <!-- google + microsoft (each shown only when admin-enabled) -->
          <div v-if="showSocial" style="display:grid; gap:10px;" :style="{ gridTemplateColumns: `repeat(${socialCols}, 1fr)` }">
            <button v-if="showGoogle" type="button" @click="signInWithGoogle" :disabled="loadingProvider !== null" class="cai-prov"
              style="display:flex; align-items:center; justify-content:center; gap:10px; background:#FCFAF6; border:1px solid #E4D9CA; border-radius:11px; padding:11px; cursor:pointer; font-family:inherit; font-size:14px; font-weight:600; color:#352F27;">
              <Spinner v-if="loadingProvider === 'google'" class="h-4 w-4" />
              <span v-else style="width:17px;height:17px;display:inline-flex" v-html="idpLogoSvg(googleLogo)"></span>
              Google
            </button>
            <button v-if="showMicrosoft" type="button" @click="onMicrosoft" :disabled="loadingProvider !== null" class="cai-prov"
              style="display:flex; align-items:center; justify-content:center; gap:10px; background:#FCFAF6; border:1px solid #E4D9CA; border-radius:11px; padding:11px; cursor:pointer; font-family:inherit; font-size:14px; font-weight:600; color:#352F27;">
              <Spinner v-if="loadingProvider && /microsoft|azure|entra/i.test(loadingProvider)" class="h-4 w-4" />
              <span v-else style="width:16px;height:16px;display:inline-flex" v-html="idpLogoSvg(msLogo)"></span>
              Microsoft
            </button>
          </div>

          <!-- enterprise (only if SSO / Keycloak / LDAP enabled) -->
          <div v-if="showEnterprise" style="margin-top:12px; padding:12px 14px; background:#FBF7F1; border:1px solid #ECE3D5; border-radius:13px;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:9px;">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-4z" stroke="#A8330F" stroke-width="1.8" stroke-linejoin="round"/><path d="M9 12l2 2 4-4" stroke="#A8330F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              <span style="font-size:11.5px; font-weight:600; letter-spacing:.04em; color:#8A7F70;">ENTERPRISE SIGN-IN</span>
            </div>
            <div style="display:grid; gap:8px;" :style="{ gridTemplateColumns: `repeat(${entCols}, 1fr)` }">
              <button v-if="showSSO" type="button" @click="onSSO" class="cai-ent"
                style="display:flex; flex-direction:column; align-items:center; gap:5px; background:#FFFFFF; border:1px solid #E4D9CA; border-radius:10px; padding:10px 8px; cursor:pointer; font-family:inherit; font-size:12.5px; font-weight:600; color:#4A4239;">
                <span style="width:18px;height:18px;display:inline-flex" v-html="idpLogoSvg(ssoLogo)"></span>
                SSO
              </button>
              <button v-if="showKeycloak" type="button" @click="onKeycloak" class="cai-ent"
                style="display:flex; flex-direction:column; align-items:center; gap:5px; background:#FFFFFF; border:1px solid #E4D9CA; border-radius:10px; padding:10px 8px; cursor:pointer; font-family:inherit; font-size:12.5px; font-weight:600; color:#4A4239;">
                <span style="width:18px;height:18px;display:inline-flex" v-html="idpLogoSvg(keycloakLogo)"></span>
                Keycloak
              </button>
              <button v-if="showLdap" type="button" @click="onLDAP" class="cai-ent"
                style="display:flex; flex-direction:column; align-items:center; gap:5px; background:#FFFFFF; border:1px solid #E4D9CA; border-radius:10px; padding:10px 8px; cursor:pointer; font-family:inherit; font-size:12.5px; font-weight:600; color:#4A4239;">
                <span style="width:18px;height:18px;display:inline-flex" v-html="idpLogoSvg(ldapLogo)"></span>
                LDAP
              </button>
            </div>
          </div>
        </section>
      </div>

      <!-- RIGHT: agent-at-work showcase -->
      <section class="cai-right" style="position:relative; align-self:stretch; min-height:0; border-radius:24px; overflow:hidden; background:radial-gradient(120% 90% at 70% 0%, #2A1F18 0%, #17120E 55%, #100C09 100%); padding:24px; display:flex; flex-direction:column; box-shadow:0 40px 90px -40px rgba(40,24,12,.7), inset 0 1px 0 rgba(255,255,255,.05); border:1px solid rgba(214,112,55,.14);">
        <div style="position:absolute; inset:0; background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px); background-size:36px 36px; mask-image:radial-gradient(120% 80% at 65% 12%, #000 28%, transparent 82%); animation:cai-drift 7s linear infinite; pointer-events:none;"></div>
        <div style="position:absolute; top:-50px; right:-30px; width:260px; height:260px; border-radius:50%; background:radial-gradient(circle, rgba(214,112,55,.42), transparent 65%); filter:blur(22px); animation:cai-orb 7s ease-in-out infinite; pointer-events:none;"></div>
        <div style="position:absolute; bottom:-40px; left:-30px; width:220px; height:220px; border-radius:50%; background:radial-gradient(circle, rgba(168,51,15,.3), transparent 66%); filter:blur(26px); animation:cai-orb2 9s ease-in-out infinite; pointer-events:none;"></div>

        <!-- header -->
        <div style="display:flex; align-items:center; gap:9px; position:relative; flex-shrink:0;">
          <span style="width:8px; height:8px; border-radius:50%; background:#D67037; box-shadow:0 0 12px 2px rgba(214,112,55,.7); animation:cai-pulse 1.8s ease-in-out infinite;"></span>
          <span style="font-size:13px; color:#B8A99A;">{{ statusLine }}</span>
          <span style="margin-left:auto; display:inline-flex; align-items:center; gap:6px; font-size:11.5px; color:#C2854F; background:rgba(214,112,55,.1); border:1px solid rgba(214,112,55,.28); padding:4px 10px; border-radius:999px;">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" style="animation:cai-spin 2.4s linear infinite;"><path d="M21 12a9 9 0 1 1-6.2-8.5" stroke="#D67037" stroke-width="2.6" stroke-linecap="round"/></svg>
            agent
          </span>
        </div>

        <!-- STAGE -->
        <div style="position:relative; flex:1; min-height:0; display:flex; flex-direction:column; justify-content:center; padding:18px 2px;">

          <!-- question prompt (persists across scenes 2-3) -->
          <div v-if="showQuestion" style="align-self:flex-end; max-width:84%; margin-bottom:14px; background:#2C211A; border:1px solid rgba(255,255,255,.07); color:#E8DDD2; font-size:14px; line-height:1.45; padding:10px 15px; border-radius:14px 14px 5px 14px; animation:cai-rise .4s cubic-bezier(.2,.8,.2,1) both;">{{ question }}</div>

          <!-- SCENE 1: pick a source -->
          <div v-if="scene === 1" style="animation:cai-fade .45s both;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><ellipse cx="12" cy="6" rx="7" ry="3" stroke="#C2854F" stroke-width="2"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" stroke="#C2854F" stroke-width="2"/></svg>
              <span style="font-size:13.5px; color:#CABBAC; font-weight:600;">Select a data source</span>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:9px;">
              <div v-for="src in sourceTiles" :key="src.name" style="position:relative; display:flex; align-items:center; gap:11px; border-radius:12px; padding:13px; transition:border-color .35s, background .35s;"
                :style="{ border: '1px solid ' + src.bd, background: src.bg }">
                <span style="width:30px; height:30px; border-radius:8px; background:rgba(255,255,255,.06); display:flex; align-items:center; justify-content:center; flex-shrink:0;"><svg width="15" height="15" viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="16" rx="2" stroke="#B8A99A" stroke-width="1.8"/><path d="M3 9h18M9 4v16" stroke="#B8A99A" stroke-width="1.8"/></svg></span>
                <span style="line-height:1.2;"><span style="display:block; font-size:13.5px; font-weight:600;" :style="{ color: src.nameColor }">{{ src.name }}</span><span style="display:block; font-size:11.5px; color:#8A7868;">{{ src.sub }}</span></span>
                <span v-if="src.picked" style="position:absolute; right:11px; top:50%; transform:translateY(-50%); animation:cai-pop .3s both;"><svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M5 3l14 9-6 1 3 6-3 1-3-6-5 4z" fill="#fff" stroke="#1A1611" stroke-width="1.2" stroke-linejoin="round"/></svg></span>
              </div>
            </div>
            <div v-if="connecting" style="display:flex; align-items:center; gap:9px; margin-top:13px; font-size:13px; color:#C2854F; animation:cai-fade .3s both;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="animation:cai-spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.2-8.5" stroke="#D67037" stroke-width="2.6" stroke-linecap="round"/></svg>
              Connecting to {{ connectName }}…
            </div>
          </div>

          <!-- SCENE 2: progress checklist -->
          <div v-else-if="scene === 2" style="background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.08); border-radius:15px; padding:15px 16px; animation:cai-rise .4s cubic-bezier(.2,.8,.2,1) both;">
            <div style="display:flex; align-items:center; gap:9px; margin-bottom:13px; padding-bottom:12px; border-bottom:1px solid rgba(255,255,255,.07);">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="animation:cai-spin 2s linear infinite;"><path d="M21 12a9 9 0 1 1-6.2-8.5" stroke="#D67037" stroke-width="2.6" stroke-linecap="round"/></svg>
              <span style="font-size:13.5px; font-weight:600; color:#F1E6DB;">Working</span>
              <span style="margin-left:auto; font-size:12px; color:#8A7868;">{{ progressCount }}</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:11px;">
              <div v-for="(t, ti) in taskRows" :key="ti" style="display:flex; align-items:center; gap:11px;">
                <span style="width:20px; height:20px; flex-shrink:0; display:flex; align-items:center; justify-content:center;">
                  <span v-if="t.done" style="width:20px; height:20px; border-radius:50%; background:#D67037; display:flex; align-items:center; justify-content:center; animation:cai-pop .3s both;"><svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2.5 6.2l2.2 2.3L9.5 3.5" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
                  <svg v-else-if="t.active" width="18" height="18" viewBox="0 0 24 24" fill="none" style="animation:cai-spin 1s linear infinite;"><circle cx="12" cy="12" r="9" stroke="rgba(214,112,55,.25)" stroke-width="2.6"/><path d="M21 12a9 9 0 0 0-9-9" stroke="#D67037" stroke-width="2.6" stroke-linecap="round"/></svg>
                  <span v-else style="width:16px; height:16px; border-radius:50%; border:1.8px solid rgba(255,255,255,.16);"></span>
                </span>
                <span style="font-size:13.5px; transition:color .3s;" :style="{ color: t.color, textDecoration: t.deco }">{{ t.label }}</span>
              </div>
            </div>
          </div>

          <!-- SCENE 3: result -->
          <div v-else style="background:linear-gradient(135deg,#D67037,#B8431A); border-radius:15px 15px 15px 5px; padding:16px 17px; color:#fff; animation:cai-glow 3.2s ease-in-out infinite, cai-rise .4s cubic-bezier(.2,.8,.2,1) both; align-self:flex-start; max-width:90%;">
            <div style="display:flex; align-items:flex-end; gap:7px; height:64px; margin-bottom:13px;">
              <span v-for="(bar, bi) in chartBars" :key="bi" style="flex:1; min-width:0; border-radius:5px 5px 2px 2px; background:rgba(255,255,255,.9); transition:height .65s cubic-bezier(.2,.8,.2,1);" :style="{ height: bar.h, transitionDelay: bar.delay }"></span>
            </div>
            <div style="font-size:15px; line-height:1.45; font-weight:500;"><span>{{ resultText }}</span><span v-if="streaming" style="display:inline-block; width:7px; height:15px; background:#fff; margin-left:2px; vertical-align:-2px; border-radius:1px; animation:cai-blink .9s steps(1) infinite;"></span></div>
            <div v-if="delta" style="display:inline-flex; align-items:center; gap:6px; margin-top:11px; background:rgba(0,0,0,.24); padding:5px 11px; border-radius:8px; font-size:12.5px; font-weight:600; font-family:ui-monospace,monospace; animation:cai-pop .35s both;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M4 7V5a2 2 0 0 1 2-2h2M4 17v2a2 2 0 0 0 2 2h2M20 7V5a2 2 0 0 0-2-2h-2M20 17v2a2 2 0 0 1-2 2h-2" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>
              {{ delta }}
            </div>
          </div>
        </div>

        <!-- footer -->
        <div style="position:relative; display:flex; align-items:center; gap:20px; padding-top:14px; border-top:1px solid rgba(255,255,255,.07); font-size:13px; color:#9A8678; flex-shrink:0;">
          <span><strong style="color:#D9CABB;">4</strong> sources</span>
          <span><strong style="color:#D9CABB;">11</strong> tables</span>
          <span style="margin-left:auto; display:inline-flex; align-items:center; gap:7px;"><span style="width:6px; height:6px; border-radius:50%; background:#3FA86B;"></span><strong style="color:#D9CABB;">SSO</strong> ready</span>
        </div>
      </section>
    </main>

    <footer style="text-align:center; padding:8px 0 12px; font-size:12.5px; color:#A89C8C; flex-shrink:0;">© 2026 City Agent Insights · Data Intelligence &amp; Analytics</footer>
  </div>
  <div v-else class="flex h-screen items-center justify-center" style="background:#F6F1EA"><Spinner class="h-6 w-6" /></div>
</template>


<script setup lang="ts">

import qs from 'qs';

import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue';
import Spinner from '~/components/Spinner.vue';
import { idpLogoSvg } from '~/utils/idpLogos';

const { t } = useI18n()
const { rawToken } = useAuthState()
const { fetchOrganization } = useOrganization()
const route = useRoute()
const googleSignIn = ref(false)
const googleLogo = ref('google')
const signupEnabled = ref(false)
const oidcProviders = ref<{ name: string; enabled: boolean; logo?: string }[]>([])
const loadingProvider = ref<string | null>(null)
const authMode = ref<'hybrid'|'local_only'|'sso_only'>('hybrid')
const smtpEnabled = ref(false)
const ldapEnabled = ref(false)
const ldapLogo = ref('ldap')

// Which auth providers the admin has enabled (Settings → Identity Provider).
// oidcProviders is already filtered to enabled-only on load. Microsoft + Keycloak
// are stored as OIDC providers (names microsoft/azure/entra, keycloak).
const msProvider = computed(() => oidcProviders.value.find(p => /microsoft|azure|entra/i.test(p.name)) || null)
const keycloakProvider = computed(() => oidcProviders.value.find(p => /keycloak/i.test(p.name)) || null)
const genericSsoProvider = computed(() => oidcProviders.value.find(p => !/microsoft|azure|entra|keycloak/i.test(p.name)) || null)
const showGoogle = computed(() => googleSignIn.value)
const showMicrosoft = computed(() => !!msProvider.value)
const showKeycloak = computed(() => !!keycloakProvider.value)
const showSSO = computed(() => !!genericSsoProvider.value)
const showLdap = computed(() => ldapEnabled.value)
const showSocial = computed(() => showGoogle.value || showMicrosoft.value)
const showEnterprise = computed(() => showSSO.value || showKeycloak.value || showLdap.value)
const showProviders = computed(() => showSocial.value || showEnterprise.value)
// Admin-chosen logos (custom upload wins over the brand default).
const msLogo = computed(() => msProvider.value?.logo || 'microsoft')
const keycloakLogo = computed(() => keycloakProvider.value?.logo || 'keycloak')
const ssoLogo = computed(() => genericSsoProvider.value?.logo || 'oidc')
const socialCols = computed(() => (showGoogle.value ? 1 : 0) + (showMicrosoft.value ? 1 : 0))
const entCols = computed(() => (showSSO.value ? 1 : 0) + (showKeycloak.value ? 1 : 0) + (showLdap.value ? 1 : 0))
const isSubmitting = ref(false)
const rememberMe = ref(true)
const revealForm = ref(false)
const localOverride = computed(() => route.query.local === 'true')
// Form is shown unless the deployment is SSO-only (then it's revealed via Admin/LDAP).
const showForm = computed(() => authMode.value !== 'sso_only' || localOverride.value || revealForm.value)

// Load the design fonts (Spectral serif heading + Hanken Grotesk body) for this page.
useHead({
  link: [
    { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
    { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
    { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,500;0,600;1,400&family=Hanken+Grotesk:wght@400;500;600;700&display=swap' },
  ],
})

// Version chip: real product version (VERSION_HYBRID) from /api/settings,
// with an env label derived from the host (localhost -> local, else prod).
const hybridVersion = ref('…')
const envLabel = computed(() => {
  if (import.meta.client) {
    const h = window.location.hostname
    if (h === 'localhost' || h === '127.0.0.1') return 'local'
  }
  return 'prod'
})

// Time-of-day greeting (client-only page, so local hour is correct).
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 5) return 'Working late'
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  if (h < 22) return 'Good evening'
  return 'Working late'
})

definePageMeta({
  auth: {
    unauthenticatedOnly: true,
  },
  layout: 'users'
})

// Define reactive references for email and password
const email = ref('');
const password = ref('');
const showPw = ref(false);

const error_message = ref('')
// Extract the signIn function from useAuth
const { signIn, getSession } = useAuth();

// ===================== right-panel "agent at work" showcase =====================
const sources = [
  { name: 'Postgres', sub: 'primary db' },
  { name: 'Stripe', sub: 'billing' },
  { name: 'GA4', sub: 'analytics' },
  { name: 'Warehouse', sub: 'snowflake' },
]
const turns = [
  { q: 'Top 5 artists by revenue this quarter?', pick: 0,
    tasks: ['Scan invoice_line · 4.2M rows', 'Join track ⋈ artist', 'Aggregate revenue', 'Rank top 5'],
    a: 'Rock leads with +$11.2K this quarter.', delta: '+12% QoQ', chart: [52, 68, 44, 90, 76] },
  { q: 'Which customers churned in May?', pick: 1,
    tasks: ['Load subscriptions', 'Flag lapsed accounts', 'Compute lost MRR', 'Group by plan'],
    a: '23 accounts lapsed → −$4.8K MRR.', delta: '−4.8K MRR', chart: [80, 72, 58, 46, 30] },
  { q: "Forecast next month's signups.", pick: 2,
    tasks: ['Read events.signup', 'Build 12-month series', 'Fit trend model', 'Project next period'],
    a: '≈ 1,420 signups expected, up 9%.', delta: '+9% MoM', chart: [40, 55, 50, 70, 82, 95] },
]

const scene = ref(1)
const pickedSource = ref<number | null>(null)
const connecting = ref(false)
const question = ref('')
const showQuestion = ref(false)
const tasks = ref<{ label: string; status: string }[]>([])
const chart = ref<number[]>([])
const chartGrown = ref(false)
const resultText = ref('')
const streaming = ref(false)
const delta = ref('')

let mounted = true
let timers: ReturnType<typeof setTimeout>[] = []
const wait = (ms: number) => new Promise<void>(r => { const tm = setTimeout(r, ms); timers.push(tm) })

const sourceTiles = computed(() => sources.map((src, idx) => {
  const picked = idx === pickedSource.value
  return {
    name: src.name, sub: src.sub, picked,
    bd: picked ? '#D67037' : 'rgba(255,255,255,.08)',
    bg: picked ? 'rgba(214,112,55,.12)' : 'rgba(255,255,255,.03)',
    nameColor: picked ? '#F1E6DB' : '#CABBAC',
  }
}))
const taskRows = computed(() => tasks.value.map(t => ({
  label: t.label,
  done: t.status === 'done', active: t.status === 'active', pending: t.status === 'pending',
  color: t.status === 'done' ? '#8A7868' : (t.status === 'active' ? '#F1E6DB' : '#9A8678'),
  deco: t.status === 'done' ? 'line-through' : 'none',
})))
const progressCount = computed(() => tasks.value.filter(t => t.status === 'done').length + ' / ' + tasks.value.length)
const chartBars = computed(() => (chart.value || []).map((h, idx) => ({
  h: chartGrown.value ? h + '%' : '0%',
  delay: (idx * 0.06) + 's',
})))
const connectName = computed(() => pickedSource.value != null ? sources[pickedSource.value].name : '')
const statusLine = computed(() => scene.value === 1 ? 'live · connecting to your data'
  : scene.value === 2 ? 'live · running the query'
  : 'live · answered from your data')

async function runShowcase(i: number) {
  if (!mounted) return
  const turn = turns[i % turns.length]

  // SCENE 1 — pick a source
  scene.value = 1; pickedSource.value = null; connecting.value = false
  question.value = turn.q; showQuestion.value = false
  tasks.value = []; chart.value = turn.chart; chartGrown.value = false
  resultText.value = ''; streaming.value = false; delta.value = ''
  await wait(750); if (!mounted) return
  pickedSource.value = turn.pick
  await wait(750); if (!mounted) return
  connecting.value = true
  await wait(800); if (!mounted) return

  // SCENE 2 — progress checklist
  tasks.value = turn.tasks.map((label, idx) => ({ label, status: idx === 0 ? 'active' : 'pending' }))
  scene.value = 2; showQuestion.value = true
  await wait(700)
  for (let k = 0; k < turn.tasks.length; k++) {
    if (!mounted) return
    tasks.value = tasks.value.map((x, idx) =>
      idx <= k ? { ...x, status: 'done' } : (idx === k + 1 ? { ...x, status: 'active' } : x))
    await wait(620)
  }
  await wait(450); if (!mounted) return

  // SCENE 3 — result
  scene.value = 3; resultText.value = ''; streaming.value = true; chartGrown.value = false
  await wait(120); if (!mounted) return
  chartGrown.value = true
  await wait(350)
  for (let c = 1; c <= turn.a.length; c++) {
    if (!mounted) return
    resultText.value = turn.a.slice(0, c)
    await wait(22)
  }
  if (!mounted) return
  streaming.value = false; delta.value = turn.delta
  await wait(2600)
  runShowcase(i + 1)
}

onBeforeUnmount(() => { mounted = false; timers.forEach(clearTimeout) })

// Only honor redirects to same-origin paths to avoid open-redirect bugs
function safeRedirectTarget(value: unknown): string | null {
  if (typeof value !== 'string' || !value) return null
  if (!value.startsWith('/') || value.startsWith('//')) return null
  return value
}

const OAUTH_REDIRECT_STORAGE_NAME = 'dash:postSignInRedirect'

// Helper to extract error message from server response
function extractErrorMessage(error: any, fallback: string): string {
  const data = error?.data
  if (!data) return fallback
  if (Array.isArray(data.detail)) {
    return data.detail.map((d: any) => d.msg || d.message || JSON.stringify(d)).join('\n')
  }
  if (typeof data.detail === 'string') return data.detail
  if (data.message) return data.message
  return fallback
}
const pageLoaded = ref(false)

onMounted(async () => {
  try {
    const settings = await $fetch('/api/settings')
    if (settings?.oidc_providers?.length) {
      oidcProviders.value = settings.oidc_providers.filter((p: any) => p.enabled)
    }
    if (settings?.auth?.mode) {
      authMode.value = settings.auth.mode
    }
    smtpEnabled.value = settings?.smtp_enabled ?? false
    ldapEnabled.value = !!(settings as any)?.ldap_enabled
    ldapLogo.value = (settings as any)?.ldap_logo || 'ldap'
    googleSignIn.value = !!(settings as any)?.google_oauth?.enabled
    googleLogo.value = (settings as any)?.google_oauth?.logo || 'google'
    signupEnabled.value = !!(settings as any)?.signup_enabled
    const hv = (settings as any)?.hybrid_version
    if (hv) hybridVersion.value = hv
  } catch (_) {}
  const inviteError = route.query.error as string
  if (inviteError) {
    error_message.value = inviteError
  }
  const access_token = route.query.access_token as string
  if (access_token) {
    rawToken.value = access_token
    await getSession({ force: true })
    const org = await fetchOrganization()
    if (!org || !org.id) {
      navigateTo('/organizations/new')
    } else {
      let pendingRedirect: string | null = null
      try {
        pendingRedirect = safeRedirectTarget(sessionStorage.getItem(OAUTH_REDIRECT_STORAGE_NAME))
        sessionStorage.removeItem(OAUTH_REDIRECT_STORAGE_NAME)
      } catch (_) {}
      navigateTo(pendingRedirect || '/')
    }
    return
  }
  pageLoaded.value = true
  // kick off the agent-at-work showcase loop
  runShowcase(0)
})


function persistRedirectForOAuth() {
  const target = safeRedirectTarget(route.query.redirect)
  try {
    if (target) {
      sessionStorage.setItem(OAUTH_REDIRECT_STORAGE_NAME, target)
    } else {
      sessionStorage.removeItem(OAUTH_REDIRECT_STORAGE_NAME)
    }
  } catch (_) {}
}

async function signInWithCredentials() {
  isSubmitting.value = true
  error_message.value = ''
  const route = useRoute();
  const redirectedFrom = safeRedirectTarget(route.query.redirect)

  const credentials = {
    username: email.value,
    password: password.value,
  };

  try {
    const response = await $fetch('/api/auth/jwt/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: qs.stringify(credentials),
    });

    if (response) {
      rawToken.value = response.access_token
      await getSession({ force: true })
      const org = await fetchOrganization();
      if (!org || !org.id) {
        navigateTo('/organizations/new');
      } else {
        navigateTo(redirectedFrom || '/');
      }
    } else {
      error_message.value = t('auth.invalidCredentials')
      isSubmitting.value = false
    }
  } catch (error: any) {
    error_message.value = extractErrorMessage(error, t('auth.invalidCredentials'))
    isSubmitting.value = false
  }
}

async function signInWithGoogle() {
  try {
    loadingProvider.value = 'google'
    persistRedirectForOAuth()
    const response = await $fetch('/api/auth/google/authorize', { method: 'GET' });
    if (response.authorization_url) {
      window.location.href = response.authorization_url;
    }
  } catch (error) {
    error_message.value = t('auth.googleInitError')
    loadingProvider.value = null
  }
}

async function signInWithProvider(name: string) {
  try {
    loadingProvider.value = name
    persistRedirectForOAuth()
    const response = await $fetch(`/api/auth/${name}/authorize`, { method: 'GET' })
    if ((response as any)?.authorization_url) {
      window.location.href = (response as any).authorization_url
    }
  } catch (error) {
    error_message.value = t('auth.providerInitError', { provider: name })
    loadingProvider.value = null
  }
}

// Map the design's fixed enterprise buttons onto the configured OIDC providers.
function pickProvider(re: RegExp): string | null {
  const p = oidcProviders.value.find(x => re.test(x.name))
  return p?.name || null
}
function onMicrosoft() {
  const name = pickProvider(/microsoft|azure|entra/i)
  if (name) return signInWithProvider(name)
  error_message.value = 'Microsoft sign-in is not configured yet. Add an Azure/Entra OIDC provider in Settings → Authentication.'
}
function onKeycloak() {
  const name = pickProvider(/keycloak/i)
  if (name) return signInWithProvider(name)
  error_message.value = 'Keycloak sign-in is not configured yet. Add a Keycloak OIDC provider in Settings → Authentication.'
}
function onSSO() {
  // Generic SSO: use any non-Google/Microsoft/Keycloak provider, else the first available.
  const name = pickProvider(/saml|sso|okta|onelogin|ping/i) || oidcProviders.value[0]?.name
  if (name) return signInWithProvider(name)
  error_message.value = 'No SSO provider configured. Add a SAML/OIDC provider in Settings → Authentication.'
}
function onLDAP() {
  // LDAP authenticates through the same directory username/password as the email form.
  revealForm.value = true
  error_message.value = ''
  nextTick(() => {
    const el = document.getElementById('email') as HTMLInputElement | null
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el?.focus()
  })
}
</script>

<style scoped>
.cai-root {
  min-height: 100vh;
  width: 100%;
  background: #F6F1EA;
  color: #1A1611;
  display: flex;
  flex-direction: column;
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.cai-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 44px;
  max-width: 1500px;
  margin: 0 auto;
  width: 100%;
  flex-shrink: 0;
}
.cai-main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1.04fr 1fr;
  gap: 48px;
  max-width: 1500px;
  margin: 0 auto;
  width: 100%;
  padding: 0 44px 16px;
}
.cai-left {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 0;
}
.cai-h1 {
  font-family: 'Spectral', ui-serif, Georgia, serif;
  font-weight: 500;
  font-size: 42px;
  line-height: 1.08;
  letter-spacing: -.015em;
  margin: 0 0 12px;
  color: #211B14;
}
@media (max-width: 1024px) {
  .cai-main { grid-template-columns: 1fr; }
  .cai-right { display: none; }
  .cai-header, .cai-main { padding-left: 24px; padding-right: 24px; }
  .cai-h1 { font-size: 34px; }
}

.cai-field:focus-within { border-color: #C2541E !important; box-shadow: 0 0 0 4px rgba(194,84,30,.12) !important; }
.cai-field { transition: border-color .16s, box-shadow .16s; }
.cai-prov:hover { border-color: #C9BEAF !important; background: #FFFFFF !important; transform: translateY(-1px); }
.cai-prov { transition: .15s; }
.cai-ent:hover { border-color: #C2541E !important; color: #C2541E !important; }
.cai-ent { transition: .15s; }
.cai-primary { transition: background .16s, transform .08s; }
.cai-primary:hover { background: #000 !important; }
.cai-primary:active { transform: translateY(1px); }
.cai-primary:disabled { opacity: .6; cursor: not-allowed; }
.cai-prov:disabled { opacity: .55; cursor: not-allowed; }
.cai-link:hover { color: #C2541E !important; }

@keyframes cai-pulse { 0%,100% { opacity:1; transform:scale(1);} 50% { opacity:.45; transform:scale(.82);} }
@keyframes cai-rise { from { opacity:0; transform:translateY(14px) scale(.97);} to { opacity:1; transform:translateY(0) scale(1);} }
@keyframes cai-fade { from { opacity:0;} to { opacity:1;} }
@keyframes cai-glow { 0%,100% { box-shadow:0 0 0 1px rgba(214,112,55,.3), 0 18px 50px -20px rgba(214,112,55,.5);} 50% { box-shadow:0 0 0 1px rgba(214,112,55,.5), 0 22px 60px -16px rgba(214,112,55,.72);} }
@keyframes cai-blink { 0%,49% { opacity:1;} 50%,100% { opacity:0;} }
@keyframes cai-drift { 0% { background-position:0 0;} 100% { background-position:36px 36px;} }
@keyframes cai-orb { 0%,100% { transform:translate(0,0) scale(1); opacity:.5;} 50% { transform:translate(24px,-18px) scale(1.18); opacity:.85;} }
@keyframes cai-orb2 { 0%,100% { transform:translate(0,0) scale(1); opacity:.35;} 50% { transform:translate(-20px,16px) scale(1.2); opacity:.6;} }
@keyframes cai-spin { to { transform:rotate(360deg);} }
@keyframes cai-pop { 0% { opacity:0; transform:scale(.6);} 60% { transform:scale(1.12);} 100% { opacity:1; transform:scale(1);} }
@keyframes cai-bob { 0%,100% { transform:translateY(0);} 50% { transform:translateY(-5px);} }

@media (prefers-reduced-motion: reduce) {
  .cai-root *, .cai-root *::before, .cai-root *::after { animation: none !important; }
}
</style>
