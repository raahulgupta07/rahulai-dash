<template>
  <!-- Overlay -->
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30" @click.self="emit('close')">
    <div class="w-full max-w-2xl max-h-[90vh] flex flex-col rounded-2xl border border-[#E7E5DD] bg-white shadow-lg overflow-hidden">
      <!-- Header -->
      <div class="flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-[#E7E5DD]">
        <div>
          <h2
            class="text-[17px] font-semibold text-[#1f2328]"
            style="font-family: ui-serif, Georgia, 'Times New Roman', serif"
          >Use template</h2>
          <p class="text-xs text-[#9a958c] mt-0.5">{{ templateName || 'Bind to your data' }}</p>
        </div>
        <button
          type="button"
          aria-label="Close"
          class="w-7 h-7 inline-flex items-center justify-center rounded-md text-[#9a958c] hover:text-[#1f2328] hover:bg-[#F4F1EA] transition-colors cursor-pointer"
          @click="emit('close')"
        >
          <UIcon name="i-heroicons-x-mark" class="w-4 h-4" />
        </button>
      </div>

      <!-- Stepper -->
      <div class="flex items-center gap-1.5 px-5 py-3 border-b border-[#E7E5DD] bg-[#FBFAF6]">
        <template v-for="(s, i) in steps" :key="s.n">
          <div
            class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors"
            :class="step === s.n
              ? 'bg-[#C2683F] text-white'
              : step > s.n
                ? 'bg-[#F3E7DF] text-[#A8542F] border border-[#E8C9B5]'
                : 'bg-[#F4F1EA] text-[#9a958c] border border-[#E7E5DD]'"
          >
            <UIcon v-if="step > s.n" name="i-heroicons-check" class="w-3.5 h-3.5" />
            <span v-else class="font-mono">{{ s.n }}</span>
            {{ s.label }}
          </div>
          <UIcon
            v-if="i < steps.length - 1"
            name="i-heroicons-chevron-right"
            class="w-3.5 h-3.5 text-[#cfcabf]"
          />
        </template>
      </div>

      <!-- Body -->
      <div class="flex-1 overflow-y-auto px-5 py-4">
        <!-- STEP 1: pick data -->
        <div v-if="step === 1">
          <p class="text-[13px] text-[#6b6b6b] mb-3">Pick the data source(s) this agent should use.</p>

          <div v-if="dsLoading" class="space-y-2">
            <div v-for="n in 3" :key="n" class="animate-pulse h-12 bg-[#F4F1EA] rounded-lg" />
          </div>

          <div v-else-if="dataSources.length" class="space-y-2">
            <button
              v-for="ds in dataSources"
              :key="ds.id"
              type="button"
              class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border text-left transition-colors cursor-pointer"
              :class="dataSourceIds.includes(ds.id)
                ? 'border-[#C2683F] bg-[#F3E7DF]'
                : 'border-[#E7E5DD] bg-white hover:bg-[#F4F1EA]'"
              @click="toggleDataSource(ds.id)"
            >
              <span
                class="w-5 h-5 rounded-md border flex items-center justify-center flex-none"
                :class="dataSourceIds.includes(ds.id) ? 'bg-[#C2683F] border-[#C2683F]' : 'border-[#E7E5DD] bg-white'"
              >
                <UIcon v-if="dataSourceIds.includes(ds.id)" name="i-heroicons-check" class="w-3.5 h-3.5 text-white" />
              </span>
              <span class="text-sm text-[#1f2328] truncate">{{ ds.name || ('Source ' + ds.id) }}</span>
            </button>
          </div>

          <div v-else class="text-center py-10 text-sm text-[#9a958c]">
            No data sources connected yet.
          </div>
        </div>

        <!-- STEP 2: bind columns -->
        <div v-else-if="step === 2">
          <p class="text-[13px] text-[#6b6b6b] mb-3">
            Map each required role to a column in your data. Auto-matched rows are pre-filled.
          </p>

          <div v-if="previewLoading" class="space-y-2">
            <div v-for="n in 3" :key="n" class="animate-pulse h-12 bg-[#F4F1EA] rounded-lg" />
          </div>

          <div v-else-if="requiresColumns.length" class="space-y-2.5">
            <div
              v-for="(rc, i) in requiresColumns"
              :key="i"
              class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg border border-[#E7E5DD] bg-white"
            >
              <!-- left: role + as -->
              <div class="flex items-center gap-1.5 flex-none w-[40%] min-w-0">
                <div class="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-[#F3E7DF] border border-[#E8C9B5] min-w-0">
                  <span class="font-mono text-[11px] font-medium text-[#A8542F] truncate">{{ rc.role }}</span>
                </div>
                <span class="font-mono text-[11px] text-[#6b6b6b] truncate">{{ rc.as }}</span>
              </div>

              <UIcon name="i-heroicons-arrow-long-right" class="w-4 h-4 text-[#9a958c] flex-none" />

              <!-- right: column picker -->
              <div class="flex-1 min-w-0">
                <select
                  v-if="columnOptions.length"
                  v-model="columnMap[rc.as]"
                  class="w-full px-2.5 py-1.5 text-[13px] rounded-lg border border-[#E7E5DD] bg-white text-[#1f2328] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C2683F]"
                >
                  <option value="">— pick a column —</option>
                  <option v-for="col in columnOptions" :key="col" :value="col">{{ col }}</option>
                </select>
                <input
                  v-else
                  v-model="columnMap[rc.as]"
                  type="text"
                  placeholder="column name"
                  class="w-full px-2.5 py-1.5 text-[13px] rounded-lg border border-[#E7E5DD] bg-white text-[#1f2328] placeholder:text-[#9a958c] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C2683F]"
                />
              </div>

              <!-- status pill -->
              <span
                v-if="needsUser.includes(rc.as)"
                class="flex-none inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#F3E7DF] text-[#A8542F] border border-[#E8C9B5]"
              >needs you</span>
              <span
                v-else-if="columnMap[rc.as]"
                class="flex-none inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#eef6f0] text-[#3f9e6a] border border-[#d7ebde]"
              >
                <UIcon name="i-heroicons-check" class="w-3 h-3" />auto-matched
              </span>
            </div>
          </div>

          <div v-else class="text-center py-10 text-sm text-[#9a958c]">
            This template needs no column binding.
          </div>
        </div>

        <!-- STEP 3: review -->
        <div v-else-if="step === 3">
          <p class="text-[13px] text-[#6b6b6b] mb-4">
            Rules, metrics and example questions are added as
            <span class="font-medium text-[#A8542F]">PENDING</span> — they go live only after you approve
            them. Nothing is auto-applied.
          </p>

          <div class="grid grid-cols-3 gap-3 mb-4">
            <div class="bg-[#FBF4EF] border border-[#f0ddd0] rounded-xl px-3.5 py-2.5 text-center">
              <div class="text-xl font-bold text-[#1f2328]">{{ dataSourceIds.length }}</div>
              <div class="text-[10px] text-[#8A4527] uppercase tracking-wide">Data sources</div>
            </div>
            <div class="bg-[#FBF4EF] border border-[#f0ddd0] rounded-xl px-3.5 py-2.5 text-center">
              <div class="text-xl font-bold text-[#1f2328]">{{ mappedCount }}</div>
              <div class="text-[10px] text-[#8A4527] uppercase tracking-wide">Columns mapped</div>
            </div>
            <div class="bg-[#FBF4EF] border border-[#f0ddd0] rounded-xl px-3.5 py-2.5 text-center">
              <div class="text-xl font-bold text-[#1f2328]">{{ unmappedCount }}</div>
              <div class="text-[10px] text-[#8A4527] uppercase tracking-wide">Still unmapped</div>
            </div>
          </div>

          <label class="block text-xs font-medium text-[#6b6b6b] mb-1">Agent name</label>
          <input
            v-model="agentName"
            type="text"
            placeholder="My new agent"
            class="w-full px-3 py-2 text-sm rounded-lg border border-[#E7E5DD] bg-white text-[#1f2328] placeholder:text-[#9a958c] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C2683F] mb-2"
          />

          <div
            v-if="unmappedCount > 0"
            class="rounded-lg border-l-[3px] border-[#C2683F] bg-[#faf8f4] px-3.5 py-2.5 text-[12px] text-[#555]"
          >
            {{ unmappedCount }} required column(s) are still unmapped — you can go back, or proceed and
            fill them in later in the new agent.
          </div>
        </div>

        <!-- STEP 4: build -->
        <div v-else-if="step === 4">
          <div v-if="!buildErr" class="text-center py-6">
            <div class="w-12 h-12 rounded-xl bg-[#F3E7DF] border border-[#E8C9B5] mx-auto flex items-center justify-center mb-3">
              <UIcon name="i-heroicons-sparkles" class="w-7 h-7 text-[#A8542F]" />
            </div>
            <p class="text-sm font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, serif">
              Ready to build
            </p>
            <p class="text-xs text-[#9a958c] mt-1 max-w-sm mx-auto">
              We'll create <span class="font-medium text-[#1f2328]">{{ agentName || 'your agent' }}</span>
              from this template with the bound columns and pending items.
            </p>
          </div>

          <div
            v-if="buildErr"
            class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600"
          >{{ buildErr }}</div>
        </div>
      </div>

      <!-- Footer nav -->
      <div class="flex items-center justify-between gap-2 px-5 py-3 border-t border-[#E7E5DD] bg-[#FBFAF6]">
        <button
          type="button"
          class="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border border-[#E7E5DD] text-[#1f2328] bg-white hover:bg-[#F4F1EA] transition-colors cursor-pointer"
          :class="step === 1 ? 'opacity-65 cursor-default' : ''"
          :disabled="step === 1"
          @click="back"
        >
          <UIcon name="i-heroicons-arrow-left" class="w-4 h-4" />
          Back
        </button>

        <button
          v-if="step < 4"
          type="button"
          class="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-xl bg-[#C2683F] text-white hover:bg-[#A8542F] transition-colors cursor-pointer"
          :class="!canNext ? 'opacity-65 cursor-default hover:bg-[#C2683F]' : ''"
          :disabled="!canNext"
          @click="next"
        >
          Next
          <UIcon name="i-heroicons-arrow-right" class="w-4 h-4" />
        </button>
        <button
          v-else
          type="button"
          :disabled="building"
          class="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-xl bg-[#C2683F] text-white hover:bg-[#A8542F] transition-colors cursor-pointer"
          :class="building ? 'opacity-65 cursor-default hover:bg-[#C2683F]' : ''"
          @click="instantiate"
        >
          <UIcon name="i-heroicons-sparkles" class="w-4 h-4" />
          {{ building ? 'Creating…' : 'Create my agent from template' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useMyFetch } from '~/composables/useMyFetch'

interface Props {
  templateId: string
  templateName?: string
  requiresColumns?: any[]
}
const props = withDefaults(defineProps<Props>(), {
  templateName: '',
  requiresColumns: () => [],
})
const emit = defineEmits<{ (e: 'close'): void }>()

const steps = [
  { n: 1, label: 'Pick data' },
  { n: 2, label: 'Bind columns' },
  { n: 3, label: 'Review' },
  { n: 4, label: 'Build' },
]

const step = ref(1)

// Step 1
const dataSources = ref<any[]>([])
const dsLoading = ref(false)
const dataSourceIds = ref<string[]>([])

// Step 2
const previewLoading = ref(false)
// columnMap is {as: col}; requiresColumns can be refined from the bind-preview response.
const columnMap = reactive<Record<string, string>>({})
const needsUser = ref<string[]>([])
const previewRequires = ref<any[]>([])
const columnOptions = ref<string[]>([])

// Step 3
const agentName = ref('')

// Step 4
const building = ref(false)
const buildErr = ref('')

// requiresColumns: prefer the bind-preview's (more accurate) list, else the prop.
const requiresColumns = computed<any[]>(() =>
  previewRequires.value.length ? previewRequires.value : (props.requiresColumns || [])
)

const mappedCount = computed(() =>
  requiresColumns.value.filter((rc: any) => !!columnMap[rc.as]).length
)
const unmappedCount = computed(() => requiresColumns.value.length - mappedCount.value)

const canNext = computed(() => {
  if (step.value === 1) return dataSourceIds.value.length > 0
  return true
})

function toggleDataSource(id: string) {
  const i = dataSourceIds.value.indexOf(id)
  if (i >= 0) dataSourceIds.value.splice(i, 1)
  else dataSourceIds.value.push(id)
}

async function loadDataSources() {
  dsLoading.value = true
  try {
    const { data, error } = await useMyFetch<any>('/data_sources', { method: 'GET' })
    if (error.value) throw error.value
    const d = data.value
    dataSources.value = Array.isArray(d) ? d : (Array.isArray(d?.data_sources) ? d.data_sources : [])
  } catch {
    dataSources.value = []
  } finally {
    dsLoading.value = false
  }
}

async function loadBindPreview() {
  previewLoading.value = true
  try {
    const dsId = encodeURIComponent(dataSourceIds.value[0] || '')
    const { data, error } = await useMyFetch<any>(
      `/templates/${encodeURIComponent(props.templateId)}/bind-preview?data_source_id=${dsId}`,
      { method: 'GET' }
    )
    if (error.value) throw error.value
    const d = data.value || {}

    // requires_columns (authoritative if present)
    previewRequires.value = Array.isArray(d.requires_columns) ? d.requires_columns : []
    needsUser.value = Array.isArray(d.needs_user) ? d.needs_user : []

    // prefill columnMap {as: col}
    const cm = d.column_map || {}
    for (const rc of requiresColumns.value) {
      if (columnMap[rc.as] === undefined) columnMap[rc.as] = ''
    }
    for (const k of Object.keys(cm)) {
      if (cm[k]) columnMap[k] = cm[k]
    }

    // Derive the target source's column list for the dropdown.
    // bind-preview exposes mapped columns via column_map values; fall back to none → text input.
    const cols = new Set<string>()
    for (const k of Object.keys(cm)) {
      if (cm[k]) cols.add(cm[k])
    }
    if (Array.isArray(d.columns)) {
      for (const c of d.columns) cols.add(typeof c === 'string' ? c : (c?.name || ''))
    }
    columnOptions.value = Array.from(cols).filter(Boolean).sort()
  } catch {
    // fail-soft: ensure every required role has a map key so inputs render
    for (const rc of requiresColumns.value) {
      if (columnMap[rc.as] === undefined) columnMap[rc.as] = ''
    }
    needsUser.value = []
    columnOptions.value = []
  } finally {
    previewLoading.value = false
  }
}

async function next() {
  if (!canNext.value) return
  const target = step.value + 1
  if (target === 2) await loadBindPreview()
  if (target === 3 && !agentName.value) {
    agentName.value = props.templateName || 'My new agent'
  }
  step.value = target
}

function back() {
  if (step.value > 1) step.value -= 1
}

async function instantiate() {
  if (building.value) return
  buildErr.value = ''
  building.value = true
  try {
    const cleanMap: Record<string, string> = {}
    for (const k of Object.keys(columnMap)) {
      if (columnMap[k]) cleanMap[k] = columnMap[k]
    }
    const { data, error } = await useMyFetch<any>(
      `/templates/${encodeURIComponent(props.templateId)}/instantiate`,
      {
        method: 'POST',
        body: {
          name: agentName.value || props.templateName || 'My new agent',
          data_source_ids: dataSourceIds.value,
          column_map: cleanMap,
        },
      }
    )
    if (error.value) throw error.value
    const studioId = data.value?.studio_id
    if (!studioId) throw new Error('no studio id')
    navigateTo(`/studios/${studioId}`)
  } catch {
    buildErr.value = 'Could not create the agent. Please check your bindings and try again.'
  } finally {
    building.value = false
  }
}

onMounted(loadDataSources)
</script>
