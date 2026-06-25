<template>
  <!-- navLayout 'left' = vertical sub-nav rail beside full-width content (Knowledge
       page). Default 'top' = the original horizontal tab bar (unchanged for every
       embed: Studio Queries, data-agent Knowledge, etc). -->
  <div :class="navLayout === 'left' ? 'flex items-stretch min-h-[calc(100vh-3rem)]' : ''">

    <!-- Shared hidden file input for "Upload data" (auto-train) -->
    <input ref="fileInput" type="file" accept=".csv,.tsv,.txt,.xlsx,.xls" class="hidden" @change="onAutotrainFile" />

    <!-- LEFT RAIL nav: anchored full-height panel, flush to the edge, stays on
         scroll. Neutral (gray) active state — no accent colour. -->
    <aside
      v-if="navLayout === 'left' && !hideNav"
      class="w-56 shrink-0 bg-gray-50 border-e border-gray-200 sticky top-12 self-start h-[calc(100vh-3rem)] overflow-y-auto flex flex-col"
    >
      <div v-if="title" class="px-4 pt-5 pb-3">
        <h1 class="text-base font-semibold text-gray-900">{{ title }}</h1>
        <p v-if="subtitle" class="mt-1 text-xs text-gray-500 leading-snug">{{ subtitle }}</p>
      </div>
      <nav class="px-2 flex flex-col gap-0.5">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="[
            'flex items-center gap-1.5 px-3 py-2 rounded-md text-sm text-left transition-colors',
            activeTab === tab.id
              ? 'bg-gray-200/70 text-gray-900 font-medium'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          ]"
        >
          {{ tab.label }}
          <span
            v-if="tab.id === 'review' && pendingCount > 0"
            class="ml-auto inline-flex items-center justify-center min-w-[18px] h-4 px-1 rounded-full bg-gray-200 text-gray-600 text-[10px] font-semibold"
          >{{ pendingCount }}</span>
        </button>
      </nav>
      <div v-if="dataSourceId" class="mt-auto p-3 flex flex-col gap-2">
        <UButton
          size="2xs"
          variant="soft"
          color="gray"
          icon="i-heroicons-sparkles"
          :loading="suggesting"
          block
          @click="aiSuggest"
        >AI-suggest</UButton>
        <UButton
          size="2xs"
          variant="soft"
          color="gray"
          icon="i-heroicons-arrow-up-tray"
          :loading="autotrainBusy"
          block
          @click="fileInput?.click()"
        >Upload data</UButton>
        <UButton
          size="2xs"
          variant="soft"
          color="gray"
          icon="i-heroicons-bolt"
          :loading="autotrainBusy"
          block
          @click="autotrainConnector"
        >Auto-train tables</UButton>
      </div>
    </aside>

    <!-- CONTENT (shared by both layouts) -->
    <div :class="navLayout === 'left' ? 'flex-1 min-w-0 px-6 py-6' : ''">

    <!-- TOP tab bar + AI-suggest (default layout only) -->
    <div v-if="navLayout !== 'left'" :class="['flex items-end justify-between gap-3 mb-6', hideNav ? 'justify-end' : 'border-b border-gray-200']">
      <div v-if="!hideNav" class="flex items-center gap-1">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="[
            'px-4 py-2 text-xs font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5',
            activeTab === tab.id
              ? 'border-[#C2683F] text-[#C2683F]'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          {{ tab.label }}
          <span
            v-if="tab.id === 'review' && pendingCount > 0"
            class="inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-[#F4E5DA] text-[#A8542F] text-[10px] font-semibold"
          >{{ pendingCount }}</span>
        </button>
      </div>

      <!-- AI-suggest + Upload data (only when a concrete data source is pinned) -->
      <div v-if="dataSourceId" class="pb-1.5 flex items-center gap-2">
        <UButton
          size="2xs"
          variant="soft"
          color="gray"
          icon="i-heroicons-sparkles"
          :loading="suggesting"
          @click="aiSuggest"
        >AI-suggest</UButton>
        <UButton
          size="2xs"
          variant="soft"
          color="gray"
          icon="i-heroicons-arrow-up-tray"
          :loading="autotrainBusy"
          @click="fileInput?.click()"
        >Upload data</UButton>
        <UButton
          size="2xs"
          variant="soft"
          color="gray"
          icon="i-heroicons-bolt"
          :loading="autotrainBusy"
          @click="autotrainConnector"
        >Auto-train tables</UButton>
      </div>
    </div>

    <!-- AI-suggest result note -->
    <div
      v-if="suggestNote"
      :class="[
        'mb-4 rounded-md border px-3 py-2 text-xs flex items-start gap-2',
        suggestError
          ? 'border-red-100 bg-red-50 text-red-700'
          : 'border-[#E8C9B5] bg-[#F6EFEA] text-[#A8542F]'
      ]"
    >
      <Icon
        :name="suggestError ? 'heroicons:exclamation-triangle' : 'heroicons:sparkles'"
        class="w-3.5 h-3.5 shrink-0 mt-0.5"
      />
      <span>{{ suggestNote }}</span>
      <button class="ml-auto text-current opacity-60 hover:opacity-100" @click="suggestNote = ''">
        <Icon name="heroicons:x-mark" class="w-3.5 h-3.5" />
      </button>
    </div>

    <!-- Tabs -->
    <SemanticTab v-if="effectiveTab === 'semantic'" :dataSourceId="dataSourceId" />
    <MetricsTab v-else-if="effectiveTab === 'metrics'" :dataSourceId="dataSourceId" />
    <QueriesTab v-else-if="effectiveTab === 'queries'" :dataSourceId="dataSourceId" />
    <AssetsTab v-else-if="effectiveTab === 'assets'" :dataSourceId="dataSourceId" />
    <ReviewTab
      v-else-if="effectiveTab === 'review' && !hideReview"
      :key="reviewRefreshKey"
      :dataSourceId="dataSourceId"
      @count="pendingCount = $event"
    />
    <div
      v-else-if="effectiveTab === 'review' && hideReview"
      class="py-10 text-center text-xs text-[#9a958c]"
    >
      You don't have access to the review queue for this source.
    </div>
    </div><!-- /content -->
  </div>
</template>

<script setup lang="ts">
import { useMyFetch } from '~/composables/useMyFetch'
// Explicit imports: these siblings live in components/knowledge/, so Nuxt
// auto-registers them as <KnowledgeSemanticTab> etc. (path prefix). Referencing
// them by bare name in the template would silently resolve to nothing — blank
// tab, no fetch, no error. Importing here binds the bare tags to the real
// components regardless of auto-import naming.
import SemanticTab from './SemanticTab.vue'
import MetricsTab from './MetricsTab.vue'
import QueriesTab from './QueriesTab.vue'
import AssetsTab from './AssetsTab.vue'
import ReviewTab from './ReviewTab.vue'

interface Props { dataSourceId?: string; hideReview?: boolean; navLayout?: 'top' | 'left'; title?: string; subtitle?: string; forceTab?: string; hideNav?: boolean }
const props = withDefaults(defineProps<Props>(), { dataSourceId: '', hideReview: false, navLayout: 'top', title: '', subtitle: '', forceTab: '', hideNav: false })

const ALL_TABS = [
  { id: 'semantic', label: 'Semantic' },
  { id: 'metrics', label: 'Metrics' },
  { id: 'queries', label: 'Queries' },
  { id: 'assets', label: 'Assets' },
  { id: 'review', label: 'Review' },
]

const tabs = computed(() =>
  props.hideReview ? ALL_TABS.filter(t => t.id !== 'review') : ALL_TABS
)

const activeTab = ref('semantic')
const pendingCount = ref(0)

// When forceTab is supplied (single sub-tab rail mode) it overrides the internal
// activeTab; otherwise the internal tab bar drives the active tab as before.
const effectiveTab = computed(() => props.forceTab || activeTab.value)

// --- AI-suggest ---
const suggesting = ref(false)
const suggestNote = ref('')
const suggestError = ref(false)
const reviewRefreshKey = ref(0)

// --- Upload data (auto-train) ---
const fileInput = ref<HTMLInputElement | null>(null)
const autotrainBusy = ref(false)

async function aiSuggest() {
  if (!props.dataSourceId || suggesting.value) return
  suggesting.value = true
  suggestNote.value = ''
  suggestError.value = false
  try {
    const { data, error } = await useMyFetch<any>(
      `/knowledge/ai-suggest/${props.dataSourceId}`,
      { method: 'POST', body: { focus: 'both' } }
    )
    if (error.value) throw error.value
    const payload = data.value || {}
    if (payload.disabled) {
      suggestError.value = true
      suggestNote.value = 'AI-suggest is disabled (enable HYBRID_SEMANTIC_LAYER / HYBRID_METRICS_CATALOG).'
      return
    }
    const counts = payload.counts || {}
    const sem = counts.semantics ?? 0
    const met = counts.metrics ?? 0
    suggestNote.value = `Proposed ${sem} semantic + ${met} metric suggestions — review in the Review tab.`
    // Force ReviewTab to reload, then surface it (when not hidden).
    reviewRefreshKey.value += 1
    if (!props.hideReview) activeTab.value = 'review'
  } catch (e: any) {
    suggestError.value = true
    suggestNote.value = e?.data?.detail || e?.message || 'AI-suggest failed. Please try again.'
  } finally {
    suggesting.value = false
  }
}

function onAutotrainFile(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) autotrainUpload(file)
  target.value = ''
}

async function autotrainUpload(file: File) {
  if (!props.dataSourceId || autotrainBusy.value) return
  autotrainBusy.value = true
  suggestNote.value = ''
  suggestError.value = false
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('data_source_id', props.dataSourceId)
    // upload
    const up = await useMyFetch<any>('/files', { method: 'POST', body: fd })
    if (up.error?.value) { suggestError.value = true; suggestNote.value = 'Upload failed.'; return }
    const fileId = up.data.value?.id
    if (!fileId) { suggestError.value = true; suggestNote.value = 'Upload failed.'; return }
    // autotrain
    const r = await useMyFetch<any>('/autotrain/from-file', {
      method: 'POST',
      body: { file_id: fileId, data_source_id: props.dataSourceId, load_key: 'replace' },
    })
    if (r.error?.value) {
      const code = r.error.value?.statusCode || r.error.value?.status
      suggestError.value = true
      suggestNote.value = code === 403
        ? 'Auto-train is disabled (ask an admin to enable HYBRID_AUTOTRAIN).'
        : 'Auto-train failed: ' + (r.error.value?.data?.detail || 'unknown error')
      return
    }
    const res = r.data.value || {}
    // res shape: { ok, tables, rows, results: [{ table, autotrain: { semantics:[], metrics:[], qa } }] }
    const first = (res.results || [])[0] || {}
    const at = first.autotrain || {}
    const sem = (at.semantics || []).length, met = (at.metrics || []).length, qa = at.qa || 0
    // quarantine is per-result (res.results[0].quarantined), never a top-level field.
    const quarantined = !!first.quarantined
    suggestError.value = !res.ok || quarantined
    if (quarantined) {
      suggestNote.value = 'File quarantined (schema drift or low quality) — not trained.'
    } else if (!res.ok) {
      suggestNote.value = 'Auto-train produced no tables.'
    } else if (res.degraded) {
      // backend ingested the data but knowledge proposals failed / produced nothing.
      suggestError.value = true
      suggestNote.value = 'Ingested, but knowledge proposals failed — check with an admin.'
    } else {
      suggestNote.value = `Auto-trained "${first.table || 'table'}" (${res.rows || 0} rows): ${sem} semantic + ${met} metrics + ${qa} verified Q&A proposed — review in the Review tab.`
    }
    // Force ReviewTab to reload, then surface it (when not hidden).
    reviewRefreshKey.value += 1
    if (!props.hideReview) activeTab.value = 'review'
  } catch (e: any) {
    suggestError.value = true
    suggestNote.value = e?.data?.detail || e?.message || 'Auto-train failed. Please try again.'
  } finally {
    autotrainBusy.value = false
  }
}

async function autotrainConnector() {
  if (!props.dataSourceId || autotrainBusy.value) return
  autotrainBusy.value = true
  suggestNote.value = ''
  suggestError.value = false
  try {
    const r = await useMyFetch<any>('/autotrain/from-connector', {
      method: 'POST',
      body: { data_source_id: props.dataSourceId, max_tables: 25 },
    })
    if (r.error?.value) {
      const code = r.error.value?.statusCode || r.error.value?.status
      suggestError.value = true
      suggestNote.value = code === 403
        ? 'Auto-train is disabled (enable HYBRID_AUTOTRAIN).'
        : 'Auto-train failed: ' + (r.error.value?.data?.detail || 'unknown error')
      return
    }
    const res = r.data.value || {}
    const results = res.results || []
    const sem = results.reduce((a,x)=>a+((x.semantics||[]).length),0)
    const met = results.reduce((a,x)=>a+((x.metrics||[]).length),0)
    const qa  = results.reduce((a,x)=>a+(x.qa||0),0)
    suggestNote.value = res.ok
      ? `Auto-trained ${res.tables||results.length} table(s): ${sem} semantic + ${met} metrics + ${qa} verified Q&A proposed — review in the Review tab.`
      : 'Auto-train produced no proposals.'
    suggestError.value = !res.ok
    reviewRefreshKey.value += 1
    if (!props.hideReview) activeTab.value = 'review'
  } catch (e:any) {
    suggestError.value = true
    suggestNote.value = e?.data?.detail || e?.message || 'Auto-train failed. Please try again.'
  } finally {
    autotrainBusy.value = false
  }
}
</script>
