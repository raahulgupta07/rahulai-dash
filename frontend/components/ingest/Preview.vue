<!--
  IngestPreview — F09 Universal Ingest Brain, the "show before you reshape" gate.

  Auto-import name: <IngestPreview> (dir `ingest` + file `Preview`). If a bare tag
  ever renders blank, explicit-import it (Nuxt <DirX> landmine) and restart dev.

  Flow: parent passes a File → this posts it to /ingest-brain/preview → renders
  what the pipeline understood (tables, header rows, merged-cell/blank notes,
  per-column profile, join hints). User Confirms (optionally after correcting) →
  we POST the profiles to /ingest-brain/profiles/{dataSourceId} (pending) and
  emit `confirmed`. Nothing is reshaped silently — this screen IS the gate.

  Additive + flag-gated: backend returns {disabled:true} when the flag is off →
  we emit `skip` and the host falls back to today's plain upload.
-->
<template>
  <div v-if="open" class="ib-overlay" @click.self="close">
    <div class="ib-modal">
      <header class="ib-head">
        <div>
          <h3>Review before import</h3>
          <p class="ib-sub">{{ headSummary }}</p>
        </div>
        <button class="ib-x" @click="close">✕</button>
      </header>

      <div v-if="loading" class="ib-body ib-center">
        <div class="ib-spin"></div>
        <p>Reading your file the way a careful analyst would…</p>
      </div>

      <div v-else-if="error" class="ib-body">
        <div class="ib-warn">Couldn’t deep-read this file: {{ error }}. You can still import it normally.</div>
      </div>

      <div v-else class="ib-body">
        <div v-for="(t, ti) in tables" :key="ti" class="ib-table">
          <div class="ib-table-head">
            <strong>{{ t.name }}</strong>
            <span class="ib-meta">{{ t.sheet ? 'sheet ' + t.sheet + ' · ' : '' }}{{ t.region_bbox }} · {{ t.row_count }} rows</span>
          </div>

          <div v-if="t.notes && t.notes.length" class="ib-notes">
            <span v-for="(n, ni) in t.notes" :key="ni" class="ib-note">⚙ {{ n }}</span>
          </div>

          <div class="ib-grid-wrap">
            <table class="ib-grid">
              <thead>
                <tr><th v-for="(h, hi) in t.header" :key="hi">{{ h }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="(r, ri) in t.sample_rows" :key="ri">
                  <td v-for="(c, ci) in r" :key="ci">{{ c }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="profiles.length" class="ib-prof">
          <h4>What each column means</h4>
          <table class="ib-grid">
            <thead><tr><th>Column</th><th>Type</th><th>Role</th><th>Unit</th><th>Null%</th><th>Distinct</th><th>PII</th><th>Samples</th></tr></thead>
            <tbody>
              <tr v-for="(p, pi) in profiles" :key="pi">
                <td><b>{{ p.name }}</b></td>
                <td>{{ p.dtype }}</td>
                <td><span class="ib-role" :data-role="p.semantic_role">{{ p.semantic_role }}</span></td>
                <td>{{ p.unit || '—' }}</td>
                <td>{{ p.null_pct }}</td>
                <td>{{ p.cardinality }}</td>
                <td>{{ p.pii_flag ? '🔒' : '' }}</td>
                <td class="ib-samples">{{ (p.sample_values || []).join(', ') }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="joins.length" class="ib-joins">
          <h4>Possible links to your other data</h4>
          <div v-for="(j, ji) in joins" :key="ji" class="ib-join">
            {{ j.left }} ↔ {{ j.right }} <span class="ib-conf">{{ Math.round(j.confidence * 100) }}%</span>
          </div>
        </div>
      </div>

      <footer class="ib-foot">
        <button class="ib-ghost" @click="close">Cancel</button>
        <button class="ib-primary" :disabled="loading || committing || !!error" @click="confirm">
          {{ committing ? 'Saving…' : 'Looks right — import' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  file: { type: Object, default: null },          // the File to preview
  dataSourceId: { type: String, default: '' },     // where to attach profiles (after upload)
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['confirmed', 'skip', 'close'])

const loading = ref(false)
const committing = ref(false)
const error = ref('')
const tables = ref([])
const profiles = ref([])
const joins = ref([])
const previewSummary = ref('')

const headSummary = computed(() =>
  previewSummary.value || (props.file ? props.file.name : 'Understanding your file'))

watch(() => [props.open, props.file], async () => {
  if (props.open && props.file) await runPreview()
})

async function runPreview() {
  loading.value = true; error.value = ''
  tables.value = []; profiles.value = []; joins.value = []
  try {
    const fd = new FormData()
    fd.append('file', props.file)
    const res = await useMyFetch('/ingest-brain/preview', { method: 'POST', body: fd })
    const data = res?.data?.value ?? res
    if (data?.disabled) { emit('skip'); return }          // flag OFF → host falls back
    if (!data?.ok && data?.error) { error.value = data.error; return }
    tables.value = data.tables || []
    profiles.value = data.profiles || []
    joins.value = data.join_candidates || []
    previewSummary.value = data?.preview?.summary || ''
  } catch (e) {
    error.value = (e && e.message) ? e.message : 'preview failed'
  } finally {
    loading.value = false
  }
}

async function confirm() {
  // persist profiles as pending (only if we have a target DataSource yet)
  if (props.dataSourceId && profiles.value.length) {
    committing.value = true
    try {
      await useMyFetch(`/ingest-brain/profiles/${props.dataSourceId}`, {
        method: 'POST',
        body: { profiles: profiles.value },
      })
    } catch (e) { /* fail-soft: import proceeds even if profile save hiccups */ }
    finally { committing.value = false }
  }
  emit('confirmed', { tables: tables.value, profiles: profiles.value })
}

function close() { emit('close') }
</script>

<style scoped>
.ib-overlay{position:fixed;inset:0;background:rgba(20,16,12,.55);display:flex;align-items:center;justify-content:center;z-index:120;padding:24px}
.ib-modal{background:#FFFDF9;color:#211B14;width:min(920px,96vw);max-height:88vh;display:flex;flex-direction:column;border-radius:16px;box-shadow:0 18px 60px rgba(0,0,0,.3);overflow:hidden}
.ib-head{display:flex;justify-content:space-between;align-items:flex-start;padding:18px 22px;border-bottom:1px solid #E2D6C5}
.ib-head h3{margin:0;font-family:'Spectral',Georgia,serif;font-size:20px}
.ib-sub{margin:3px 0 0;color:#6b5f50;font-size:13px}
.ib-x{border:none;background:transparent;font-size:18px;cursor:pointer;color:#6b5f50}
.ib-body{padding:18px 22px;overflow-y:auto}
.ib-center{text-align:center;color:#6b5f50}
.ib-spin{width:34px;height:34px;border:3px solid #E2D6C5;border-top-color:#C2541E;border-radius:50%;margin:8px auto 14px;animation:ibspin .8s linear infinite}
@keyframes ibspin{to{transform:rotate(360deg)}}
.ib-warn{background:#FBEFE4;border:1px solid #E7C9A8;color:#8a4b1e;border-radius:10px;padding:12px 14px;font-size:14px}
.ib-table{margin-bottom:20px}
.ib-table-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
.ib-meta{color:#6b5f50;font-size:12px}
.ib-notes{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.ib-note{background:#F4EEE5;border:1px solid #E2D6C5;border-radius:14px;padding:2px 10px;font-size:11px;color:#6b5f50}
.ib-grid-wrap{overflow-x:auto;border:1px solid #E2D6C5;border-radius:10px}
.ib-grid{width:100%;border-collapse:collapse;font-size:12px}
.ib-grid th,.ib-grid td{text-align:left;padding:6px 9px;border-bottom:1px solid #EFE7DA;white-space:nowrap}
.ib-grid th{background:#F4EEE5;font-weight:700;color:#3a3127;position:sticky;top:0}
.ib-prof,.ib-joins{margin-top:18px}
.ib-prof h4,.ib-joins h4{font-family:'Spectral',Georgia,serif;margin:0 0 8px}
.ib-role{font-size:11px;font-weight:700;padding:1px 8px;border-radius:10px;background:#EDEFF2}
.ib-role[data-role="measure"]{background:#EAF4EE;color:#2E7D52}
.ib-role[data-role="id"]{background:#FBEFE4;color:#A8330F}
.ib-role[data-role="date"]{background:#EDF0F5;color:#2C5C8A}
.ib-samples{color:#6b5f50;max-width:240px;overflow:hidden;text-overflow:ellipsis}
.ib-join{font-size:13px;padding:4px 0}
.ib-conf{color:#C2541E;font-weight:700;margin-left:6px}
.ib-foot{display:flex;justify-content:flex-end;gap:10px;padding:14px 22px;border-top:1px solid #E2D6C5}
.ib-ghost{background:transparent;border:1px solid #D8CBB8;border-radius:9px;padding:8px 16px;cursor:pointer;color:#3a3127}
.ib-primary{background:#C2541E;border:none;color:#fff;border-radius:9px;padding:8px 18px;font-weight:600;cursor:pointer}
.ib-primary:disabled{opacity:.55;cursor:default}
</style>
