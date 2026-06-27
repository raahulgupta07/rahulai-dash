<template>
  <div>
    <!-- Data source picker -->
    <div v-if="showPicker" class="flex items-center gap-3 mb-5">
      <label class="text-xs font-medium text-gray-500 shrink-0">Data source</label>
      <USelectMenu
        v-model="selectedDataSource"
        :options="dataSources"
        option-attribute="name"
        by="id"
        placeholder="Select a data source"
        size="sm"
        class="w-72"
        :loading="loadingSources"
        :disabled="!dataSources.length"
      />
      <span v-if="!loadingSources && !dataSources.length" class="text-xs text-gray-400">
        No data sources connected.
      </span>
    </div>

    <!-- Loading -->
    <div v-if="loading && !tables.length" class="rounded-lg border border-gray-100 bg-gray-50 px-6 py-12 text-center">
      <Icon name="heroicons:arrow-path" class="w-5 h-5 text-gray-400 animate-spin mx-auto mb-2" />
      <p class="text-sm text-gray-500">Loading semantic model&hellip;</p>
    </div>

    <!-- Unavailable / empty (graceful degrade) -->
    <div
      v-else-if="!activeDataSourceId"
      class="rounded-lg border border-gray-100 bg-gray-50 px-6 py-12 text-center"
    >
      <p class="text-sm text-gray-500">Select a data source to view its semantic model.</p>
    </div>
    <div
      v-else-if="errored"
      class="rounded-lg border border-amber-100 bg-amber-50 px-6 py-10 text-center"
    >
      <Icon name="heroicons:cloud" class="w-6 h-6 text-amber-400 mx-auto mb-2" />
      <p class="text-sm text-amber-700">Semantic model isn&rsquo;t available yet for this data source.</p>
      <p class="mt-1 text-xs text-amber-600">It will appear here once the knowledge service has indexed it.</p>
    </div>
    <div
      v-else-if="!tables.length"
      class="rounded-lg border border-gray-100 bg-gray-50 px-6 py-12 text-center"
    >
      <p class="text-sm text-gray-500">No tables described yet.</p>
    </div>

    <!-- Content -->
    <template v-else>
      <!-- Coverage header -->
      <div class="mb-5">
        <div class="flex items-center justify-between text-xs text-gray-500 mb-1.5">
          <span>
            <span class="font-medium text-gray-700">{{ stats.tables }}</span> tables
            &middot;
            <span class="font-medium text-gray-700">{{ stats.columns }}</span> columns
            &middot;
            <span class="font-medium text-gray-700">{{ describedPct }}%</span> described
          </span>
          <!-- AI-fill blank column meanings (mirrors KnowledgePanel's AI-suggest) -->
          <button
            v-if="activeDataSourceId"
            type="button"
            class="inline-flex items-center gap-1.5 rounded-lg border border-[#C2541E]/30 bg-[#C2541E]/5 px-3 py-1.5 text-xs font-medium text-[#C2541E] hover:bg-[#C2541E]/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            :disabled="suggestingColumns"
            @click="suggestColumnMeanings"
          >
            <Icon
              :name="suggestingColumns ? 'heroicons:arrow-path' : 'heroicons:tag'"
              :class="['w-4 h-4', suggestingColumns && 'animate-spin']"
            />
            {{ suggestingColumns ? 'Suggesting&hellip;' : 'Suggest column meanings' }}
          </button>
        </div>
        <div class="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
          <div
            class="h-full rounded-full bg-[#C2541E] transition-all duration-500"
            :style="{ width: describedPct + '%' }"
          />
        </div>
        <div class="mt-2 flex items-center gap-2 text-xs text-gray-400">
          <span>
            <span class="font-medium text-gray-600">{{ approvedCount }}</span> of
            <span class="font-medium text-gray-600">{{ tables.length }}</span> approved
          </span>
          <span class="text-gray-300">&middot;</span>
          <span>Approved tables are injected into the agent&rsquo;s context.</span>
        </div>
      </div>

      <!-- Table cards -->
      <div class="space-y-2.5">
        <SemanticTableCard
          v-for="table in tables"
          :key="table.id"
          :table="table"
          :on-patch-table="patchTable"
          :on-patch-column="patchColumn"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useMyFetch } from '~/composables/useMyFetch'
// Bind the bare <SemanticTableCard> tag explicitly: Nuxt registers this sibling
// as <KnowledgeSemanticTableCard> (path prefix), so the bare name would resolve
// to nothing. See the same note in KnowledgePanel.vue.
import SemanticTableCard from './SemanticTableCard.vue'

interface DataSource { id: string; name: string }
interface Column { id: string; name: string; type: string; meaning?: string; status?: string }
interface SemanticTable {
  id: string
  table_name: string
  description?: string
  use_cases?: string[]
  quality_notes?: string[]
  status?: string
  described?: boolean
  columns?: Column[]
}
interface Stats { tables: number; columns: number; described_pct: number }

interface Props { dataSourceId?: string }
const props = withDefaults(defineProps<Props>(), { dataSourceId: '' })
const pinnedDs = computed(() => props.dataSourceId || '')
const showPicker = computed(() => !pinnedDs.value)
const activeDataSourceId = computed(() => pinnedDs.value || selectedDataSource.value?.id || '')

const dataSources = ref<DataSource[]>([])
const selectedDataSource = ref<DataSource | null>(null)
const loadingSources = ref(false)

const tables = ref<SemanticTable[]>([])
const stats = ref<Stats>({ tables: 0, columns: 0, described_pct: 0 })
const loading = ref(false)
const errored = ref(false)
const suggestingColumns = ref(false)

// Nuxt UI toast (auto-imported); guarded so a missing toast never throws.
const toast = useToast()

const describedPct = computed(() => Math.round(stats.value?.described_pct ?? 0))
const approvedCount = computed(() => tables.value.filter(t => t.status === 'approved').length)

// --- load data sources for the picker ---
async function loadDataSources() {
  if (!showPicker.value) return
  loadingSources.value = true
  try {
    const { data, error } = await useMyFetch<DataSource[]>('/data_sources', { method: 'GET' })
    if (error.value) throw error.value
    dataSources.value = (data.value as DataSource[]) || []
    if (dataSources.value.length && !selectedDataSource.value) {
      selectedDataSource.value = dataSources.value[0]
    }
  } catch {
    dataSources.value = []
  } finally {
    loadingSources.value = false
  }
}

// --- load semantic model for the selected data source ---
async function loadSemantic() {
  if (!activeDataSourceId.value) {
    tables.value = []
    return
  }
  loading.value = true
  errored.value = false
  try {
    const { data, error } = await useMyFetch<any>(
      `/knowledge/semantic?data_source_id=${encodeURIComponent(activeDataSourceId.value)}`,
      { method: 'GET' }
    )
    if (error.value) throw error.value
    const payload = data.value
    if (!payload) throw new Error('empty')
    tables.value = (payload.tables as SemanticTable[]) || []
    stats.value = payload.stats || { tables: 0, columns: 0, described_pct: 0 }
  } catch {
    // Backend not ready / 404 / error -> degrade gracefully, never crash.
    tables.value = []
    stats.value = { tables: 0, columns: 0, described_pct: 0 }
    errored.value = true
  } finally {
    loading.value = false
  }
}

// --- PATCH table ---
async function patchTable(id: string, body: Record<string, any>): Promise<boolean> {
  try {
    const { error } = await useMyFetch(`/knowledge/semantic/table/${id}`, {
      method: 'PATCH',
      body,
    })
    if (error.value) throw error.value
    // Optimistic local update
    const t = tables.value.find(x => x.id === id)
    if (t) {
      Object.assign(t, body)
      if (body.description !== undefined) {
        t.described = !!(body.description && body.description.trim())
      }
    }
    return true
  } catch {
    return false
  }
}

// --- PATCH column ---
async function patchColumn(id: string, body: Record<string, any>): Promise<boolean> {
  try {
    const { error } = await useMyFetch(`/knowledge/semantic/column/${id}`, {
      method: 'PATCH',
      body,
    })
    if (error.value) throw error.value
    for (const t of tables.value) {
      const c = (t.columns || []).find(x => x.id === id)
      if (c) { Object.assign(c, body); break }
    }
    return true
  } catch {
    return false
  }
}

// --- AI-fill blank column meanings (Semantic Layer) ---
async function suggestColumnMeanings() {
  if (!activeDataSourceId.value || suggestingColumns.value) return
  suggestingColumns.value = true
  try {
    // BARE path — useMyFetch prepends /api + injects auth + X-Organization-Id.
    const { data, error } = await useMyFetch<any>(
      `/knowledge/ai-suggest-columns/${activeDataSourceId.value}`,
      { method: 'POST', body: {} }
    )
    if (error.value) throw error.value
    const payload: any = data.value || {}
    if (payload.disabled) {
      toast?.add?.({
        title: 'Semantic Layer is off',
        description: 'Enable the Semantic Layer feature to draft column meanings.',
        color: 'amber',
      })
      return
    }
    const n = payload?.counts?.columns ?? (payload?.proposed?.columns?.length ?? 0)
    // Re-fetch so the freshly drafted (pending) column meanings appear.
    await loadSemantic()
    toast?.add?.({
      title: `Drafted ${n} column meanings — review & approve`,
      color: 'green',
    })
  } catch {
    // Fail-soft: never throw to the user.
    toast?.add?.({ title: 'Could not suggest column meanings', color: 'red' })
  } finally {
    suggestingColumns.value = false
  }
}

watch([selectedDataSource, () => props.dataSourceId], () => loadSemantic())

onMounted(async () => {
  await loadDataSources()
  await loadSemantic()
})
</script>
