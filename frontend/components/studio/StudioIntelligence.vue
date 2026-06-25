<template>
  <div>
    <!-- Layer header -->
    <div class="flex items-start gap-3 mb-1">
      <div class="w-10 h-10 rounded-[10px] bg-[#F3E3DA] text-[#8A4527] flex items-center justify-center text-lg flex-none">
        <span v-html="M.glyph" />
      </div>
      <div>
        <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">{{ M.title }}</h2>
        <p class="text-xs text-[#6b6b6b] mt-0.5">{{ M.sub }}</p>
      </div>
      <div class="ms-auto flex items-center gap-2.5">
        <span class="text-[11px] font-medium text-[#6b6b6b] bg-[#f1efe9] px-2 py-1 rounded-md">{{ M.role }}</span>
        <span
          class="text-[11px] font-bold px-2.5 py-1 rounded-md"
          :class="enabled ? 'bg-[#eaf6f0] text-[#2f9e6f]' : 'bg-[#f0eeec] text-[#9a958c]'"
        >{{ enabled ? 'ENABLED' : 'DISABLED' }}</span>
        <!-- real toggle (org-wide flag override; editors only) -->
        <button
          type="button"
          :disabled="!canEdit || toggling"
          class="relative w-[44px] h-[25px] rounded-full transition-colors flex-none"
          :class="[enabled ? 'bg-[#C2683F]' : 'bg-[#d7d7d7]', (!canEdit || toggling) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer']"
          :title="canEdit ? 'Toggle org-wide' : 'Editors only'"
          @click="toggle"
        >
          <span class="absolute top-[3px] w-[19px] h-[19px] bg-white rounded-full shadow transition-all" :style="{ left: enabled ? '22px' : '3px' }" />
        </button>
      </div>
    </div>

    <p class="text-[13px] text-[#444] mt-3 mb-1 max-w-[640px]">{{ M.desc }}</p>
    <div class="text-[11px] text-[#9a958c] font-mono mb-1">flag: {{ M.flag }} <span class="ms-1">· org-wide</span></div>
    <div v-if="toggleErr" class="text-[11px] text-[#c0392b] mb-2">{{ toggleErr }}</div>

    <!-- Loading -->
    <div v-if="loading" class="rounded-lg border border-[#eee] bg-[#fafafa] px-6 py-10 text-center text-sm text-[#6b6b6b] mt-3">
      Loading…
    </div>

    <template v-else>
      <!-- Stat strip -->
      <div v-if="data?.stats?.length" class="flex gap-3 mb-4 mt-3">
        <div v-for="s in data.stats" :key="s.l" class="flex-1 bg-[#FBF4EF] border border-[#f0ddd0] rounded-[10px] px-3.5 py-2.5">
          <div class="text-xl font-bold text-[#1f2328]">{{ s.n }}</div>
          <div class="text-[10px] text-[#8A4527] uppercase tracking-wide">{{ s.l }}</div>
        </div>
      </div>

      <!-- Data table -->
      <div v-if="data?.table?.rows?.length" class="bg-white border border-[#E7E5DD] rounded-xl p-4 mb-4 mt-3">
        <h3 class="text-[11.5px] font-bold uppercase tracking-wide text-[#6b6b6b] mb-3">{{ data.table.title }}</h3>
        <table class="w-full text-[12px]">
          <thead>
            <tr>
              <th v-for="h in data.table.head" :key="h" class="text-left text-[10px] uppercase tracking-wide text-[#9a958c] font-bold py-1.5 px-2 border-b border-[#E7E5DD]">{{ h }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in data.table.rows" :key="i">
              <td v-for="(cell, j) in row" :key="j" class="py-2 px-2 border-b border-[#f1efe9]" :class="j === 0 ? 'font-mono text-[11.5px]' : ''">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Note / empty state -->
      <div v-if="data?.note" class="text-[12px] text-[#555] bg-[#faf8f4] border-l-[3px] border-[#C2683F] rounded-r-lg px-3.5 py-2.5 mt-3">
        {{ data.note }}
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useMyFetch } from '~/composables/useMyFetch'

interface Props {
  studioId?: string
  sources?: any[]
  canEdit?: boolean
  forceLayer?: string
}
const props = withDefaults(defineProps<Props>(), {
  studioId: '', sources: () => [], canEdit: false, forceLayer: 'profiler',
})

// Static per-layer metadata (glyph/title/desc/flag). Live status + data are fetched.
const META: Record<string, any> = {
  profiler: { glyph: '&#9638;', title: 'Deep Profiler', role: '🤖 agent', flag: 'HYBRID_PROFILE_V2',
    sub: 'Per-column role catalog + value distribution + variant detection',
    desc: 'Classifies every column into a role (DIMENSION / STATE / MEASURE / IDENTIFIER / TEMPORAL), grabs top-3 values + frequency, and flags near-duplicate variants. Stored as profile_v2 and injected as an 80-char/column catalog.' },
  codeenrich: { glyph: '{ }', title: 'Code Enrich', role: '🤖 agent', flag: 'HYBRID_CODE_ENRICH',
    sub: 'Grain & formulas from source — "meaning lives in code"',
    desc: 'Reads view/table DDL + saved-query SQL, then an LLM extracts grain, derived-column formulas, and included/excluded population into pipeline_logic. File sources derive grain from Deep Profiler.' },
  metrics: { glyph: '&#128274;', title: 'Verified Metrics', role: '✅ review', flag: 'HYBRID_VERIFIED_METRICS',
    sub: 'Locked, executable definitions — one truth, drift-tracked',
    desc: 'A locked metric runs its own read-only sql_calc and returns the value, overriding any formula the agent improvises. Marked AUTHORITATIVE in the prompt; drift computed vs the previous run.' },
  lazy: { glyph: '&#8635;', title: 'Lazy Profile / Drift', role: '🤖 agent', flag: 'HYBRID_PROFILE_V2',
    sub: 'Zero-touch schema drift — auto-profiles new tables at query time',
    desc: 'A table added after training has no catalog. On a cache-miss it profiles the table inline (~1.4s cold, 0.1s warm), caches it, and refreshes the prompt — so the next answer is correct.' },
  insights: { glyph: '&#9672;', title: 'Proactive Insights', role: '👤 user', flag: 'HYBRID_PROACTIVE_INSIGHTS',
    sub: 'Anomaly + trend scan on every result',
    desc: 'After each result, scans numeric columns with z-score + IQR and runs a temporal spike detector. Up to 5 insights rendered as chips under the answer. No LLM, fail-soft.' },
  forecast: { glyph: '&#128200;', title: 'Forecasting', role: '👤 user', flag: 'HYBRID_FORECAST',
    sub: 'Prophet time-series tool the agent can call',
    desc: 'Adds a forecast_df tool: feed a date column + value column, get back yhat / lower / upper for N future periods. Prophet is lazy-imported; the tool is hidden from the planner when off.' },
  golden: { glyph: '&#9733;', title: 'Golden Queries', role: '✅ review', flag: 'HYBRID_GOLDEN_QUERIES',
    sub: 'Promote proven queries — ranked first for reuse',
    desc: 'A learned query becomes GOLDEN on a thumbs-up or after it succeeds verified_count ≥ 2 times. Golden queries are injected first into the codegen prompt so the agent reuses known-good SQL.' },
  search: { glyph: '&#8853;', title: 'Hybrid Search + Knowledge Graph', role: '🤖 agent', flag: 'HYBRID_SEMANTIC_SEARCH',
    sub: 'pgvector + BM25 RRF search + entity graph (scaffold)',
    desc: 'Indexes tables / metrics / queries / docs into knowledge_search_index, searches via full-text + token-Jaccard fused with Reciprocal Rank Fusion, and links entities into a knowledge graph. Currently scaffolding.' },
}

const M = computed(() => META[props.forceLayer] || META.profiler)

const data = ref<any>(null)
const loading = ref(false)
const enabled = ref(false)
const toggling = ref(false)
const toggleErr = ref('')

async function loadLayer() {
  loading.value = true
  try {
    const sid = encodeURIComponent(props.studioId || '')
    const { data: d, error } = await useMyFetch<any>(
      `/intelligence/layer/${props.forceLayer}?studio_id=${sid}`, { method: 'GET' }
    )
    if (error.value) throw error.value
    data.value = d.value || null
    enabled.value = !!(d.value && d.value.enabled)
  } catch {
    data.value = { note: 'Data temporarily unavailable.' }
  } finally {
    loading.value = false
  }
}

async function toggle() {
  if (!props.canEdit || toggling.value) return
  toggleErr.value = ''
  toggling.value = true
  const next = !enabled.value
  try {
    const { error } = await useMyFetch(`/organization/hybrid-flags/${M.value.flag}`, {
      method: 'PUT', body: { enabled: next },
    })
    if (error.value) throw error.value
    enabled.value = next
    // refresh data now that the flag changed
    await loadLayer()
  } catch {
    toggleErr.value = 'Could not change the flag (needs manage_settings).'
  } finally {
    toggling.value = false
  }
}

watch(() => props.forceLayer, () => loadLayer())
onMounted(loadLayer)
</script>
