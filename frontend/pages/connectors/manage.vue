<template>
    <div class="flex justify-center px-4 md:px-6 text-sm bg-[#F6F1EA] min-h-full">
        <div class="w-full max-w-5xl py-6 text-[#1f2328]">
            <NuxtLink to="/agents" class="inline-flex items-center gap-1.5 text-[#8A7F70] hover:text-[#C2541E] text-sm mb-4">
                <UIcon name="i-heroicons-chevron-left" class="w-4 h-4" /> {{ $t('connectors.backToAgents') }}
            </NuxtLink>

            <div class="mb-5">
                <h1 class="text-[28px] font-medium text-[#211B14]" style="font-family:'Spectral',serif">{{ $t('connectors.manageTitle') }}</h1>
                <p class="text-[#6b6b6b] text-sm mt-1">{{ $t('connectors.manageSubtitle') }}</p>
            </div>

            <div v-if="!enabled" class="border border-dashed border-[#E9E0D3] rounded-2xl p-10 text-center text-[#8A7F70] bg-[#FCFAF6]">
                {{ $t('connectors.notEnabled') }}
            </div>

            <div v-else class="bg-white border border-[#E9E0D3] rounded-2xl overflow-hidden shadow-sm">
                <!-- header row -->
                <div class="grid grid-cols-[2fr_2fr_1.2fr_1fr_auto] gap-3 px-5 py-3 bg-[#F6F1EA] text-[11px] font-bold uppercase tracking-wide text-[#8A7F70]">
                    <span>{{ $t('connectors.colConnector') }}</span>
                    <span>{{ $t('connectors.colWorkspace') }}</span>
                    <span>{{ $t('connectors.colStatus') }}</span>
                    <span>{{ $t('connectors.colMembers') }}</span>
                    <span></span>
                </div>
                <div v-for="c in catalog" :key="c.key" class="grid grid-cols-[2fr_2fr_1.2fr_1fr_auto] gap-3 px-5 py-4 items-center border-t border-[#E9E0D3] text-[13px]">
                    <span class="flex items-center gap-2.5 font-medium">
                        <span class="w-7 h-7 rounded-lg bg-white border border-[#E9E0D3] flex items-center justify-center p-1">
                            <img :src="c.icon" :alt="c.name" class="w-full h-full object-contain" />
                        </span>{{ c.name }}
                    </span>
                    <span class="text-[#8A7F70] truncate">
                        <template v-if="!c.live">{{ $t('connectors.comingSoon') }}</template>
                        <template v-else-if="templateFor(c.key)">{{ workspaceLabel(c.key) }}</template>
                        <template v-else>{{ $t('connectors.notSet') }}</template>
                    </span>
                    <span>
                        <span v-if="!c.live" class="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#EFE7DA] text-[#8A7F70]">{{ $t('connectors.soon') }}</span>
                        <span v-else-if="templateFor(c.key)" class="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#E7F1E9] text-[#3E7A52]">{{ $t('connectors.configured') }}</span>
                        <span v-else class="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#EFE7DA] text-[#8A7F70]">{{ $t('connectors.draft') }}</span>
                    </span>
                    <span class="text-[#8A7F70]">{{ c.live && templateFor(c.key) ? memberCount(c.key) : '—' }}</span>
                    <span class="flex justify-end gap-2">
                        <template v-if="c.live">
                            <button v-if="templateFor(c.key)" @click="openCfg(c.key)" class="minibtn">{{ $t('common.edit') }}</button>
                            <button v-else @click="openCfg(c.key)" class="minibtn primary">{{ $t('connectors.configure') }}</button>
                        </template>
                        <button v-else disabled class="minibtn opacity-40 cursor-not-allowed">{{ $t('connectors.configure') }}</button>
                    </span>
                </div>
            </div>

            <!-- CONFIG MODAL -->
            <UModal v-model="showCfg">
                <div class="p-6">
                    <h3 class="text-lg text-[#1f2328] mb-1" style="font-family:'Spectral',serif">{{ $t('connectors.configureName', { name: editing.name }) }}</h3>
                    <p class="text-xs text-[#6b6b6b] mb-4">{{ $t('connectors.configureHint') }}</p>
                    <template v-if="editing.fields && editing.fields.includes('server_hostname')">
                        <label class="block text-xs font-semibold text-[#6b6b6b] mb-1">{{ $t('connectors.sqlEndpoint') }}</label>
                        <input v-model="cfg.server_hostname" placeholder="xxxxx.datawarehouse.fabric.microsoft.com" class="cin mb-3" />
                    </template>
                    <label class="block text-xs font-semibold text-[#6b6b6b] mb-1">{{ $t('connectors.tenantId') }}</label>
                    <input v-model="cfg.tenant_id" placeholder="0a8a4f2c-..." class="cin mb-3" />
                    <p class="text-[11px] text-[#9a958c] bg-[#FCFAF6] border border-[#E9E0D3] rounded-lg p-2.5 leading-relaxed">{{ $t('connectors.autoDbNote') }}</p>
                    <div v-if="err" class="text-xs text-[#B4432B] bg-[#F7E7E2] rounded-lg p-2.5 mt-2">{{ err }}</div>
                    <div class="flex justify-end gap-2 mt-4">
                        <button @click="showCfg = false" class="minibtn">{{ $t('common.cancel') }}</button>
                        <button @click="save" :disabled="saving" class="minibtn primary">
                            <Spinner v-if="saving" class="w-3.5 h-3.5 inline" /> {{ $t('connectors.publish') }}
                        </button>
                    </div>
                </div>
            </UModal>
        </div>
    </div>
</template>

<script lang="ts" setup>
import Spinner from '~/components/Spinner.vue'
import { useCan } from '~/composables/usePermissions'
definePageMeta({ auth: true })
const { t } = useI18n()
const toast = useToast()

const enabled = ref(false)
const templates = ref<any[]>([])
const agents = ref<any[]>([])
const canManage = computed(() => useCan('manage_connections'))

const catalog = [
    { key: 'fabric', type: 'ms_fabric', name: 'Microsoft Fabric', icon: '/data_sources_icons/ms_fabric.png', live: true, fields: ['server_hostname', 'tenant_id'] },
    { key: 'powerbi', type: 'powerbi_user', name: 'Power BI (User Sign-in)', icon: '/data_sources_icons/powerbi.png', live: true, fields: ['tenant_id'] },
    { key: 'sharepoint', type: 'sharepoint', name: 'SharePoint', icon: '/data_sources_icons/sharepoint.png', live: false, fields: ['tenant_id'] },
    { key: 'onedrive', type: 'onedrive', name: 'OneDrive', icon: '/data_sources_icons/onedrive.png', live: false, fields: ['tenant_id'] },
]
function templateFor(key: string) {
    const type = catalog.find(c => c.key === key)?.type
    return templates.value.find(tp => tp.type === type) || null
}
function workspaceLabel(key: string) {
    const tpl = templateFor(key)
    const cfg = tpl?.config || {}
    if (cfg.server_hostname) return cfg.server_hostname
    if (cfg.tenant_id) return `tenant ${String(cfg.tenant_id).slice(0, 8)}…`
    return t('connectors.notSet')
}
function memberCount(key: string) {
    const tpl = templateFor(key)
    if (!tpl) return 0
    return (agents.value || []).filter(a => a.template_source_id === tpl.id).length
}

async function loadFlag() {
    try {
        const { data } = await useMyFetch('/organization/hybrid-flags', { method: 'GET' })
        const row = ((data.value as any[]) || []).find(r => r.key === 'PER_USER_CONNECTOR' || r.env_name === 'HYBRID_PER_USER_CONNECTOR')
        enabled.value = !!row?.effective
    } catch { enabled.value = false }
}
async function loadAll() {
    try { const { data } = await useMyFetch('/connectors/available', { method: 'GET' }); templates.value = (data.value as any[]) || [] } catch {}
    try { const { data } = await useMyFetch('/data_sources', { method: 'GET' }); agents.value = (data.value as any[]) || [] } catch {}
}

// config modal
const showCfg = ref(false)
const saving = ref(false)
const err = ref('')
const editingKey = ref('fabric')
const editing = computed(() => catalog.find(c => c.key === editingKey.value) || catalog[0])
const cfg = reactive<{ server_hostname: string; tenant_id: string }>({ server_hostname: '', tenant_id: '' })

function openCfg(key: string) {
    editingKey.value = key
    const tpl = templateFor(key)
    cfg.server_hostname = tpl?.config?.server_hostname || ''
    cfg.tenant_id = tpl?.config?.tenant_id || ''
    err.value = ''
    showCfg.value = true
}
async function save() {
    saving.value = true; err.value = ''
    try {
        const c = editing.value
        const config: any = {}
        if (c.fields.includes('server_hostname')) config.server_hostname = cfg.server_hostname.trim()
        config.tenant_id = cfg.tenant_id.trim() || null
        const existing = templateFor(c.key)
        if (existing) {
            const { error } = await useMyFetch(`/data_sources/${existing.id}`, { method: 'PUT', body: { config } })
            if (error.value) throw error.value
        } else {
            const body = { name: c.name, type: c.type, config, auth_policy: 'user_required', allowed_user_auth_modes: ['device_code'], is_user_template: true }
            const { error } = await useMyFetch('/data_sources', { method: 'POST', body })
            if (error.value) throw error.value
        }
        toast.add({ title: t('connectors.published'), color: 'green', icon: 'i-heroicons-check-circle' })
        showCfg.value = false
        await loadAll()
    } catch (e: any) {
        err.value = e?.data?.detail || e?.message || t('connectors.publishFailed')
    } finally { saving.value = false }
}

onMounted(async () => { await loadFlag(); if (enabled.value) await loadAll() })
</script>

<style scoped>
.minibtn{font-size:12px;font-weight:600;padding:6px 12px;border-radius:9px;border:1px solid #E9E0D3;background:#fff;color:#211B14;cursor:pointer;}
.minibtn:hover{border-color:#C2541E;}
.minibtn.primary{background:#C2541E;color:#fff;border-color:#C2541E;}
.minibtn.primary:hover{background:#A8330F;}
.cin{width:100%;border:1px solid #E9E0D3;border-radius:10px;padding:10px 12px;font-size:13.5px;background:#FCFAF6;font-family:inherit;}
.cin:focus{outline:none;border-color:#C2541E;background:#fff;}
</style>
