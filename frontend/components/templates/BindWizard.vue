<template>
  <!-- Modal popup launched from the gallery. Guided 5-step journey; no page nav. -->
  <div v-if="modelValue" class="fixed inset-0 z-50 flex items-center justify-center p-5" style="background:rgba(30,25,20,.45)" @click.self="close">
    <div class="bg-white rounded-[18px] w-[760px] max-w-full max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
      <!-- header -->
      <div class="flex items-center gap-3 px-6 py-4 border-b border-[#E7E5DD]">
        <div class="w-10 h-10 rounded-[10px] bg-[#FBF4EF] text-[#C2683F] flex items-center justify-center flex-none">
          <UIcon name="i-heroicons-square-3-stack-3d" class="w-5 h-5" />
        </div>
        <div class="min-w-0">
          <h2 class="text-[17px] font-semibold text-[#1f2328] truncate" style="font-family:ui-serif,Georgia,serif">Use “{{ tpl?.name || templateName || 'template' }}”</h2>
          <div class="text-[12px] text-[#9a958c] truncate">{{ tpl?.version ? 'v'+tpl.version : '' }}<span v-if="tpl?.author"> · by {{ tpl.author }}</span></div>
        </div>
        <button class="ml-auto text-[#9a958c] hover:text-[#6b6b6b] text-xl leading-none" @click="close">✕</button>
      </div>

      <!-- stepper -->
      <div class="flex gap-1.5 px-6 pt-3.5">
        <div v-for="s in visibleSteps" :key="s.key" class="flex-1 flex flex-col gap-1.5 items-center">
          <div class="w-full h-1 rounded" :class="stepClass(s.key)"></div>
          <div class="text-[11px] font-bold" :class="stepIdx(s.key) === activeIdx ? 'text-[#C2683F]' : stepIdx(s.key) < activeIdx ? 'text-[#2f9e6f]' : 'text-[#9a958c]'">{{ s.label }}</div>
        </div>
      </div>

      <!-- body -->
      <div class="px-6 py-4 overflow-auto flex-1">
        <!-- 1 PREVIEW -->
        <div v-if="step === 'preview'">
          <p class="text-[#6b6b6b] mt-0 text-[13px]">You'll get a new agent seeded with this playbook — on <b>your</b> data. What transfers:</p>
          <div v-if="loadingTpl" class="text-sm text-[#6b6b6b] py-6 text-center">Loading…</div>
          <template v-else>
            <div v-for="f in previewFeatures" :key="f.label" class="flex gap-2.5 py-2 border-b border-dashed border-[#eee] last:border-0 items-start">
              <div class="w-[22px] h-[22px] rounded-[7px] bg-[#FBF4EF] text-[#C2683F] flex items-center justify-center text-xs flex-none">{{ f.glyph }}</div>
              <div><b class="text-[13px]">{{ f.label }}</b><div class="text-[#6b6b6b] text-[12px]">{{ f.desc }}</div></div>
            </div>
            <div v-if="requiresColumns.length" class="mt-3.5 rounded-[10px] border border-[#E8C9B5] bg-[#FBF4EF] px-3 py-2.5">
              <div class="text-[11px] font-bold text-[#C2683F] uppercase mb-1.5">Needs these columns in your data</div>
              <div class="flex flex-wrap gap-1.5">
                <span v-for="r in requiresColumns" :key="r.as" class="text-[11px] font-medium px-2 py-1 rounded-full bg-white text-[#C2683F] border border-[#E8C9B5]">{{ r.role }} · {{ r.as }}</span>
              </div>
            </div>
            <div v-else class="mt-3.5 text-[12px] text-[#555] bg-[#faf8f4] border-l-[3px] border-[#C2683F] rounded-r-lg px-3 py-2.5">
              This template has no required columns — it'll seed rules &amp; skills you can use on any data.
            </div>
          </template>
        </div>

        <!-- 2 PICK DATA (3-way) -->
        <div v-else-if="step === 'data'">
          <p class="text-[#6b6b6b] mt-0 text-[13px]">Where's the data for this agent?</p>
          <label class="flex items-center gap-3 border rounded-[10px] px-3.5 py-3 my-2 cursor-pointer" :class="mode==='existing' ? 'border-[#C2683F] bg-[#FBF4EF]' : 'border-[#E7E5DD]'" @click="mode='existing'">
            <span class="w-[18px] h-[18px] rounded-full border-2 flex-none" :class="mode==='existing' ? 'border-[#C2683F] bg-[#C2683F] shadow-[inset_0_0_0_3px_#fff]' : 'border-[#ccc]'"></span>
            <div><b class="text-[13px]">Use an existing source</b><div class="text-[12px] text-[#9a958c]">Bind to data you've already connected.</div></div>
          </label>
          <div v-if="mode==='existing'" class="ml-9 mb-2 max-h-[180px] overflow-auto">
            <div v-if="loadingDs" class="text-[12px] text-[#9a958c] py-2">Loading sources…</div>
            <div v-else-if="!dataSources.length" class="text-[12px] text-[#9a958c] py-2">No sources yet — connect new or skip.</div>
            <label v-for="ds in dataSources" :key="ds.id" class="flex items-center gap-2.5 border rounded-lg px-3 py-2 my-1 cursor-pointer text-[13px]" :class="selectedDs===ds.id ? 'border-[#C2683F] bg-[#FBF4EF]' : 'border-[#E7E5DD]'" @click="selectDs(ds.id)">
              <span class="w-[15px] h-[15px] rounded-full border-2 flex-none" :class="selectedDs===ds.id ? 'border-[#C2683F] bg-[#C2683F] shadow-[inset_0_0_0_2px_#fff]' : 'border-[#ccc]'"></span>
              <UIcon name="i-heroicons-circle-stack" class="w-4 h-4 text-[#9a958c]" /> {{ ds.name || ds.id }}
            </label>
          </div>
          <label class="flex items-center gap-3 border rounded-[10px] px-3.5 py-3 my-2 cursor-pointer" :class="mode==='connect' ? 'border-[#C2683F] bg-[#FBF4EF]' : 'border-[#E7E5DD]'" @click="mode='connect'">
            <span class="w-[18px] h-[18px] rounded-full border-2 flex-none" :class="mode==='connect' ? 'border-[#C2683F] bg-[#C2683F] shadow-[inset_0_0_0_3px_#fff]' : 'border-[#ccc]'"></span>
            <div><b class="text-[13px]">Connect / upload new data</b><div class="text-[12px] text-[#9a958c]">Build the agent now, then connect a source or upload a file.</div></div>
          </label>
          <label class="flex items-center gap-3 border rounded-[10px] px-3.5 py-3 my-2 cursor-pointer" :class="mode==='skip' ? 'border-[#C2683F] bg-[#FBF4EF]' : 'border-[#E7E5DD]'" @click="mode='skip'">
            <span class="w-[18px] h-[18px] rounded-full border-2 flex-none" :class="mode==='skip' ? 'border-[#C2683F] bg-[#C2683F] shadow-[inset_0_0_0_3px_#fff]' : 'border-[#ccc]'"></span>
            <div><b class="text-[13px]">Skip for now — add data later</b><div class="text-[12px] text-[#9a958c]">Loads the playbook; bind columns when data arrives.</div></div>
          </label>
        </div>

        <!-- 3 MAP COLUMNS -->
        <div v-else-if="step === 'map'">
          <p class="text-[#6b6b6b] mt-0 text-[13px]">We auto-matched your columns. Fix anything marked <span class="text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#FBF4EF] text-[#C2683F]">needs you</span>.</p>
          <div v-if="loadingBind" class="text-sm text-[#6b6b6b] py-6 text-center">Matching…</div>
          <template v-else>
            <div v-for="r in requiresColumns" :key="r.as" class="grid grid-cols-[1fr_26px_1fr] gap-2 items-center my-2">
              <div class="border border-[#E8C9B5] bg-[#FBF4EF] rounded-[9px] px-3 py-2"><div class="text-[10px] text-[#C2683F] font-bold uppercase">{{ r.role }}</div>{{ r.as }}</div>
              <div class="text-[#C2683F] text-center font-bold">→</div>
              <div class="flex items-center gap-2">
                <select v-model="columnMap[r.as]" class="flex-1 border rounded-[9px] px-2.5 py-2 text-[13px] bg-white" :class="columnMap[r.as] ? 'border-[#E7E5DD]' : 'border-[#C2683F]'">
                  <option value="">— choose —</option>
                  <option v-for="c in columnOptions" :key="c" :value="c">{{ c }}</option>
                </select>
                <span v-if="columnMap[r.as]" class="text-[11px] font-medium px-2 py-1 rounded-full bg-[#eaf6f0] text-[#2f9e6f] flex-none">{{ autoMatched.includes(r.as) ? 'auto' : 'set' }}</span>
                <span v-else class="text-[11px] font-medium px-2 py-1 rounded-full bg-[#FBF4EF] text-[#C2683F] flex-none">needs you</span>
              </div>
            </div>
            <div class="mt-3 text-[12px] text-[#555] bg-[#faf8f4] border-l-[3px] border-[#C2683F] rounded-r-lg px-3 py-2.5">Rules, metrics &amp; examples get rewritten with your columns. Unmapped ones stay flagged so nothing breaks silently.</div>
          </template>
        </div>

        <!-- 4 REVIEW -->
        <div v-else-if="step === 'review'">
          <p class="text-[#6b6b6b] mt-0 text-[13px]">Name your agent. Everything lands <b>pending</b> for your approval — never auto-applied.</p>
          <label class="text-[11px] font-bold text-[#9a958c]">AGENT NAME</label>
          <input v-model="agentName" class="w-full border border-[#E7E5DD] rounded-[9px] px-3 py-2.5 text-[13px] mt-1.5 mb-3.5" placeholder="My agent" />
          <div v-for="f in previewFeatures" :key="f.label" class="flex gap-2.5 py-1.5 items-center text-[13px]">
            <div class="w-[22px] h-[22px] rounded-[7px] bg-[#FBF4EF] text-[#C2683F] flex items-center justify-center text-xs flex-none">{{ f.glyph }}</div>
            <div>{{ f.label }} <span class="text-[#9a958c]">→ pending</span></div>
          </div>
          <div class="flex gap-2.5 py-1.5 items-center text-[13px]">
            <div class="w-[22px] h-[22px] rounded-[7px] bg-[#FBF4EF] text-[#C2683F] flex items-center justify-center text-xs flex-none">🗄</div>
            <div>{{ mode==='existing' && selectedDs ? 'Data source linked' : 'No data yet — add it after (bind later)' }}</div>
          </div>
        </div>

        <!-- 5 BUILD / SUCCESS -->
        <div v-else-if="step === 'done'" class="text-center py-5">
          <div v-if="building" class="py-8">
            <Spinner class="h-8 w-8 mx-auto text-[#C2683F]" />
            <p class="text-[#6b6b6b] mt-3">Building your agent…</p>
          </div>
          <template v-else-if="builtStudioId">
            <div class="w-16 h-16 rounded-full bg-[#eaf6f0] text-[#2f9e6f] flex items-center justify-center text-3xl mx-auto mb-3.5">✓</div>
            <h2 class="text-lg font-semibold" style="font-family:ui-serif,Georgia,serif">Your agent is ready</h2>
            <p class="text-[#6b6b6b] max-w-[420px] mx-auto mt-1.5 text-[13px]">
              “{{ agentName }}” was created.
              <template v-if="mode==='existing' && selectedDs">Approve the pending items, then train.</template>
              <template v-else>Connect data to finish setup, then approve &amp; train.</template>
            </p>
          </template>
          <div v-else class="py-8 text-[#c0392b] text-sm">{{ buildError || 'Could not build the agent.' }}</div>
        </div>
      </div>

      <!-- footer -->
      <div class="flex items-center gap-2.5 px-6 py-3.5 border-t border-[#E7E5DD]">
        <button v-if="step !== 'preview' && step !== 'done'" class="text-[13px] font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3.5 py-2 hover:bg-[#faf8f3]" @click="prev">← Back</button>
        <span class="flex-1"></span>
        <span class="text-[12px] text-[#9a958c]">Step {{ activeIdx + 1 }} of {{ visibleSteps.length }}</span>
        <button
          class="text-[13px] font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-4 py-2 disabled:opacity-50"
          :disabled="building || (step==='map' && !allMapped)"
          @click="nextOrBuild"
        >{{ ctaLabel }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useMyFetch } from '~/composables/useMyFetch'

interface Props { modelValue: boolean; templateId: string; templateName?: string }
const props = withDefaults(defineProps<Props>(), { templateName: '' })
const emit = defineEmits(['update:modelValue'])

const tpl = ref<any>(null)
const loadingTpl = ref(false)
const requiresColumns = ref<any[]>([])
const previewFeatures = ref<any[]>([])

const mode = ref<'existing' | 'connect' | 'skip'>('skip')
const dataSources = ref<any[]>([])
const loadingDs = ref(false)
const selectedDs = ref('')

const loadingBind = ref(false)
const columnMap = ref<Record<string, string>>({})
const columnOptions = ref<string[]>([])
const autoMatched = ref<string[]>([])

const agentName = ref('')
const building = ref(false)
const builtStudioId = ref('')
const buildError = ref('')

const step = ref<'preview' | 'data' | 'map' | 'review' | 'done'>('preview')

const visibleSteps = computed(() => {
  const s: any[] = [
    { key: 'preview', label: '1 · Preview' },
    { key: 'data', label: '2 · Data' },
  ]
  if (mode.value === 'existing' && requiresColumns.value.length) s.push({ key: 'map', label: '3 · Map' })
  s.push({ key: 'review', label: (s.length + 1) + ' · Review' })
  s.push({ key: 'done', label: (s.length + 1) + ' · Build' })
  return s
})
const activeIdx = computed(() => visibleSteps.value.findIndex(s => s.key === step.value))
const stepIdx = (k: string) => visibleSteps.value.findIndex(s => s.key === k)
function stepClass(k: string) {
  const i = stepIdx(k)
  if (i === activeIdx.value) return 'bg-[#C2683F]'
  if (i < activeIdx.value) return 'bg-[#2f9e6f]'
  return 'bg-[#f1efe9]'
}
const allMapped = computed(() => requiresColumns.value.every(r => !!columnMap.value[r.as]))
const ctaLabel = computed(() => {
  if (step.value === 'review') return 'Create my agent →'
  if (step.value === 'done') return builtStudioId.value ? 'Open agent' : 'Close'
  return 'Continue →'
})

function close() { emit('update:modelValue', false) }

async function loadTemplate() {
  loadingTpl.value = true
  try {
    const { data } = await useMyFetch<any>(`/templates/${props.templateId}`, { method: 'GET' })
    const t = (data.value && (data.value.template || data.value)) || null
    tpl.value = t
    const m = (t && t.manifest) || {}
    requiresColumns.value = Array.isArray(m.requires_columns) ? m.requires_columns : (t?.requires_columns || [])
    agentName.value = t?.name ? `${t.name}` : 'New agent'
    previewFeatures.value = [
      { glyph: '✦', label: 'Rules', desc: 'How to answer — born pending for review.' },
      { glyph: '∑', label: 'Metric definitions', desc: 'Formulas + grain (not values).' },
      { glyph: '◈', label: 'Example patterns', desc: 'Question → method, generalized.' },
      { glyph: '⚙', label: `Skills (${(m.uses_skills || []).length})`, desc: 'Reusable analysis methods.' },
    ]
  } catch { tpl.value = null } finally { loadingTpl.value = false }
}

async function loadDataSources() {
  loadingDs.value = true
  try {
    const { data } = await useMyFetch<any>('/data_sources', { method: 'GET' })
    const d: any = data.value
    dataSources.value = Array.isArray(d) ? d : (d?.data_sources || [])
  } catch { dataSources.value = [] } finally { loadingDs.value = false }
}

function selectDs(id: string) { selectedDs.value = id }

async function loadBindPreview() {
  if (!selectedDs.value) return
  loadingBind.value = true
  try {
    const { data } = await useMyFetch<any>(`/templates/${props.templateId}/bind-preview?data_source_id=${encodeURIComponent(selectedDs.value)}`, { method: 'GET' })
    const d: any = data.value || {}
    const cm = d.column_map || {}
    columnMap.value = { ...cm }
    autoMatched.value = Object.keys(cm)
    const fromMap = [...(Object.values(cm) as string[])]
    columnOptions.value = Array.from(new Set([...fromMap, ...((d.columns as string[]) || [])]))
    if (Array.isArray(d.requires_columns) && d.requires_columns.length) requiresColumns.value = d.requires_columns
  } catch { /* manual map */ } finally { loadingBind.value = false }
}

function prev() {
  const order = visibleSteps.value.map(s => s.key)
  const i = order.indexOf(step.value)
  if (i > 0) step.value = order[i - 1]
}

async function nextOrBuild() {
  const order = visibleSteps.value.map(s => s.key)
  const i = order.indexOf(step.value)
  if (step.value === 'data' && mode.value === 'existing' && requiresColumns.value.length) {
    await loadBindPreview()
  }
  if (step.value === 'review') { await build(); return }
  if (step.value === 'done') {
    if (builtStudioId.value) navigateTo(`/studios/${builtStudioId.value}`)
    else close()
    return
  }
  if (i < order.length - 1) step.value = order[i + 1]
}

async function build() {
  building.value = true
  buildError.value = ''
  step.value = 'done'
  try {
    const body: any = {
      name: agentName.value || 'New agent',
      data_source_ids: mode.value === 'existing' && selectedDs.value ? [selectedDs.value] : [],
      column_map: mode.value === 'existing' ? columnMap.value : {},
    }
    const { data, error } = await useMyFetch<any>(`/templates/${props.templateId}/instantiate`, { method: 'POST', body })
    if (error.value) throw error.value
    const d: any = data.value || {}
    if (!d.ok || !d.studio_id) throw new Error(d.error || 'failed')
    builtStudioId.value = d.studio_id
  } catch (e: any) {
    buildError.value = 'Could not build the agent.'
  } finally {
    building.value = false
  }
}

watch(() => props.modelValue, (open) => {
  if (open) {
    step.value = 'preview'
    mode.value = 'skip'
    selectedDs.value = ''
    columnMap.value = {}
    builtStudioId.value = ''
    buildError.value = ''
    loadTemplate()
    loadDataSources()
  }
})
</script>
