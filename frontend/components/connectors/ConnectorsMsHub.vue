<template>
    <div v-if="enabled" class="mb-8">
        <!-- Section header -->
        <div class="flex items-center justify-between mb-3">
            <div>
                <h2 class="text-xl text-[#1f2328]" style="font-family: 'Spectral', ui-serif, Georgia, serif">
                    {{ $t('connectors.hubTitle') }}
                </h2>
                <p class="text-[#6b6b6b] text-xs mt-0.5">{{ $t('connectors.hubSubtitle') }}</p>
            </div>
            <button
                v-if="canManage"
                @click="navigateTo('/connectors/manage')"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl bg-white border border-[#E9E0D3] text-[#1f2328] hover:bg-[#F4EEE5] hover:border-[#C2541E]/40 transition-colors"
            >
                <UIcon name="i-heroicons-cog-6-tooth" class="w-3.5 h-3.5" />
                {{ $t('connectors.manage') }}
            </button>
        </div>

        <!-- Compact tiles: logo + name + gear(configure). Single action row. -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div
                v-for="c in catalog"
                :key="c.key"
                class="p-3.5 rounded-xl border border-[#E9E0D3] bg-white shadow-sm relative"
                :class="{ 'opacity-60': !c.live }"
            >
                <!-- draft/configured pill (admin) -->
                <span
                    v-if="c.live && canManage"
                    class="absolute top-3 right-3 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded"
                    :class="templateFor(c.key) ? 'text-[#3f9e6a] bg-[#eef6f0]' : 'text-[#9a958c] bg-[#F4EEE5]'"
                >{{ templateFor(c.key) ? $t('connectors.configured') : $t('connectors.draft') }}</span>

                <div class="flex items-center gap-2.5">
                    <div class="w-8 h-8 rounded-lg bg-white border border-[#E9E0D3] flex items-center justify-center p-1 shrink-0">
                        <img :src="c.icon" :alt="c.name" class="w-full h-full object-contain" />
                    </div>
                    <h3 class="text-[13.5px] font-semibold text-[#1f2328] leading-tight">{{ c.name }}</h3>
                    <!-- GEAR = configure/edit (admin, live) -->
                    <button
                        v-if="c.live && canManage"
                        @click="openAdminConfig(c.key)"
                        :title="$t('connectors.configure')"
                        class="ml-auto text-[#9a958c] hover:text-[#C2541E] hover:bg-[#F4EEE5] rounded-md p-1 transition-colors"
                    >
                        <UIcon name="i-heroicons-cog-6-tooth" class="w-4 h-4" />
                    </button>
                </div>

                <!-- status + single action -->
                <template v-if="!c.live">
                    <div class="text-[11px] text-[#9a958c] mt-2.5 mb-2.5">{{ $t('connectors.comingSoon') }}</div>
                    <span class="text-xs font-medium text-[#9a958c] cursor-default">{{ $t('connectors.signIn') }}</span>
                </template>

                <template v-else-if="cloneFor(c.key)">
                    <div class="text-[11px] flex items-center gap-1.5 font-semibold text-[#3f9e6a] mt-2.5 mb-2.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-[#3f9e6a]"></span>{{ $t('connectors.connected') }} · {{ ownerLabel(cloneFor(c.key)) }}
                    </div>
                    <div class="flex gap-1.5 items-center">
                        <NuxtLink :to="`/agents/${cloneFor(c.key).id}`" class="text-xs font-semibold px-2.5 py-1.5 rounded-lg bg-[#C2541E] text-white hover:bg-[#A8330F]">{{ $t('connectors.open') }}</NuxtLink>
                        <button @click="testClone(cloneFor(c.key))" :disabled="testingId === cloneFor(c.key).id" class="text-xs font-medium text-[#6b6b6b] hover:text-[#C2541E] disabled:opacity-50">
                            <Spinner v-if="testingId === cloneFor(c.key).id" class="w-3 h-3 inline" />{{ $t('connectors.test') }}
                        </button>
                        <button @click="startConnect(c.key)" class="text-xs font-medium text-[#6b6b6b] hover:text-[#C2541E]">{{ $t('connectors.resync') }}</button>
                    </div>
                </template>

                <template v-else-if="templateFor(c.key)">
                    <div class="text-[11px] flex items-center gap-1.5 text-[#6b6b6b] mt-2.5 mb-2.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-[#C9BCA9]"></span>{{ canManage ? $t('connectors.configuredNotConnected') : $t('connectors.notConnected') }}
                    </div>
                    <button @click="startConnect(c.key)" class="text-xs font-semibold px-2.5 py-1.5 rounded-lg bg-[#C2541E] text-white hover:bg-[#A8330F]">{{ $t('connectors.signInCode') }}</button>
                </template>

                <template v-else>
                    <div class="text-[11px] flex items-center gap-1.5 text-[#6b6b6b] mt-2.5 mb-2.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-[#C9BCA9]"></span>{{ $t('connectors.notConfigured') }}
                    </div>
                    <button v-if="canManage" @click="openAdminConfig(c.key)" class="text-xs font-semibold px-2.5 py-1.5 rounded-lg bg-[#C2541E] text-white hover:bg-[#A8330F]">{{ $t('connectors.configure') }}</button>
                    <span v-else class="text-xs font-medium text-[#9a958c]">{{ $t('connectors.askAdmin') }}</span>
                </template>
            </div>
        </div>

        <!-- ADMIN CONFIG MODAL -->
        <UModal v-model="showAdmin">
            <div class="p-6">
                <h3 class="text-lg text-[#1f2328] mb-1" style="font-family:'Spectral',serif">{{ $t('connectors.configureName', { name: editingConn.name }) }}</h3>
                <p class="text-xs text-[#6b6b6b] mb-4">{{ $t('connectors.configureHint') }}</p>
                <template v-if="editingConn.fields.includes('server_hostname')">
                    <label class="block text-xs font-semibold text-[#6b6b6b] mb-1">{{ $t('connectors.sqlEndpoint') }}</label>
                    <input v-model="cfg.server_hostname" placeholder="xxxxx.datawarehouse.fabric.microsoft.com" class="w-full border border-[#E9E0D3] rounded-lg px-3 py-2 text-sm bg-[#FCFAF6] focus:outline-none focus:border-[#C2541E] mb-3" />
                </template>
                <label class="block text-xs font-semibold text-[#6b6b6b] mb-1">{{ $t('connectors.tenantId') }}</label>
                <input v-model="cfg.tenant_id" placeholder="0a8a4f2c-..." class="w-full border border-[#E9E0D3] rounded-lg px-3 py-2 text-sm bg-[#FCFAF6] focus:outline-none focus:border-[#C2541E] mb-3" />
                <p class="text-[11px] text-[#9a958c] bg-[#FCFAF6] border border-[#E9E0D3] rounded-lg p-2.5 leading-relaxed">{{ $t('connectors.autoDbNote') }}</p>
                <div v-if="adminError" class="text-xs text-[#B4432B] bg-[#F7E7E2] rounded-lg p-2.5 mt-2">{{ adminError }}</div>
                <div class="flex justify-end gap-2 mt-4">
                    <button @click="showAdmin = false" class="text-sm px-3 py-2 rounded-lg bg-white border border-[#E9E0D3]">{{ $t('common.cancel') }}</button>
                    <button @click="publishTemplate" :disabled="publishing" class="text-sm px-4 py-2 rounded-lg bg-[#C2541E] text-white hover:bg-[#A8330F] disabled:opacity-50">
                        <Spinner v-if="publishing" class="w-3.5 h-3.5 inline" /> {{ $t('connectors.publish') }}
                    </button>
                </div>
            </div>
        </UModal>

        <!-- DEVICE-CODE CONNECT MODAL -->
        <UModal v-model="showConnect" :prevent-close="connecting">
            <div class="p-6">
                <h3 class="text-lg text-[#1f2328] mb-1" style="font-family:'Spectral',serif">{{ $t('connectors.connectTitle', { name: connectName }) }}</h3>
                <p class="text-xs text-[#6b6b6b] mb-4">{{ $t('connectors.mfaSafe') }}</p>

                <div v-if="dcError" class="text-xs text-[#B4432B] bg-[#F7E7E2] rounded-lg p-3">{{ dcError }}</div>

                <template v-else-if="dcPhase === 'starting'">
                    <div class="flex items-center gap-2 text-sm text-[#6b6b6b] py-4"><Spinner class="w-4 h-4" /> {{ $t('connectors.starting') }}</div>
                </template>

                <template v-else-if="dcPhase === 'code'">
                    <ol class="text-sm text-[#1f2328] space-y-2 mb-3">
                        <li>1. {{ $t('connectors.step1') }} <a :href="verificationUri" target="_blank" class="text-[#A8330F] font-semibold underline">{{ verificationUri }}</a></li>
                        <li>2. {{ $t('connectors.step2') }}</li>
                    </ol>
                    <div @click="copyCode" class="font-mono text-2xl font-bold tracking-widest text-center text-[#A8330F] bg-[#FBF3EB] border border-dashed border-[#C2541E] rounded-xl py-4 cursor-pointer select-all">{{ userCode }}</div>
                    <p class="text-sm text-[#1f2328] mt-2">3. {{ $t('connectors.step3') }}</p>
                    <div class="flex items-center gap-2 text-xs text-[#6b6b6b] bg-[#F6F1EA] rounded-lg p-2.5 mt-3">
                        <Spinner class="w-3.5 h-3.5" /> {{ $t('connectors.waiting') }}
                    </div>
                </template>

                <template v-else-if="dcPhase === 'syncing'">
                    <div class="text-sm text-[#3f9e6a] bg-[#eef6f0] rounded-lg p-3 mb-2 flex items-center gap-2">✓ {{ $t('connectors.signedIn') }}</div>
                    <div class="flex items-center gap-2 text-xs text-[#6b6b6b] bg-[#F6F1EA] rounded-lg p-2.5"><Spinner class="w-3.5 h-3.5" /> {{ $t('connectors.syncing') }}</div>
                </template>

                <div class="flex justify-end mt-4">
                    <button @click="cancelConnect" class="text-sm px-3 py-2 rounded-lg bg-white border border-[#E9E0D3]">{{ dcPhase === 'syncing' ? $t('common.close') : $t('common.cancel') }}</button>
                </div>
            </div>
        </UModal>
    </div>
</template>

<script lang="ts" setup>
import Spinner from '~/components/Spinner.vue'
import { useCan } from '~/composables/usePermissions'

const props = defineProps<{ agents: any[] }>()
const emit = defineEmits<{ (e: 'refresh'): void }>()

const { t } = useI18n()
const toast = useToast()

const enabled = ref(false)
const templates = ref<any[]>([])
const canManage = computed(() => useCan('manage_connections'))

// Static catalog. `fields` = what the admin sets ONCE (no per-user data / passwords).
// Fabric: server host + tenant; database is auto-discovered from what each user can
// access at sign-in. Power BI (User Sign-in): tenant only — datasets a user can see
// come back automatically. SharePoint/OneDrive queued (same device-code path).
const catalog = [
    { key: 'fabric', type: 'ms_fabric', name: 'Microsoft Fabric', icon: '/data_sources_icons/ms_fabric.png', desc: 'Lakehouse & warehouse SQL endpoint.', live: true, fields: ['server_hostname', 'tenant_id'] },
    { key: 'powerbi', type: 'powerbi_user', name: 'Power BI (User Sign-in)', icon: '/data_sources_icons/powerbi.png', desc: 'Datasets & reports — each user sees their own.', live: true, fields: ['tenant_id'] },
    { key: 'sharepoint', type: 'sharepoint', name: 'SharePoint', icon: '/data_sources_icons/sharepoint.png', desc: 'Sites, docs & lists.', live: false, fields: ['tenant_id'] },
    { key: 'onedrive', type: 'onedrive', name: 'OneDrive', icon: '/data_sources_icons/onedrive.png', desc: 'Your personal files.', live: false, fields: ['tenant_id'] },
]

function templateFor(key: string) {
    const type = catalog.find(c => c.key === key)?.type
    return templates.value.find(tp => tp.type === type) || null
}
function cloneFor(key: string) {
    const tpl = templateFor(key)
    if (!tpl) return null
    return (props.agents || []).find(a => a.template_source_id === tpl.id) || null
}
function ownerLabel(clone: any) {
    return (clone?.name || '').split('·').pop()?.trim() || t('connectors.you')
}

async function loadFlag() {
    try {
        const { data } = await useMyFetch('/organization/hybrid-flags', { method: 'GET' })
        const rows = (data.value as any[]) || []
        const row = rows.find(r => r.key === 'PER_USER_CONNECTOR' || r.env_name === 'HYBRID_PER_USER_CONNECTOR')
        enabled.value = !!row?.effective
    } catch { enabled.value = false }
}
async function loadTemplates() {
    try {
        const { data } = await useMyFetch('/connectors/available', { method: 'GET' })
        templates.value = (data.value as any[]) || []
    } catch { templates.value = [] }
}

// ---- admin config (per-connector fields) ----
const showAdmin = ref(false)
const publishing = ref(false)
const adminError = ref('')
const cfg = reactive<{ server_hostname: string; tenant_id: string }>({ server_hostname: '', tenant_id: '' })
const editingKey = ref('fabric')
const editingConn = computed(() => catalog.find(c => c.key === editingKey.value) || catalog[0])

function openAdminConfig(key: string) {
    editingKey.value = key
    const tpl = templateFor(key)
    cfg.server_hostname = tpl?.config?.server_hostname || ''
    cfg.tenant_id = tpl?.config?.tenant_id || ''
    adminError.value = ''
    showAdmin.value = true
}
async function publishTemplate() {
    publishing.value = true
    adminError.value = ''
    try {
        const c = editingConn.value
        // Only send the fields this connector needs. Database is NEVER set here —
        // it's auto-discovered from what each user can access at sign-in.
        const config: any = {}
        if (c.fields.includes('server_hostname')) config.server_hostname = cfg.server_hostname.trim()
        config.tenant_id = cfg.tenant_id.trim() || null
        const body = {
            name: c.name,
            type: c.type,
            config,
            auth_policy: 'user_required',
            allowed_user_auth_modes: ['device_code'],
            is_user_template: true,
        }
        const { data, error } = await useMyFetch('/data_sources', { method: 'POST', body })
        if (error.value) throw error.value
        toast.add({ title: t('connectors.published'), color: 'green', icon: 'i-heroicons-check-circle' })
        showAdmin.value = false
        await loadTemplates()
        emit('refresh')
    } catch (e: any) {
        adminError.value = e?.data?.detail || e?.message || t('connectors.publishFailed')
    } finally {
        publishing.value = false
    }
}

// ---- device-code connect (start → poll loop → auto-register) ----
const showConnect = ref(false)
const connecting = ref(false)
const dcPhase = ref<'starting' | 'code' | 'syncing'>('starting')
const dcError = ref('')
const userCode = ref('')
const verificationUri = ref('')
const connectName = ref('')
let deviceCode = ''
let templateId = ''
let pollHandle: ReturnType<typeof setTimeout> | null = null
let pollInterval = 5000
let cancelled = false

async function startConnect(key: string) {
    const tpl = templateFor(key)
    if (!tpl) return
    templateId = tpl.id
    connectName.value = catalog.find(c => c.key === key)?.name || 'connector'
    dcPhase.value = 'starting'; dcError.value = ''; userCode.value = ''; cancelled = false; connecting.value = true
    showConnect.value = true
    try {
        const { data, error } = await useMyFetch(`/connectors/${templateId}/device-code/start`, { method: 'POST' })
        if (error.value) throw error.value
        const d = data.value as any
        userCode.value = d.user_code
        verificationUri.value = d.verification_uri
        deviceCode = d.device_code
        pollInterval = (d.interval || 5) * 1000
        dcPhase.value = 'code'
        schedulePoll()
    } catch (e: any) {
        dcError.value = e?.data?.detail || e?.message || t('connectors.startFailed')
        connecting.value = false
    }
}
function schedulePoll() {
    pollHandle = setTimeout(poll, pollInterval)
}
async function poll() {
    if (cancelled) return
    try {
        const { data, error } = await useMyFetch(`/connectors/${templateId}/device-code/poll`, { method: 'POST', body: { device_code: deviceCode } })
        if (error.value) throw error.value
        const r = data.value as any
        if (r.status === 'pending') {
            if (r.slow_down) pollInterval += 5000
            schedulePoll(); return
        }
        if (r.status === 'success') {
            dcPhase.value = 'syncing'
            connecting.value = false
            emit('refresh')
            setTimeout(() => {
                showConnect.value = false
                if (r.data_source_id) navigateTo(`/agents/${r.data_source_id}`)
            }, 900)
            return
        }
        dcError.value = r.error || t('connectors.signInFailed')
        connecting.value = false
    } catch (e: any) {
        dcError.value = e?.data?.detail || e?.message || t('connectors.signInFailed')
        connecting.value = false
    }
}
function cancelConnect() {
    cancelled = true
    if (pollHandle) clearTimeout(pollHandle)
    showConnect.value = false
    connecting.value = false
}
function copyCode() {
    if (navigator.clipboard) navigator.clipboard.writeText(userCode.value)
    toast.add({ title: t('connectors.codeCopied'), color: 'green' })
}

// ---- test an existing clone ----
const testingId = ref<string | null>(null)
async function testClone(clone: any) {
    testingId.value = clone.id
    try {
        const { data, error } = await useMyFetch(`/data_sources/${clone.id}/test_connection`, { method: 'GET' })
        if (error.value) throw error.value
        const r = data.value as any
        toast.add({
            title: r?.success ? t('connectors.testOk') : t('connectors.testFail'),
            description: r?.message || '',
            color: r?.success ? 'green' : 'red',
            icon: r?.success ? 'i-heroicons-check-circle' : 'i-heroicons-x-circle',
        })
    } catch (e: any) {
        toast.add({ title: t('connectors.testFail'), description: e?.data?.detail || e?.message || '', color: 'red' })
    } finally {
        testingId.value = null
    }
}

onBeforeUnmount(() => { if (pollHandle) clearTimeout(pollHandle) })

onMounted(async () => {
    await loadFlag()
    if (enabled.value) await loadTemplates()
})
</script>
