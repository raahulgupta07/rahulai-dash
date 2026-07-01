<template>
    <NuxtLayout name="default">
        <div class="flex bg-[#F1ECE3] text-sm" style="min-height: calc(100vh - 56px)">

            <!-- Loading skeleton (rail + main cards) -->
            <template v-if="isLoading">
                <div class="w-[240px] shrink-0 m-2 rounded-2xl bg-[#FBFAF6] border border-[#E9E0D3] animate-pulse" />
                <div class="flex-1 my-2 me-2 rounded-2xl bg-[#FBFAF6] border border-[#E9E0D3] animate-pulse" />
            </template>

            <!-- Access errors -->
            <div v-else-if="fetchError === 403" class="flex-1 m-2">
                <div class="bg-[#FBFAF6] border border-[#E9E0D3] rounded-2xl p-10 text-center">
                    <Icon name="i-heroicons-lock-closed" class="w-10 h-10 text-[#9a958c] mx-auto mb-3" />
                    <h2 class="text-base font-medium text-[#1f2328]">Access Restricted</h2>
                    <p class="mt-1.5 text-sm text-[#6b6b6b] max-w-sm mx-auto">This agent is private. Contact the owner or an admin to request access.</p>
                    <NuxtLink to="/agents" class="mt-4 inline-block text-sm text-[#C2541E] hover:underline">← Back to agents</NuxtLink>
                </div>
            </div>
            <div v-else-if="fetchError === 404" class="flex-1 m-2">
                <div class="bg-[#FBFAF6] border border-[#E9E0D3] rounded-2xl p-10 text-center">
                    <Icon name="i-heroicons-exclamation-circle" class="w-10 h-10 text-[#9a958c] mx-auto mb-3" />
                    <h2 class="text-base font-medium text-[#1f2328]">Agent Not Found</h2>
                    <p class="mt-1.5 text-sm text-[#6b6b6b] max-w-sm mx-auto">The agent you're looking for doesn't exist or has been removed.</p>
                    <NuxtLink to="/agents" class="mt-4 inline-block text-sm text-[#C2541E] hover:underline">← Back to agents</NuxtLink>
                </div>
            </div>
            <div v-else-if="fetchError" class="flex-1 m-2">
                <div class="bg-[#FBFAF6] border border-[#E9E0D3] rounded-2xl p-10 text-center text-sm text-[#6b6b6b]">Failed to load this agent.</div>
            </div>

            <!-- RAIL + MAIN (mirrors /workspace AppRail .cag-rail-card + main card) -->
            <template v-else>

                <!-- LEFT RAIL -->
                <aside class="cag-rail-card shrink-0 self-stretch min-h-0 overflow-y-auto m-2 flex flex-col">
                    <!-- header card: back link + identity -->
                    <div class="px-3 pt-3 pb-2.5 border-b border-[#E9E0D3]">
                        <NuxtLink to="/agents" class="text-[11px] text-[#9a958c] hover:text-[#6b6b6b] mb-1.5 inline-flex items-center gap-1">
                            <UIcon name="i-heroicons-arrow-left" class="w-3 h-3" /> All agents
                        </NuxtLink>
                        <div class="flex items-center gap-2">
                            <div class="shrink-0 flex items-center justify-center w-7 h-7 rounded-lg bg-[#F4F1EA] border border-[#E9E0D3] text-[#C2541E] p-1">
                                <img v-if="connectorMeta" :src="connectorMeta.logo" :alt="connectorMeta.name" class="w-full h-full object-contain" />
                                <UIcon v-else name="i-heroicons-circle-stack" class="w-4 h-4" />
                            </div>
                            <div class="min-w-0">
                                <div class="flex items-center gap-1.5">
                                    <span class="text-sm font-semibold text-[#1f2328] truncate" style="font-family:'Spectral',ui-serif,Georgia,serif">{{ connectorMeta ? connectorMeta.name : (integration?.name || 'Agent') }}</span>
                                    <span v-if="(integration?.connections || []).length" class="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded bg-[#EDEBE3] text-[#6b6b6b] shrink-0">Connected</span>
                                </div>
                                <p v-if="connectorMeta?.subtitle" class="text-[11px] text-[#9a958c] truncate">{{ connectorMeta.subtitle }}</p>
                            </div>
                        </div>
                    </div>

                    <!-- grouped tab nav -->
                    <nav class="px-2 py-2 space-y-px flex-1">
                        <template v-for="grp in tabGroups" :key="grp.label">
                            <div class="cag-eyebrow px-2 pt-3 pb-1">{{ grp.label }}</div>
                            <NuxtLink
                                v-for="tab in grp.items"
                                :key="tab.name"
                                :to="tabTo(tab.name)"
                                :class="['cag-sec-link', isTabActive(tab.name) ? 'cag-sec-active' : '']"
                            >
                                <span class="cag-sec-ic"><UIcon :name="tabIcon(tab.name)" class="w-[15px] h-[15px]" /></span>
                                <span class="flex-1 truncate">{{ tab.label }}</span>
                                <span v-if="tab.name === 'tables' && catalog.shouldShow && catalog.count > 0" class="text-[11px] text-[#9a958c] shrink-0">{{ catalog.count }}</span>
                            </NuxtLink>
                        </template>
                    </nav>

                    <!-- lifecycle actions (plain rail items under a Connection eyebrow) -->
                    <div class="px-2 pb-2">
                        <div class="border-t border-[#E9E0D3] mx-2"></div>
                        <div class="cag-eyebrow px-2 pt-2 pb-1">Connection</div>
                        <button @click="testConn" :disabled="testing" class="cag-sec-link w-full">
                            <span class="cag-sec-ic"><Spinner v-if="testing" class="w-3.5 h-3.5" /><UIcon v-else name="i-heroicons-bolt" class="w-[15px] h-[15px]" /></span>
                            <span class="flex-1 text-start truncate">Test connection</span>
                        </button>
                        <button v-if="isClone" @click="showDisconnect = true" class="cag-sec-link cag-sec-danger w-full">
                            <span class="cag-sec-ic"><UIcon name="i-heroicons-x-mark" class="w-[15px] h-[15px]" /></span>
                            <span class="flex-1 text-start truncate">Disconnect</span>
                        </button>
                    </div>
                </aside>

                <!-- MAIN (page card) -->
                <div class="flex-1 min-w-0 my-2 me-2">
                    <div class="px-6 md:px-8 py-6 bg-[#FBFAF6] border border-[#E9E0D3] rounded-2xl" style="min-height: calc(100vh - 72px)">
                        <div class="flex items-start justify-between gap-4 mb-5">
                            <div class="min-w-0 flex-1">
                                <!-- Description (inline-editable) -->
                                <div v-if="integration?.description || useCan('update_data_source')" class="flex items-center gap-2 group max-w-2xl">
                                    <template v-if="editingDesc">
                                        <input
                                            ref="descInputRef"
                                            v-model="descForm"
                                            type="text"
                                            class="flex-1 text-sm text-[#6b6b6b] border-b border-[#C2541E] bg-transparent outline-none py-0.5"
                                            @keydown.enter="saveDesc"
                                            @keydown.escape="cancelDesc"
                                            @blur="saveDesc"
                                        />
                                    </template>
                                    <template v-else>
                                        <p
                                            class="text-sm text-[#6b6b6b] truncate rounded px-1 -mx-1 transition-colors"
                                            :class="useCan('update_data_source') ? 'cursor-pointer hover:bg-[#ECEAE1]' : ''"
                                            @click="useCan('update_data_source') && startEditDesc()"
                                        >{{ integration?.description || 'No description' }}</p>
                                        <button
                                            v-if="useCan('update_data_source')"
                                            class="text-[10px] text-[#C2541E] hover:underline opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                                            @click="startEditDesc"
                                        >Edit</button>
                                    </template>
                                </div>
                            </div>
                            <div class="shrink-0 flex items-center gap-3">
                                <PublishStatusControl
                                    :data-source-id="id"
                                    :status="integration?.publish_status || 'published'"
                                    @updated="onPublishStatusUpdated"
                                />
                                <UButton
                                    color="gray"
                                    size="sm"
                                    class="bg-[#C2541E] hover:bg-[#A8330F] text-white ring-0"
                                    :loading="startingChat"
                                    @click="startChat"
                                >
                                    New Report
                                    <UIcon name="heroicons-arrow-right" class="w-3.5 h-3.5 ms-1" />
                                </UButton>
                            </div>
                        </div>

                        <slot />
                    </div>
                </div>
            </template>

            <!-- Disconnect confirm -->
            <UModal v-model="showDisconnect">
                <div class="p-6">
                    <h3 class="text-lg text-[#1f2328] mb-1" style="font-family:'Spectral',ui-serif,Georgia,serif">Disconnect this source?</h3>
                    <p class="text-sm text-[#6b6b6b] mb-4">Removes your private agent and sign-in. Your data stays in Microsoft — you can sign in again anytime.</p>
                    <div class="flex justify-end gap-2">
                        <button @click="showDisconnect = false" class="px-3 py-2 rounded-lg text-sm bg-white border border-[#E9E0D3]">Cancel</button>
                        <button @click="disconnect" :disabled="disconnecting" class="px-3 py-2 rounded-lg text-sm text-[#B4432B] border border-[#F0D8D1] bg-[#FCF3F0]"><Spinner v-if="disconnecting" class="w-3.5 h-3.5 inline" /> Disconnect</button>
                    </div>
                </div>
            </UModal>
        </div>

    </NuxtLayout>
</template>

<script setup lang="ts">
import Spinner from '~/components/Spinner.vue'
import PublishStatusControl from '~/components/datasources/PublishStatusControl.vue'
import {
    getEffectiveStatus,
    hasAnyActiveIndexing,
    indexingSummary,
    statusDotClass,
} from '~/composables/useConnectionStatus'
import { useCan } from '~/composables/usePermissions'

const route = useRoute()
const router = useRouter()
const toast = useToast?.()

const id = computed(() => String(route.params.id || ''))
const { isMcpToolsEnabled } = useOrgSettings()

const canViewMonitoring = computed(() => useCan('full_admin_access'))
const canManageEvals = computed(() => useCan('manage_evals'))

const allTabs = computed(() => {
    // Label the Tables tab to match the agent's data_shape: "Files" for
    // file-shape connectors (OneDrive / SharePoint / Google Drive),
    // "Collections" for object-shape (MongoDB), default "Tables" for SQL.
    const tablesLabel = (() => {
        const s = catalog.value.noun.plural
        if (s === 'tables') return 'Tables'
        // Title-case the noun
        return s.charAt(0).toUpperCase() + s.slice(1)
    })()
    return [
        { name: '', label: 'Overview' },
        { name: 'tables', label: tablesLabel },
        { name: 'context', label: 'Instructions' },
        { name: 'queries', label: 'Queries' },
        { name: 'tools', label: 'Tools' },
        { name: 'monitoring', label: 'Monitoring', gate: canViewMonitoring },
        { name: 'evals', label: 'Evals', gate: canManageEvals },
        { name: 'settings', label: 'Settings' },
    ]
})

const tabs = computed(() =>
    allTabs.value.filter(tab => {
        if (tab.name === 'tools' && !isMcpToolsEnabled.value) return false
        if (tab.gate && !tab.gate.value) return false
        return true
    })
)

function tabTo(tabName: string) {
    if (!id.value) return '/agents'
    if (tabName === '') return `/agents/${id.value}`
    return `/agents/${id.value}/${tabName}`
}

// Per-tab heroicon (rail nav), matching the Manage/Workspace rail icon style.
const TAB_ICONS: Record<string, string> = {
    '': 'i-heroicons-squares-2x2',
    tables: 'i-heroicons-table-cells',
    context: 'i-heroicons-document-text',
    queries: 'i-heroicons-command-line',
    tools: 'i-heroicons-wrench-screwdriver',
    monitoring: 'i-heroicons-chart-bar',
    evals: 'i-heroicons-check-badge',
    settings: 'i-heroicons-cog-6-tooth',
}
function tabIcon(name: string) {
    return TAB_ICONS[name] || 'i-heroicons-squares-2x2'
}

function isTabActive(tabName: string) {
    const path = route.path
    if (tabName === '') {
        return path === `/agents/${id.value}` || path === `/agents/${id.value}/`
    }
    return path === `/agents/${id.value}/${tabName}`
}

const tableCount = computed(() =>
    (integration.value?.connections || []).reduce((sum: number, c: any) => sum + (c.table_count || 0), 0)
)
const connectionCount = computed(() => (integration.value?.connections || []).length)

// Shape-aware catalog count: respects each connection's data_shape (files
// vs tables vs objects) and hides the number entirely when any attached
// connection is user_required + the current user hasn't signed in (the "0"
// would lie — per-user catalog hasn't been fetched yet).
const registryByType = ref<Record<string, any>>({})
onMounted(async () => {
    try {
        const { data } = await useMyFetch('/available_data_sources', { method: 'GET' })
        for (const entry of (data.value as any[]) || []) {
            registryByType.value[entry.type] = entry
        }
    } catch {}
})
const { computeFromAgent } = useCatalogCount()
const catalog = computed(() => computeFromAgent(integration.value, registryByType.value))

// Connector-clone identity: product logo + clean name + signed-in email, so the
// rail reads "Power BI / demo@test.com" instead of the raw stored name.
const CONNECTOR_META: Record<string, { logo: string; name: string }> = {
    ms_fabric: { logo: '/data_sources_icons/ms_fabric.png', name: 'Microsoft Fabric' },
    ms_fabric_user: { logo: '/data_sources_icons/ms_fabric.png', name: 'Microsoft Fabric' },
    powerbi: { logo: '/data_sources_icons/powerbi.png', name: 'Power BI' },
    powerbi_user: { logo: '/data_sources_icons/powerbi.png', name: 'Power BI' },
    sharepoint: { logo: '/data_sources_icons/sharepoint.png', name: 'SharePoint' },
    onedrive: { logo: '/data_sources_icons/onedrive.png', name: 'OneDrive' },
}
const isClone = computed(() => !!integration.value?.template_source_id)
const connectorMeta = computed(() => {
    if (!isClone.value) return null
    const type = integration.value?.connections?.[0]?.type || integration.value?.type
    const m = CONNECTOR_META[type]
    if (!m) return null
    const name = integration.value?.name || ''
    const subtitle = name.includes('·') ? name.split('·').pop().trim() : ''
    return { ...m, subtitle }
})

// Group the flat tab list into rail sections (mirrors the Manage page layout).
const TAB_GROUPS: { label: string; names: string[] }[] = [
    { label: 'Explore', names: ['', 'tables', 'queries'] },
    { label: 'Configure', names: ['context', 'tools', 'settings'] },
    { label: 'Observe', names: ['monitoring', 'evals'] },
]
const tabGroups = computed(() => {
    const byName: Record<string, any> = Object.fromEntries(tabs.value.map(t => [t.name, t]))
    return TAB_GROUPS
        .map(g => ({ label: g.label, items: g.names.map(n => byName[n]).filter(Boolean) }))
        .filter(g => g.items.length > 0)
})

// Test connection (per-user token round-trip).
const testing = ref(false)
async function testConn() {
    if (testing.value) return
    testing.value = true
    try {
        const { data, error } = await useMyFetch(`/data_sources/${id.value}/test_connection`, { method: 'GET' })
        if (error?.value) throw error.value
        const r = data.value as any
        toast?.add?.({
            title: r?.success ? 'Connection OK' : 'Connection failed',
            description: r?.message || '',
            color: r?.success ? 'green' : 'red',
            icon: r?.success ? 'i-heroicons-check-circle' : 'i-heroicons-x-circle',
        })
    } catch (e: any) {
        toast?.add?.({ title: 'Connection failed', description: e?.data?.detail || e?.message || '', color: 'red' })
    } finally {
        testing.value = false
    }
}

// Disconnect: delete the private clone + its owned connection(s). Deleting the
// data source cascades its tables/memberships; deleting each connection removes
// the now-orphaned private connection (owner-guarded server-side).
const showDisconnect = ref(false)
const disconnecting = ref(false)
async function disconnect() {
    if (disconnecting.value) return
    disconnecting.value = true
    try {
        const conns = [...(integration.value?.connections || [])]
        const { error } = await useMyFetch(`/data_sources/${id.value}`, { method: 'DELETE' })
        if (error?.value) throw error.value
        for (const conn of conns) {
            try { await useMyFetch(`/connections/${conn.id}`, { method: 'DELETE' }) } catch {}
        }
        toast?.add?.({ title: 'Disconnected', icon: 'i-heroicons-check-circle' })
        router.push('/agents')
    } catch (e: any) {
        toast?.add?.({ title: 'Disconnect failed', description: e?.data?.detail || e?.message || '', color: 'red' })
        disconnecting.value = false
    }
}

const integration = ref<any>(null)
const isLoading = ref(true)
const fetchError = ref<number | null>(null)
const startingChat = ref(false)

const editingDesc = ref(false)
const descForm = ref('')
const descInputRef = ref<HTMLInputElement | null>(null)

function startEditDesc() {
    descForm.value = integration.value?.description || ''
    editingDesc.value = true
    nextTick(() => descInputRef.value?.focus())
}

function cancelDesc() {
    editingDesc.value = false
}

async function saveDesc() {
    if (!editingDesc.value) return
    editingDesc.value = false
    const newVal = (descForm.value || '').trim()
    if (newVal === (integration.value?.description || '')) return
    if (integration.value) integration.value.description = newVal
    const { error } = await useMyFetch(`/data_sources/${id.value}`, {
        method: 'PUT',
        body: { description: newVal },
    })
    if (error?.value) {
        if (integration.value) integration.value.description = descForm.value
        toast?.add?.({ title: 'Failed to save description', color: 'red' })
    } else {
        toast?.add?.({ title: 'Description updated' })
        await fetchIntegration()
    }
}

function onPublishStatusUpdated(value: string) {
    // Optimistic local update; refetch keeps derived views in sync.
    if (integration.value) integration.value.publish_status = value
    fetchIntegration()
}

async function startChat() {
    if (startingChat.value || !integration.value?.id) return
    startingChat.value = true
    try {
        const response = await useMyFetch('/reports', {
            method: 'POST',
            body: JSON.stringify({
                title: 'untitled report',
                files: [],
                data_sources: [integration.value.id],
            }),
        })
        const data = (response.data as any)?.value
        if (data?.id) {
            await router.push(`/reports/${data.id}`)
        }
    } finally {
        startingChat.value = false
    }
}

async function fetchIntegration() {
    if (!id.value) return
    isLoading.value = true
    fetchError.value = null

    try {
        const config = useRuntimeConfig()
        const { token } = useAuth()
        const { organization } = useOrganization()

        const data = await $fetch(`/data_sources/${id.value}`, {
            baseURL: config.public.baseURL,
            method: 'GET',
            headers: {
                Authorization: `${token.value}`,
                'X-Organization-Id': organization.value?.id || '',
            }
        })

        integration.value = data as any
    } catch (e: any) {
        console.error('Failed to fetch integration:', e)
        fetchError.value = e?.response?.status || e?.status || e?.statusCode || 500
    }

    isLoading.value = false
    maybeStartPolling()
}

provide('integration', integration)
provide('fetchIntegration', fetchIntegration)
provide('isLoading', isLoading)
provide('fetchError', fetchError)

const POLL_INTERVAL_MS = 2000
let pollTimer: ReturnType<typeof setInterval> | null = null

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
    }
}

function maybeStartPolling() {
    const hasActive = hasAnyActiveIndexing(integration.value?.connections)
    if (hasActive && !pollTimer) {
        pollTimer = setInterval(() => {
            if (fetchError.value) {
                stopPolling()
                return
            }
            fetchIntegration().then(() => {
                if (!hasAnyActiveIndexing(integration.value?.connections)) {
                    stopPolling()
                }
            })
        }, POLL_INTERVAL_MS)
    } else if (!hasActive) {
        stopPolling()
    }
}

watch(id, () => {
    stopPolling()
    fetchIntegration()
})

onMounted(() => {
    fetchIntegration()
})

onBeforeUnmount(() => {
    stopPolling()
})
</script>

<style scoped>
/* Exact parity with components/nav/AppRail.vue .cag-rail-card (Workspace/Manage rail). */
.cag-rail-card { width: 240px; background: #FBFAF6; border: 1px solid #E9E0D3; border-radius: 16px; font-family: 'Hanken Grotesk', system-ui, sans-serif; }
.cag-eyebrow { font-size: 9px; letter-spacing: .1em; text-transform: uppercase; color: #9a958c; font-weight: 700; }
.cag-sec-link { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 12px; border-radius: 8px; font-size: 12px; color: #6b6b6b; text-decoration: none; text-align: left; background: none; border: none; cursor: pointer; transition: background .12s, color .12s; }
.cag-sec-link:hover { background: #faf8f3; color: #1f2328; }
.cag-sec-link:disabled { opacity: .55; cursor: default; }
.cag-sec-ic { display: flex; align-items: center; justify-content: center; width: 14px; height: 14px; flex: 0 0 14px; color: #8c8479; }
.cag-sec-active { background: #ECEAE1; color: #1f2328; font-weight: 500; }
.cag-sec-active .cag-sec-ic { color: #C2541E; }
.cag-sec-danger { color: #B4432B; }
.cag-sec-danger .cag-sec-ic { color: #B4432B; }
.cag-sec-danger:hover { background: #FCF3F0; color: #B4432B; }
</style>
