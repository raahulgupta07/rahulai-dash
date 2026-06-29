<template>
    <Teleport to="body">
        <div v-if="open" class="fixed inset-0 z-[120] flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8" @click.self="emitClose">
            <div class="w-full max-w-[1040px] bg-[#FAF9F8] rounded-2xl shadow-xl border border-[#ECECEC] overflow-hidden my-4">
                <!-- header -->
                <div class="flex items-center gap-3 px-5 py-4 border-b border-[#ECECEC] bg-white">
                    <div>
                        <h2 class="text-[18px] font-semibold text-[#1f2329]" style="font-family: 'Spectral', ui-serif, Georgia, serif">
                            <span class="text-[#C2541E]">&#10022;</span> Smart Upload
                        </h2>
                        <p class="text-[12px] text-[#6b7280] mt-0.5">Drop anything &mdash; data, glossary, rules, docs. It detects what each file is and routes it to the right home. You confirm or override.</p>
                    </div>
                    <span class="flex-1"></span>
                    <button type="button" class="text-[#9aa1ac] hover:text-[#6b7280]" @click="emitClose">
                        <UIcon name="i-heroicons-x-mark" class="w-5 h-5" />
                    </button>
                </div>

                <div class="px-5 py-4 max-h-[calc(100vh-180px)] overflow-y-auto">
                    <!-- drop zone -->
                    <div
                        class="border-[1.6px] border-dashed border-[#EAD8CD] bg-[#FFF6F1] rounded-2xl px-6 py-7 text-center cursor-pointer mb-4 transition-colors"
                        :class="dragging ? 'bg-[#FCEBE0] border-[#C2541E]' : ''"
                        @click="pick"
                        @dragover.prevent="dragging = true"
                        @dragleave.prevent="dragging = false"
                        @drop.prevent="onDrop"
                    >
                        <div class="text-[28px]">&#128229;</div>
                        <div class="font-semibold text-[#C2541E] mt-2 text-[15px]">Drop files here &mdash; or click to browse</div>
                        <div class="text-[12px] text-[#6b7280] mt-1">.csv .xlsx .pdf .docx .txt &middot; data, definitions, logic, references &mdash; mixed is fine</div>
                        <input ref="fileInput" type="file" multiple class="hidden" accept=".csv,.xlsx,.xls,.pdf,.docx,.txt" @change="onPick" />
                    </div>

                    <!-- error -->
                    <div v-if="error" class="mb-4 rounded-xl border border-[#f0c8b8] bg-[#FFF1EA] px-4 py-2.5 text-[12.5px] text-[#A8330F]">
                        {{ error }}
                    </div>

                    <!-- uploading / classifying spinner -->
                    <div v-if="busy" class="flex items-center gap-2.5 text-[12.5px] text-[#6b7280] py-6 justify-center">
                        <UIcon name="i-heroicons-arrow-path" class="w-4 h-4 animate-spin text-[#C2541E]" />
                        <span>{{ busyLabel }}</span>
                    </div>

                    <!-- result summary (after apply) -->
                    <div v-if="result" class="mb-4 rounded-xl border border-[#cfe7d5] bg-[#EEFAF1] px-4 py-3">
                        <div class="text-[13px] font-semibold text-[#157A43]">Routing applied &mdash; {{ result.applied }} file{{ result.applied === 1 ? '' : 's' }} placed{{ result.train_started ? ' &middot; training started' : '' }}</div>
                        <div class="text-[12px] text-[#3b4250] mt-1 flex flex-wrap gap-x-3 gap-y-1">
                            <span v-for="(n, dest) in resultByDest" :key="dest">{{ destMeta(dest).ic }} {{ n }} &rarr; {{ destMeta(dest).short }}</span>
                        </div>
                    </div>

                    <!-- banner + rows -->
                    <template v-if="items.length && !busy">
                        <div class="flex items-center gap-2 mb-3 mt-1">
                            <h3 class="text-[14px] font-semibold text-[#1f2329]" style="font-family: 'Spectral', ui-serif, Georgia, serif">Detected &amp; routed</h3>
                            <span class="flex-1"></span>
                            <span class="text-[11.5px] text-[#6b7280]">
                                <b class="text-[#1f2329]">{{ summary.auto }}</b> auto-routed &middot;
                                <b :class="summary.needs_confirm ? 'text-[#b45309]' : 'text-[#1f2329]'">{{ summary.needs_confirm }}</b> need a look
                            </span>
                        </div>

                        <div
                            v-for="(it, i) in items"
                            :key="it.file_id"
                            class="flex items-stretch border border-[#ECECEC] rounded-xl bg-white mb-2.5 overflow-hidden"
                            :class="it.dest === 'skip' ? 'opacity-50' : ''"
                        >
                            <!-- left: file + reason -->
                            <div class="flex-1 min-w-0 px-4 py-3">
                                <div class="font-semibold text-[13px] text-[#1f2329] flex items-center gap-2">
                                    <span>&#128196;</span>
                                    <span class="truncate">{{ it.filename }}</span>
                                    <span v-if="it.needs_confirm" class="text-[#b45309]" title="Uncertain — please confirm">&#9888;</span>
                                </div>
                                <div v-if="it.signals" class="text-[11.5px] text-[#9aa1ac] mt-0.5 truncate">{{ it.signals }}</div>
                                <div v-if="it.reason" class="text-[12px] text-[#6b7280] mt-2 bg-[#F4F3F1] rounded-lg px-2.5 py-1.5" v-html="it.reason"></div>
                            </div>

                            <!-- right: destination control -->
                            <div class="flex-none w-[300px] border-l border-[#ECECEC] px-4 py-3 bg-[#FCFBFA]">
                                <div class="text-[10px] font-bold uppercase tracking-wide text-[#9aa1ac] mb-1.5">Routed to</div>
                                <div class="relative">
                                    <select
                                        v-model="it.dest"
                                        class="w-full appearance-none text-[12.5px] font-semibold rounded-lg border border-[#E9E0D3] pl-3 pr-7 py-1.5 cursor-pointer focus:outline-none focus:border-[#C2541E]"
                                        :class="destMeta(it.dest).cls"
                                    >
                                        <option v-for="d in DESTS" :key="d" :value="d">{{ destMeta(d).ic }} {{ destMeta(d).label }}</option>
                                    </select>
                                    <UIcon name="i-heroicons-chevron-down" class="w-4 h-4 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-[#9aa1ac]" />
                                </div>

                                <!-- confidence bar -->
                                <div class="flex items-center gap-2 text-[11px] text-[#6b7280] mt-2">
                                    <span>{{ Math.round((it.confidence || 0) * pctScale) }}%</span>
                                    <span class="flex-1 h-1.5 rounded-full bg-[#eee] overflow-hidden">
                                        <span class="block h-full rounded-full" :class="confClass(it.confidence)" :style="{ width: confPct(it.confidence) + '%' }"></span>
                                    </span>
                                </div>

                                <button
                                    type="button"
                                    class="mt-2.5 text-[11px] font-semibold text-[#3b4250] border border-[#ECECEC] rounded-md px-2.5 py-1 hover:bg-[#F4F3F1]"
                                    @click="toggleSkip(it)"
                                >
                                    {{ it.dest === 'skip' ? 'Include' : 'Skip' }}
                                </button>
                            </div>
                        </div>
                    </template>

                    <div v-else-if="!busy && !items.length && !result" class="text-center text-[12px] text-[#9aa1ac] py-8">
                        No files yet &mdash; drop a few above to see where they&rsquo;ll be routed.
                    </div>
                </div>

                <!-- footer -->
                <div class="flex items-center gap-3 px-5 py-3.5 border-t border-[#ECECEC] bg-white">
                    <label class="inline-flex items-center gap-2 text-[12px] text-[#3b4250] cursor-pointer">
                        <input v-model="autoTrain" type="checkbox" class="accent-[#C2541E]" />
                        Auto-train after applying
                    </label>
                    <span class="flex-1"></span>
                    <span class="text-[12px] text-[#6b7280]"><b class="text-[#1f2329]">{{ keepCount }}</b> of {{ items.length }} routed</span>
                    <button type="button" class="text-[12.5px] font-semibold text-[#3b4250] bg-white border border-[#ECECEC] rounded-lg px-4 py-2 hover:bg-[#F4F3F1]" @click="emitClose">
                        Cancel
                    </button>
                    <button
                        type="button"
                        class="text-[13px] font-bold text-white bg-[#C2541E] hover:bg-[#A8330F] rounded-lg px-4 py-2 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        :disabled="!keepCount || applying || busy"
                        @click="apply"
                    >
                        <span v-if="applying">Applying&hellip;</span>
                        <span v-else>Apply routing &rarr;</span>
                    </button>
                </div>
            </div>
        </div>
    </Teleport>
</template>

<script setup lang="ts">
interface SmartItem {
    file_id: string
    filename: string
    dest: string
    confidence: number
    reason?: string
    needs_confirm?: boolean
    sink?: string
    signals?: string
}

const props = defineProps<{ studioId: string; dataSourceId?: string; open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'applied', summary: any): void }>()

const DESTS = ['database', 'semantic', 'instructions', 'examples', 'knowledge', 'skip']
const DEST_META: Record<string, { ic: string; label: string; short: string; cls: string }> = {
    database:     { ic: '🗄️', label: 'Database — data source',      short: 'Database',     cls: 'bg-[#eef2fe] text-[#2C53A8]' },
    semantic:     { ic: '🏷️', label: 'Semantic — column meanings',  short: 'Semantic',     cls: 'bg-[#F6F4FF] text-[#5A41A8]' },
    instructions: { ic: '📐', label: 'Instructions — rules',        short: 'Instructions', cls: 'bg-[#fffaf0] text-[#b45309]' },
    examples:     { ic: '🎓', label: 'Examples — Q→SQL',            short: 'Examples',     cls: 'bg-[#EEFAF1] text-[#157A43]' },
    knowledge:    { ic: '📚', label: 'Knowledge — RAG',             short: 'Knowledge',    cls: 'bg-[#e9f7f4] text-[#0d7a6b]' },
    skip:         { ic: '🚫', label: 'Skip — don’t import',         short: 'Skip',         cls: 'bg-[#f4f3f1] text-[#6b7280]' },
}
function destMeta(d: string) { return DEST_META[d] || DEST_META.skip }

const fileInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const classifying = ref(false)
const applying = ref(false)
const error = ref('')
const items = ref<SmartItem[]>([])
const summary = ref<{ auto: number; needs_confirm: number; total: number }>({ auto: 0, needs_confirm: 0, total: 0 })
const autoTrain = ref(true)
const result = ref<any>(null)

const busy = computed(() => uploading.value || classifying.value)
const busyLabel = computed(() => (uploading.value ? 'Uploading files…' : 'Classifying & routing…'))
const keepCount = computed(() => items.value.filter(it => it.dest !== 'skip').length)
// confidence may arrive as 0..1 or 0..100 — normalize for the bar + label.
const pctScale = computed(() => (items.value.some(it => (it.confidence || 0) > 1) ? 1 : 100))
function confPct(c: number) { return Math.max(0, Math.min(100, Math.round((c || 0) * pctScale.value))) }
function confClass(c: number) {
    const p = confPct(c)
    return p >= 90 ? 'bg-[#15803d]' : p >= 80 ? 'bg-[#b45309]' : 'bg-[#b91c1c]'
}
const resultByDest = computed(() => {
    const m: Record<string, number> = {}
    for (const r of (result.value?.results || [])) { if (r?.ok && r?.dest && r.dest !== 'skip') m[r.dest] = (m[r.dest] || 0) + 1 }
    return m
})

function emitClose() { emit('close') }
function pick() { fileInput.value?.click() }
function toggleSkip(it: SmartItem) {
    if (it.dest === 'skip') it.dest = (it as any)._prevDest || 'database'
    else { (it as any)._prevDest = it.dest; it.dest = 'skip' }
}

function onPick(e: Event) {
    const list = (e.target as HTMLInputElement).files
    if (list && list.length) handleFiles(Array.from(list))
    if (fileInput.value) fileInput.value.value = ''
}
function onDrop(e: DragEvent) {
    dragging.value = false
    const list = e.dataTransfer?.files
    if (list && list.length) handleFiles(Array.from(list))
}

async function handleFiles(files: File[]) {
    error.value = ''
    result.value = null
    uploading.value = true
    const fileIds: string[] = []
    try {
        for (const f of files) {
            const fd = new FormData()
            fd.append('file', f)
            // Mirror the page's upload idiom: POST /files (multipart, field `file`). useMyFetch adds auth + org headers + /api prefix.
            const { data, error: upErr } = await useMyFetch<any>('/files', { method: 'POST', body: fd })
            if (upErr?.value || !data?.value?.id) {
                error.value = (upErr?.value as any)?.data?.detail || `Could not upload “${f.name}”.`
                continue
            }
            fileIds.push((data.value as any).id)
        }
    } catch (e: any) {
        error.value = e?.data?.detail || e?.message || 'Upload failed.'
    } finally {
        uploading.value = false
    }
    if (fileIds.length) await classify(fileIds)
}

async function classify(fileIds: string[]) {
    classifying.value = true
    error.value = ''
    try {
        const body: any = { file_ids: fileIds }
        if (props.dataSourceId) body.data_source_id = props.dataSourceId
        const { data, error: clErr } = await useMyFetch<any>(`/studios/${props.studioId}/smart-upload/classify`, { method: 'POST', body })
        if (clErr?.value) {
            error.value = (clErr.value as any)?.data?.detail || 'Could not classify these files.'
            return
        }
        const res = data.value as any
        const incoming: SmartItem[] = res?.items || []
        // append so a second drop adds to the list
        items.value = [...items.value, ...incoming]
        const s = res?.summary || {}
        summary.value = {
            auto: items.value.filter(it => !it.needs_confirm).length,
            needs_confirm: items.value.filter(it => it.needs_confirm).length,
            total: items.value.length,
        }
        if (typeof s.auto === 'number' && incoming.length === items.value.length) summary.value = { auto: s.auto, needs_confirm: s.needs_confirm, total: s.total }
    } catch (e: any) {
        error.value = e?.data?.detail || e?.message || 'Classify failed.'
    } finally {
        classifying.value = false
    }
}

async function apply() {
    if (!keepCount.value || applying.value) return
    applying.value = true
    error.value = ''
    try {
        const payload: any = {
            items: items.value
                .filter(it => it.dest !== 'skip')
                .map(it => ({ file_id: it.file_id, dest: it.dest, filename: it.filename })),
            train: autoTrain.value,
        }
        if (props.dataSourceId) payload.data_source_id = props.dataSourceId
        const { data, error: apErr } = await useMyFetch<any>(`/studios/${props.studioId}/smart-upload/apply`, { method: 'POST', body: payload })
        if (apErr?.value) {
            error.value = (apErr.value as any)?.data?.detail || 'Could not apply routing.'
            return
        }
        const res = data.value as any
        result.value = res
        emit('applied', res)
    } catch (e: any) {
        error.value = e?.data?.detail || e?.message || 'Apply failed.'
    } finally {
        applying.value = false
    }
}
</script>
