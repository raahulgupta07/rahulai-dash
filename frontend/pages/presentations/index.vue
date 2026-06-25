<template>
    <div class="flex justify-center ps-2 md:ps-4 text-sm bg-[#FBFAF6] min-h-full">
        <div class="w-full max-w-7xl px-4 ps-0 py-2">
            <div class="flex items-start justify-between gap-4">
                <div>
                    <h1
                        class="text-2xl font-semibold text-[#1f2328] tracking-tight flex items-center"
                        style="font-family: ui-serif, Georgia, 'Times New Roman', serif"
                    >
                        {{ $t('nav.presentations') }}
                    </h1>
                    <p class="mt-2 text-[#6b6b6b] leading-relaxed max-w-2xl">
                        Decks generated from your reports — open a report and use the Slides tab to create one.
                    </p>
                </div>
                <button
                    class="mt-1 shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border border-[#E7E5DD] text-[#1f2328] hover:bg-[#F4F1EA] transition-colors"
                    :disabled="loading"
                    @click="fetchPresentations"
                >
                    <Icon name="heroicons:arrow-path" class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
                    Refresh
                </button>
            </div>

            <div class="mt-6">
                <!-- Loading -->
                <div v-if="loading && !presentations.length" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                    <div
                        v-for="n in 4"
                        :key="n"
                        class="bg-white border border-[#E7E5DD] rounded-2xl h-56 animate-pulse"
                    />
                </div>

                <!-- Error -->
                <div
                    v-else-if="error"
                    class="bg-white border border-[#E7E5DD] rounded-2xl py-12 text-center text-[#A8542F]"
                >
                    {{ error }}
                </div>

                <!-- Empty -->
                <div
                    v-else-if="!presentations.length"
                    class="bg-white border border-[#E7E5DD] rounded-2xl"
                >
                    <div class="py-12 flex flex-col items-center text-center">
                        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-[#F4F1EA] border border-[#E7E5DD]">
                            <Icon name="heroicons:presentation-chart-line" class="h-6 w-6 text-[#C2683F]" />
                        </div>
                        <h3
                            class="mt-3 text-base font-semibold text-[#1f2328]"
                            style="font-family: ui-serif, Georgia, 'Times New Roman', serif"
                        >
                            No presentations yet
                        </h3>
                        <p class="mt-1 text-sm text-[#6b6b6b] max-w-md">
                            Open any report → Slides tab → generate a deck. It will appear here.
                        </p>
                        <button
                            class="mt-4 inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-[#C2683F] text-white hover:bg-[#A8542F] transition-colors"
                            @click="navigateTo('/reports')"
                        >
                            Browse reports
                        </button>
                    </div>
                </div>

                <!-- Grid -->
                <div v-else class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                    <div
                        v-for="p in presentations"
                        :key="p.id"
                        class="group bg-white border border-[#E7E5DD] rounded-2xl overflow-hidden hover:border-[#C2683F] transition-colors flex flex-col"
                    >
                        <!-- Thumb (click → open split view) -->
                        <div
                            class="aspect-video bg-[#F4F1EA] border-b border-[#E7E5DD] flex items-center justify-center overflow-hidden cursor-pointer"
                            @click="openSlides(p)"
                        >
                            <img
                                v-if="thumbs[p.id]"
                                :src="thumbs[p.id]"
                                class="w-full h-full object-cover"
                                alt=""
                            />
                            <Icon v-else name="heroicons:presentation-chart-line" class="h-8 w-8 text-[#C2683F]/50" />
                        </div>
                        <!-- Body -->
                        <div class="p-3 flex flex-col gap-1.5 flex-1">
                            <h3
                                class="text-sm font-semibold text-[#1f2328] line-clamp-2 cursor-pointer"
                                @click="openSlides(p)"
                            >
                                {{ p.title || 'Untitled deck' }}
                            </h3>
                            <p v-if="p.report_title" class="text-xs text-[#9a958c] line-clamp-1">
                                {{ p.report_title }}
                            </p>
                            <div class="flex items-center gap-2 pt-0.5">
                                <span class="text-[11px] text-[#6b6b6b]">
                                    {{ p.slide_count || 0 }} slide{{ p.slide_count === 1 ? '' : 's' }}
                                </span>
                                <span
                                    v-if="p.status === 'failed'"
                                    class="text-[10px] px-1.5 py-0.5 rounded bg-[#F4D7CB] text-[#A8542F]"
                                >failed</span>
                                <span
                                    v-else-if="p.status === 'pending'"
                                    class="text-[10px] px-1.5 py-0.5 rounded bg-[#F4F1EA] text-[#9a958c]"
                                >generating</span>
                                <button
                                    v-if="p.pptx_ready"
                                    class="ms-auto inline-flex items-center gap-1 text-[11px] font-medium text-[#9a958c] hover:text-[#C2683F]"
                                    :disabled="downloading === p.id"
                                    @click.stop="downloadPptx(p)"
                                >
                                    <Icon name="heroicons:arrow-down-tray" class="h-3.5 w-3.5" />
                                    {{ downloading === p.id ? '…' : '.pptx' }}
                                </button>
                            </div>
                            <!-- Two actions: Open (split) + Open in chat -->
                            <div class="mt-auto pt-2 grid grid-cols-2 gap-2">
                                <button
                                    class="inline-flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium rounded-lg bg-[#C2683F] text-white hover:bg-[#A8542F] transition-colors"
                                    @click.stop="openSlides(p)"
                                >
                                    <Icon name="heroicons:presentation-chart-line" class="h-3.5 w-3.5" />
                                    Open
                                </button>
                                <button
                                    class="inline-flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium rounded-lg border border-[#E7E5DD] text-[#1f2328] hover:bg-[#F4F1EA] transition-colors"
                                    @click.stop="openInChat(p)"
                                >
                                    <Icon name="heroicons:chat-bubble-left-right" class="h-3.5 w-3.5" />
                                    Open in chat
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
definePageMeta({ auth: true })

interface Presentation {
    id: string
    report_id: string
    title: string | null
    version: number
    status: string
    slide_count: number
    has_preview: boolean
    pptx_ready: boolean
    report_title: string | null
    created_at: string
    updated_at: string
}

const config = useRuntimeConfig()
const { token } = useAuth()
const { organization } = useOrganization()

const presentations = ref<Presentation[]>([])
const thumbs = ref<Record<string, string>>({})
const loading = ref(false)
const error = ref<string | null>(null)
const downloading = ref<string | null>(null)

function authHeaders(): Record<string, string> {
    const h: Record<string, string> = { Authorization: `${token.value}` }
    if (organization.value?.id) h['X-Organization-Id'] = organization.value.id
    return h
}

async function fetchPresentations() {
    loading.value = true
    error.value = null
    try {
        const { data, error: fetchErr } = await useMyFetch<Presentation[]>('/api/artifacts/presentations', { method: 'GET' })
        if (fetchErr.value) throw new Error('Failed to load presentations')
        presentations.value = data.value || []
        loadThumbs()
    } catch (e: any) {
        error.value = e?.message || 'Failed to load presentations'
    } finally {
        loading.value = false
    }
}

// Preview images are auth-gated → fetch as blob, hand the card an object URL.
async function loadThumbs() {
    for (const p of presentations.value) {
        if (!p.has_preview || thumbs.value[p.id]) continue
        try {
            const res = await fetch(`${config.public.baseURL}/artifacts/${p.id}/preview/0`, {
                method: 'GET',
                headers: authHeaders(),
            })
            if (!res.ok) continue
            const blob = await res.blob()
            thumbs.value = { ...thumbs.value, [p.id]: window.URL.createObjectURL(blob) }
        } catch { /* leave icon fallback */ }
    }
}

// Open with the presentation on the right + chat on the left (split view).
function openSlides(p: Presentation) {
    navigateTo(`/reports/${p.report_id}?focus=slides`)
}

// Open the underlying conversation in plain chat (no auto-split).
function openInChat(p: Presentation) {
    navigateTo(`/reports/${p.report_id}`)
}

async function downloadPptx(p: Presentation) {
    if (downloading.value) return
    downloading.value = p.id
    try {
        const res = await fetch(`${config.public.baseURL}/artifacts/${p.id}/export/pptx`, {
            method: 'GET',
            headers: authHeaders(),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const buf = await res.arrayBuffer()
        const blob = new Blob([buf], {
            type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        })
        const safe = String(p.title || 'presentation').replace(/[^\w\s.-]/g, '').slice(0, 120) || 'presentation'
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${safe}.pptx`
        a.style.display = 'none'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        window.URL.revokeObjectURL(url)
    } catch {
        /* ignore — button stays available to retry */
    } finally {
        downloading.value = null
    }
}

onMounted(fetchPresentations)
</script>
