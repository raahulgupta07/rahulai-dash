<!--
  SmartBuildSheet — Smart Dashboard Build (HYBRID_SMART_DASHBOARD).
  Auto-import name: <DashboardSmartBuildSheet> (dir `dashboard` + file `SmartBuildSheet`).
  If a bare tag renders blank, explicit-import it (Nuxt <DirX> landmine) + restart dev.

  Opens from the Outputs "Generate dashboard" button. On open it asks the backend
  what it already knows (context): prefills the prompt from the chat turn, shows the
  agent's OWN data sources (NOT a picker), and the Auto model badge. The user can
  just hit Build. Only when the backend says "blind" does it show ONE clarify chip.
  Build reuses the proven artifact pipeline; a progress wave then a done state.

  Additive + flag-gated: backend returns {disabled:true} when off → emits `skip` and
  the host falls back to the existing one-click builder.
-->
<template>
  <div v-if="open" class="sb-overlay" @click.self="close">
    <div class="sb-sheet">
      <header class="sb-head">
        <h2>📊 Build a dashboard
          <span v-if="agentName" class="sb-agent">· {{ agentName }}</span>
        </h2>
        <button class="sb-x" @click="close">✕</button>
      </header>

      <!-- loading context -->
      <div v-if="phase==='loading'" class="sb-body sb-center">
        <div class="sb-spin"></div><p>Reading what you just asked…</p>
      </div>

      <!-- clarify (only when blind) -->
      <div v-else-if="phase==='clarify'" class="sb-body">
        <div class="sb-clarify">
          <div class="sb-q">{{ clarify.question }}</div>
          <div class="sb-opts">
            <button v-for="(o,i) in clarify.options" :key="i" class="sb-chip on" @click="pickClarify(o)">{{ o }}</button>
          </div>
        </div>
        <p class="sb-hint">Pick one, or type your own focus below and Build.</p>
        <textarea v-model="prompt" class="sb-ta" placeholder="…or describe what this dashboard should show"></textarea>
      </div>

      <!-- setup (the normal path: prefilled, mostly just hit Build) -->
      <div v-else-if="phase==='setup'" class="sb-body">
        <div class="sb-meta">
          <span class="sb-badge">⚡ Auto</span>
          <span class="sb-data">📦 Data:
            <template v-if="sources.length">{{ sources.map(s=>s.name).join(', ') }}</template>
            <template v-else>this agent’s sources</template>
            <span class="sb-auto">· auto</span>
          </span>
        </div>

        <label class="sb-lbl">Build from what you asked <span class="sb-sub">— edit to steer, or just Build</span></label>
        <textarea v-model="prompt" class="sb-ta" :placeholder="prefillPlaceholder"></textarea>

        <button class="sb-adv" @click="showOpts=!showOpts">{{ showOpts ? '▾' : '▸' }} Options</button>
        <div v-if="showOpts" class="sb-options">
          <div class="sb-opt">
            <span class="sb-olbl">Size</span>
            <div class="sb-seg">
              <button :class="{on:size==='compact'}" @click="size='compact'">Compact</button>
              <button :class="{on:size==='full'}" @click="size='full'">Full</button>
            </div>
          </div>
          <div class="sb-opt">
            <span class="sb-olbl">Depth</span>
            <div class="sb-seg">
              <button :class="{on:depth==='exec'}" @click="depth='exec'">Executive</button>
              <button :class="{on:depth==='analyst'}" @click="depth='analyst'">Analyst</button>
            </div>
          </div>
        </div>
      </div>

      <!-- needs data -->
      <div v-else-if="phase==='needsData'" class="sb-body">
        <div class="sb-warn">{{ message }}</div>
      </div>

      <!-- building -->
      <div v-else-if="phase==='building'" class="sb-body sb-center">
        <div class="sb-spin"></div>
        <div class="sb-wave">⚡ Auto · {{ agentName || 'agent' }} · building…</div>
        <p class="sb-step">{{ buildStep }}</p>
      </div>

      <!-- done -->
      <div v-else-if="phase==='done'" class="sb-body sb-center">
        <div class="sb-tick">✓</div>
        <p>Dashboard ready.</p>
      </div>

      <!-- error -->
      <div v-else-if="phase==='error'" class="sb-body">
        <div class="sb-warn">{{ error }}</div>
      </div>

      <footer class="sb-foot">
        <div class="sb-note">{{ footNote }}</div>
        <div>
          <button class="sb-ghost" @click="close">Close</button>
          <button v-if="phase==='setup' || phase==='clarify'" class="sb-primary" :disabled="building" @click="build">Build dashboard →</button>
          <button v-else-if="phase==='done'" class="sb-primary" @click="finish">Open</button>
          <button v-else-if="phase==='needsData' || phase==='error'" class="sb-primary" @click="phase='setup'">Back</button>
        </div>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  reportId: { type: String, required: true },
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'built', 'skip'])

const phase = ref('loading')          // loading|setup|clarify|building|needsData|done|error
const prompt = ref('')
const size = ref('compact')
const depth = ref('exec')
const showOpts = ref(false)
const sources = ref([])
const agentName = ref('')
const clarify = ref({ question: '', options: [] })
const message = ref('')
const error = ref('')
const building = ref(false)
const buildStep = ref('Planning widgets…')
const lastArtifactId = ref('')

const prefillPlaceholder = computed(() =>
  'e.g. Q2 sales — revenue by month and category')
const footNote = computed(() => ({
  loading: 'Understanding the turn…',
  setup: 'Data is auto-picked from this agent. Only the focus is yours.',
  clarify: 'One quick question so I build the right view.',
  building: 'Composing your dashboard…',
  needsData: 'No charts yet for this turn.',
  done: 'Ask a follow-up in chat to refine.',
  error: 'Something went wrong.',
}[phase.value] || ''))

watch(() => props.open, async (v) => { if (v) await loadContext() })

async function loadContext() {
  phase.value = 'loading'
  prompt.value = ''; sources.value = []; error.value = ''
  try {
    const res = await useMyFetch(`/reports/${props.reportId}/dashboard/context`)
    const d = res?.data?.value ?? res
    if (d?.disabled) { emit('skip'); return }
    sources.value = d?.sources || []
    prompt.value = d?.prefill || ''
    if (d?.needs_clarification && d?.clarify) {
      clarify.value = d.clarify
      phase.value = 'clarify'
    } else {
      phase.value = 'setup'
    }
  } catch (e) {
    error.value = (e && e.message) || 'could not read context'
    phase.value = 'setup'   // still let the user type + build
  }
}

function pickClarify(o) {
  prompt.value = prompt.value ? (o + ' — ' + prompt.value) : o
  phase.value = 'setup'
}

async function build() {
  building.value = true
  phase.value = 'building'
  cycleSteps()
  try {
    const res = await useMyFetch(`/reports/${props.reportId}/dashboard/smart-generate`, {
      method: 'POST',
      body: { prompt: prompt.value, size: size.value, depth: depth.value },
    })
    const d = res?.data?.value ?? res
    if (d?.disabled) { emit('skip'); return }
    if (d?.needs_clarification && d?.clarify) { clarify.value = d.clarify; phase.value = 'clarify'; return }
    if (d?.needs_data) { message.value = d.message; phase.value = 'needsData'; return }
    if (!d?.ok) { error.value = d?.error || 'build failed'; phase.value = 'error'; return }
    lastArtifactId.value = d.artifact_id || ''
    phase.value = 'done'
  } catch (e) {
    error.value = (e && e.message) || 'build failed'
    phase.value = 'error'
  } finally {
    building.value = false
  }
}

function cycleSteps() {
  const steps = ['Planning widgets…', 'Writing queries…', 'Composing layout…', 'Adding insights…']
  let i = 0
  const iv = setInterval(() => {
    if (phase.value !== 'building') { clearInterval(iv); return }
    i = (i + 1) % steps.length
    buildStep.value = steps[i]
  }, 900)
}

function finish() { emit('built', { artifactId: lastArtifactId.value }); close() }
function close() { emit('close') }
</script>

<style scoped>
.sb-overlay{position:fixed;inset:0;background:rgba(20,16,12,.55);display:flex;align-items:center;justify-content:center;z-index:120;padding:24px}
.sb-sheet{background:#FFFDF9;color:#211B14;width:min(620px,96vw);max-height:88vh;display:flex;flex-direction:column;border-radius:18px;box-shadow:0 18px 60px rgba(0,0,0,.3);overflow:hidden}
.sb-head{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid #E2D6C5}
.sb-head h2{font-family:'Spectral',Georgia,serif;font-size:18px;margin:0}
.sb-agent{color:#6b5f50;font-size:14px;font-weight:400}
.sb-x{border:none;background:transparent;font-size:17px;cursor:pointer;color:#6b5f50}
.sb-body{padding:18px 20px;overflow-y:auto}
.sb-center{text-align:center;color:#6b5f50}
.sb-meta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;font-size:13px}
.sb-badge{background:#C2541E;color:#fff;font-weight:700;font-size:12px;padding:3px 10px;border-radius:20px}
.sb-data{color:#3a3127}
.sb-auto{color:#8a7a5f}
.sb-lbl{display:block;font-size:13px;font-weight:600;margin-bottom:6px}
.sb-sub{color:#8a7a5f;font-weight:400}
.sb-ta{width:100%;min-height:64px;border:1px solid #E2D6C5;border-radius:10px;padding:10px 12px;font-family:inherit;font-size:14px;resize:vertical}
.sb-adv{background:transparent;border:none;color:#C2541E;font-weight:600;cursor:pointer;padding:8px 0;font-size:13px}
.sb-options{display:flex;flex-direction:column;gap:10px}
.sb-opt{display:flex;align-items:center;gap:12px}
.sb-olbl{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#6b5f50;width:54px}
.sb-seg{display:flex;border:1px solid #E2D6C5;border-radius:9px;overflow:hidden}
.sb-seg button{border:none;background:#fff;padding:7px 14px;font-size:13px;font-weight:600;color:#6b5f50;cursor:pointer;border-right:1px solid #E2D6C5}
.sb-seg button:last-child{border-right:none}
.sb-seg button.on{background:#C2541E;color:#fff}
.sb-clarify{background:#FBEFE4;border:1px solid #E7C9A8;border-radius:12px;padding:12px 14px;margin-bottom:12px}
.sb-q{font-weight:700;color:#A8330F;margin-bottom:8px;font-size:14px}
.sb-opts{display:flex;flex-wrap:wrap;gap:7px}
.sb-chip{border:1px solid #E2D6C5;background:#fff;border-radius:20px;padding:5px 12px;font-size:13px;cursor:pointer}
.sb-chip.on{background:#C2541E;color:#fff;border-color:#C2541E}
.sb-hint{font-size:12px;color:#8a7a5f;margin:0 0 8px}
.sb-warn{background:#FBEFE4;border:1px solid #E7C9A8;color:#8a4b1e;border-radius:10px;padding:12px 14px;font-size:14px}
.sb-spin{width:32px;height:32px;border:3px solid #E2D6C5;border-top-color:#C2541E;border-radius:50%;margin:8px auto 12px;animation:sbsp .8s linear infinite}
@keyframes sbsp{to{transform:rotate(360deg)}}
.sb-wave{font-size:13px;color:#3a3127;font-weight:600}
.sb-step{font-size:12px;color:#8a7a5f}
.sb-tick{width:42px;height:42px;border-radius:50%;background:#2E7D52;color:#fff;font-size:24px;display:flex;align-items:center;justify-content:center;margin:6px auto 10px}
.sb-foot{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:13px 20px;border-top:1px solid #E2D6C5}
.sb-note{font-size:12px;color:#8a7a5f}
.sb-ghost{background:transparent;border:1px solid #D8CBB8;border-radius:9px;padding:8px 15px;cursor:pointer;color:#3a3127}
.sb-primary{background:#C2541E;border:none;color:#fff;border-radius:9px;padding:8px 17px;font-weight:600;cursor:pointer;margin-left:8px}
.sb-primary:disabled{opacity:.55;cursor:default}
</style>
