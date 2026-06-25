<template>
    <div>
        <div class="mb-4">
            <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Access &amp; Channels</h2>
            <p class="text-xs text-[#6b6b6b] mt-0.5">Decide who can use this agent, which model it runs on, and where it answers.</p>
        </div>

        <!-- WHO CAN USE -->
        <div class="rounded-2xl border border-[#E7E5DD] bg-white p-4 mb-3">
            <div class="flex items-center justify-between mb-1">
                <h3 class="text-sm font-semibold text-[#1f2328] flex items-center gap-1.5" style="font-family: ui-serif, Georgia, serif">
                    <UIcon name="i-heroicons-lock-closed" class="w-4 h-4 text-[#C2683F]" /> Who can use this agent
                </h3>
                <span v-if="savingScope" class="text-[10px] text-[#9a958c] inline-flex items-center gap-1"><Spinner class="h-3 w-3" /> saving…</span>
            </div>
            <p class="text-[11px] text-[#6b6b6b] mb-3">Current access: <span class="font-medium text-[#1f2328]">{{ scopeLabel }}</span></p>
            <div class="space-y-2">
                <label
                    v-for="opt in scopeOptions"
                    :key="opt.value"
                    class="flex items-start gap-2 rounded-xl border p-2.5 transition-colors"
                    :class="[
                        scope === opt.value ? 'border-[#E8C9B5] bg-[#F6EFEA]' : 'border-[#E7E5DD]',
                        canEdit ? 'cursor-pointer hover:border-[#dcd9cf]' : 'opacity-70 cursor-default',
                    ]"
                >
                    <input
                        type="radio"
                        :value="opt.value"
                        :checked="scope === opt.value"
                        :disabled="!canEdit || savingScope"
                        class="mt-0.5 text-[#C2683F] focus:ring-[#C2683F]"
                        @change="setScope(opt.value)"
                    />
                    <span>
                        <span class="block text-xs font-medium text-[#1f2328]">{{ opt.label }}</span>
                        <span class="block text-[11px] text-[#9a958c]">{{ opt.hint }}</span>
                    </span>
                </label>
            </div>

            <!-- Share link (when scope === link and a token exists) -->
            <div v-if="scope === 'link' && shareToken" class="mt-3">
                <label class="block text-[11px] font-medium text-[#6b6b6b] mb-1">Share link</label>
                <div class="flex items-center gap-2">
                    <UInput :model-value="shareUrl" readonly size="sm" class="flex-1" @focus="(e: any) => e.target.select()" />
                    <UButton color="gray" variant="outline" size="xs" icon="i-heroicons-clipboard" @click="copyLink">Copy</UButton>
                </div>
            </div>
        </div>

        <!-- MEMBERS (only when Scoped) -->
        <div v-if="scope === 'private'" class="rounded-2xl border border-[#E7E5DD] bg-white p-4 mb-3">
            <h3 class="text-sm font-semibold text-[#1f2328] flex items-center gap-1.5 mb-1" style="font-family: ui-serif, Georgia, serif">
                <UIcon name="i-heroicons-users" class="w-4 h-4 text-[#C2683F]" /> Members
            </h3>
            <p class="text-[11px] text-[#6b6b6b] mb-3">Only these people can open and use the agent.</p>

            <!-- Add member -->
            <div v-if="canEdit" class="flex items-center gap-2 mb-3">
                <UInput
                    v-model="inviteEmail"
                    type="email"
                    placeholder="teammate@company.com"
                    size="sm"
                    class="flex-1"
                    @keyup.enter="invite"
                />
                <USelectMenu
                    v-model="inviteRole"
                    :options="roleOptions"
                    value-attribute="value"
                    option-attribute="label"
                    size="sm"
                    class="w-28"
                />
                <UButton color="orange" size="xs" :loading="inviting" :disabled="!inviteEmail.trim()" @click="invite">Add</UButton>
            </div>

            <div v-if="loadingMembers" class="flex items-center justify-center py-6 text-[#9a958c]">
                <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
            </div>
            <ul v-else class="divide-y divide-[#F0EEE6] border border-[#F0EEE6] rounded-xl overflow-hidden">
                <li v-for="m in members" :key="m.id" class="flex items-center justify-between px-3 py-2 bg-white">
                    <div class="min-w-0">
                        <div class="flex items-center gap-1.5">
                            <span class="text-xs font-medium text-[#1f2328] truncate">{{ m.user_name || m.user_email || m.user_id }}</span>
                            <span v-if="String(m.user_id) === ownerUserId" class="text-[9px] uppercase tracking-wide text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">Owner</span>
                        </div>
                        <span v-if="m.user_email && m.user_name" class="text-[11px] text-[#9a958c] truncate">{{ m.user_email }}</span>
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                        <USelectMenu
                            v-if="canEdit && String(m.user_id) !== ownerUserId"
                            :model-value="m.role"
                            :options="roleOptions"
                            value-attribute="value"
                            option-attribute="label"
                            size="2xs"
                            class="w-24"
                            @update:model-value="(r: string) => changeRole(m, r)"
                        />
                        <span v-else class="text-[11px] text-[#9a958c]">{{ roleLabel(m.role) }}</span>
                        <button
                            v-if="canEdit && String(m.user_id) !== ownerUserId"
                            class="text-[#9a958c] hover:text-red-500"
                            title="Remove member"
                            @click="removeMember(m)"
                        >
                            <UIcon name="i-heroicons-x-mark" class="w-4 h-4" />
                        </button>
                    </div>
                </li>
                <li v-if="!members.length" class="px-3 py-3 text-[11px] text-[#9a958c] bg-white">No members yet — add a teammate above.</li>
            </ul>
        </div>

        <!-- MODEL (per-agent override) -->
        <div class="rounded-2xl border border-[#E7E5DD] bg-white p-4 mb-3">
            <h3 class="text-sm font-semibold text-[#1f2328] flex items-center gap-1.5 mb-1" style="font-family: ui-serif, Georgia, serif">
                <UIcon name="i-heroicons-cpu-chip" class="w-4 h-4 text-[#C2683F]" /> Model
            </h3>
            <p class="text-[11px] text-[#6b6b6b] mb-3">Pick the LLM this agent uses. Leave on <span class="font-medium">Org default</span> to follow the org-wide setting.</p>
            <div class="flex items-center gap-2">
                <select
                    :value="modelId"
                    :disabled="!canEdit || savingModel || loadingModels"
                    class="flex-1 text-xs text-[#1f2328] bg-white border border-[#E7E5DD] rounded-lg px-3 py-2 focus:outline-none focus:border-[#C2683F] disabled:opacity-60"
                    @change="(e: any) => setModel(e.target.value)"
                >
                    <option value="">Org default</option>
                    <option v-for="m in models" :key="m.id || m.model_id" :value="m.model_id || m.id">
                        {{ m.name || m.model_id }}{{ m.is_default ? ' (org default)' : '' }}
                    </option>
                </select>
                <span v-if="savingModel" class="text-[10px] text-[#9a958c] inline-flex items-center gap-1"><Spinner class="h-3 w-3" /></span>
            </div>
            <p v-if="loadingModels" class="text-[10px] text-[#9a958c] mt-1.5">Loading models…</p>
        </div>

        <!-- CONNECTION (read-only summary) -->
        <div class="rounded-2xl border border-[#E7E5DD] bg-white p-4 mb-3">
            <h3 class="text-sm font-semibold text-[#1f2328] flex items-center gap-1.5 mb-1" style="font-family: ui-serif, Georgia, serif">
                <UIcon name="i-heroicons-signal" class="w-4 h-4 text-[#C2683F]" /> Connections
            </h3>
            <p class="text-[11px] text-[#6b6b6b] mb-3">Data sources this agent is grounded on. Manage them in the Connection tab.</p>
            <div v-if="!sources.length" class="text-[11px] text-[#9a958c] py-2">No sources pinned yet.</div>
            <ul v-else class="space-y-1.5">
                <li v-for="s in sources" :key="s.id" class="flex items-center justify-between gap-2 rounded-lg border border-[#F0EEE6] bg-[#FBFAF6] px-3 py-2">
                    <div class="flex items-center gap-2 min-w-0">
                        <DataSourceIcon v-if="s.type" class="h-4 shrink-0" :type="s.type" />
                        <UIcon v-else name="i-heroicons-circle-stack" class="w-4 h-4 shrink-0 text-[#9a958c]" />
                        <span class="text-xs font-medium text-[#1f2328] truncate">{{ s.name || s.agent_id }}</span>
                    </div>
                    <span class="text-[10px] text-[#9a958c] uppercase tracking-wide shrink-0">{{ credentialMode(s) }}</span>
                </li>
            </ul>
        </div>

        <!-- CHANNELS -->
        <div class="rounded-2xl border border-[#E7E5DD] bg-white p-4">
            <div class="flex items-center justify-between mb-1">
                <h3 class="text-sm font-semibold text-[#1f2328] flex items-center gap-1.5" style="font-family: ui-serif, Georgia, serif">
                    <UIcon name="i-heroicons-megaphone" class="w-4 h-4 text-[#C2683F]" /> Channels
                </h3>
                <button
                    v-if="canEdit && !channelsUnavailable"
                    type="button"
                    class="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b6b6b] bg-white border border-[#E7E5DD] rounded-lg px-3 py-1.5 hover:bg-[#faf8f3] hover:border-[#dcd9cf] transition-colors"
                    @click="openTelegramModal"
                >
                    <UIcon name="i-heroicons-plus" class="w-3.5 h-3.5" /> Add channel
                </button>
            </div>
            <p class="text-[11px] text-[#6b6b6b] mb-3">Let people reach this agent outside the app — e.g. a Telegram bot.</p>

            <div v-if="channelsUnavailable" class="text-[11px] text-[#9a958c] py-2 flex items-center gap-1.5">
                <UIcon name="i-heroicons-information-circle" class="w-3.5 h-3.5" /> Channels aren't enabled for this org yet.
            </div>
            <div v-else-if="loadingChannels" class="flex items-center justify-center py-6 text-[#9a958c]">
                <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
            </div>
            <ul v-else-if="channels.length" class="space-y-1.5">
                <li v-for="c in channels" :key="c.id" class="flex items-center justify-between gap-2 rounded-lg border border-[#F0EEE6] bg-[#FBFAF6] px-3 py-2">
                    <div class="flex items-center gap-2 min-w-0">
                        <UIcon name="i-heroicons-paper-airplane" class="w-4 h-4 shrink-0 text-[#1F6F8B]" />
                        <div class="min-w-0">
                            <div class="text-xs font-medium text-[#1f2328] truncate">
                                {{ platformLabel(c.platform_type) }}<span v-if="c.display" class="text-[#9a958c] font-normal"> · {{ c.display }}</span>
                            </div>
                            <div class="text-[10px] text-[#9a958c]">Audience: {{ audienceLabel(c.audience) }}</div>
                        </div>
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                        <span class="text-[10px] font-medium px-1.5 py-0.5 rounded" :class="c.is_active ? 'bg-[#E7F2EC] text-[#2f7a52]' : 'bg-[#F3F0E9] text-[#9a958c]'">{{ c.is_active ? 'On' : 'Off' }}</span>
                        <button
                            v-if="canEdit"
                            type="button"
                            class="text-[11px] font-medium text-[#6b6b6b] border border-[#E7E5DD] rounded-md px-2 py-1 hover:bg-[#faf8f3]"
                            @click="toggleChannel(c)"
                        >
                            {{ c.is_active ? 'Disable' : 'Enable' }}
                        </button>
                        <button
                            v-if="canEdit"
                            type="button"
                            class="text-[#9a958c] hover:text-red-500"
                            title="Delete channel"
                            @click="deleteChannel(c)"
                        >
                            <UIcon name="i-heroicons-trash" class="w-4 h-4" />
                        </button>
                    </div>
                </li>
            </ul>
            <p v-else class="text-[11px] text-[#9a958c] py-2">No channels yet — add a Telegram bot to let people chat with this agent.</p>
        </div>

        <!-- Telegram modal -->
        <UModal v-model="showTelegram" :ui="{ width: 'sm:max-w-md' }">
            <div class="p-6">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-lg font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, serif">Add Telegram channel</h2>
                    <button class="text-[#9a958c] hover:text-[#6b6b6b]" @click="showTelegram = false">
                        <UIcon name="i-heroicons-x-mark" class="w-5 h-5" />
                    </button>
                </div>
                <label class="block text-xs font-medium text-[#1f2328] mb-1">Bot token</label>
                <p class="text-[11px] text-[#9a958c] mb-2">Create a bot with @BotFather on Telegram and paste its token here.</p>
                <UInput v-model="botToken" type="password" size="sm" placeholder="123456:ABC-DEF…" class="mb-4" />

                <label class="block text-xs font-medium text-[#1f2328] mb-2">Who can use the bot</label>
                <div class="space-y-2 mb-5">
                    <label
                        v-for="opt in audienceOptions"
                        :key="opt.value"
                        class="flex items-start gap-2 rounded-xl border p-2.5 cursor-pointer transition-colors"
                        :class="audience === opt.value ? 'border-[#E8C9B5] bg-[#F6EFEA]' : 'border-[#E7E5DD] hover:border-[#dcd9cf]'"
                    >
                        <input type="radio" :value="opt.value" v-model="audience" class="mt-0.5 text-[#C2683F] focus:ring-[#C2683F]" />
                        <span>
                            <span class="block text-xs font-medium text-[#1f2328]">{{ opt.label }}</span>
                            <span class="block text-[11px] text-[#9a958c]">{{ opt.hint }}</span>
                        </span>
                    </label>
                </div>

                <div class="flex justify-end gap-2">
                    <UButton color="gray" variant="outline" size="sm" @click="showTelegram = false">Cancel</UButton>
                    <UButton color="orange" size="sm" :loading="addingChannel" :disabled="!botToken.trim()" @click="addTelegram">Add channel</UButton>
                </div>
            </div>
        </UModal>
    </div>
</template>

<script setup lang="ts">
import Spinner from '~/components/Spinner.vue'

interface Member {
    id: string
    user_id: string
    role: string
    user_name?: string | null
    user_email?: string | null
}
interface Source { id: string; agent_id: string; name?: string | null; type?: string | null; credential_mode?: string | null }
interface Channel { id: string; platform_type: string; audience: string; is_active: boolean; display?: string | null }
interface Studio { id: string; share_scope?: string; share_token?: string | null; config?: Record<string, any> }

const props = defineProps<{
    studioId: string
    studio: Studio | null
    sources: Source[]
    canEdit: boolean
    ownerUserId: string
}>()

const emit = defineEmits<{
    'share-updated': [payload: { share_scope: string; share_token: string | null }]
    'config-updated': [config: Record<string, any>]
}>()

const { t } = useI18n()
const toast = useToast()

// ---- WHO CAN USE -------------------------------------------------------
const scope = ref(props.studio?.share_scope || 'private')
const shareToken = ref<string | null>(props.studio?.share_token ?? null)
const savingScope = ref(false)

const scopeOptions = [
    { value: 'org', label: 'Master — everyone in the org', hint: 'Any member of your organization can open and use this agent.' },
    { value: 'private', label: 'Scoped — only chosen members', hint: 'Only people you add below can use it.' },
    { value: 'link', label: 'Link — anyone with the link', hint: 'Share a link; no sign-in needed to view.' },
]
const scopeLabel = computed(() => scopeOptions.find(o => o.value === scope.value)?.label.split(' — ')[0] || scope.value)

const shareUrl = computed(() => {
    if (!shareToken.value) return ''
    const origin = typeof window !== 'undefined' ? window.location.origin : ''
    return `${origin}/studios/shared/${shareToken.value}`
})

const setScope = async (value: string) => {
    if (!props.canEdit || value === scope.value) return
    const prev = scope.value
    scope.value = value
    savingScope.value = true
    try {
        const { data, error } = await useMyFetch<any>(`/studios/${props.studioId}/share`, {
            method: 'PATCH',
            body: { share_scope: value },
        })
        if (error?.value) throw error.value
        const updated = data.value || {}
        scope.value = updated.share_scope || value
        shareToken.value = updated.share_token ?? shareToken.value
        emit('share-updated', { share_scope: scope.value, share_token: shareToken.value })
        toast.add({ title: 'Access updated', color: 'green', icon: 'i-heroicons-check-circle' })
    } catch (e: any) {
        scope.value = prev
        console.error('Failed to update access:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    } finally {
        savingScope.value = false
    }
}

const copyLink = async () => {
    if (!shareUrl.value) return
    try {
        await navigator.clipboard.writeText(shareUrl.value)
        toast.add({ title: 'Link copied', color: 'green', icon: 'i-heroicons-check-circle' })
    } catch {
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    }
}

// ---- MEMBERS -----------------------------------------------------------
const members = ref<Member[]>([])
const loadingMembers = ref(false)
const inviteEmail = ref('')
const inviteRole = ref('viewer')
const inviting = ref(false)

const roleOptions = [
    { value: 'viewer', label: 'Viewer' },
    { value: 'editor', label: 'Editor' },
    { value: 'owner', label: 'Owner' },
]
const roleLabel = (r: string) => roleOptions.find(o => o.value === r)?.label || r

const fetchMembers = async () => {
    loadingMembers.value = true
    try {
        const { data, error } = await useMyFetch<Member[]>(`/studios/${props.studioId}/members`, { method: 'GET' })
        if (error?.value) throw error.value
        members.value = data.value || []
    } catch (e: any) {
        console.error('Failed to load members:', e)
    } finally {
        loadingMembers.value = false
    }
}

const invite = async () => {
    const email = inviteEmail.value.trim()
    if (!email) return
    inviting.value = true
    try {
        const { error } = await useMyFetch(`/studios/${props.studioId}/members`, {
            method: 'POST',
            body: { email, role: inviteRole.value },
        })
        if (error?.value) throw error.value
        inviteEmail.value = ''
        inviteRole.value = 'viewer'
        toast.add({ title: 'Member added', color: 'green', icon: 'i-heroicons-check-circle' })
        await fetchMembers()
    } catch (e: any) {
        console.error('Failed to add member:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    } finally {
        inviting.value = false
    }
}

const changeRole = async (m: Member, role: string) => {
    if (!role || role === m.role) return
    try {
        const { error } = await useMyFetch(`/studios/${props.studioId}/members/${m.user_id}`, {
            method: 'PATCH',
            body: { role },
        })
        if (error?.value) throw error.value
        await fetchMembers()
    } catch (e: any) {
        console.error('Failed to change role:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    }
}

const removeMember = async (m: Member) => {
    if (!window.confirm('Remove this member?')) return
    try {
        const { error } = await useMyFetch(`/studios/${props.studioId}/members/${m.user_id}`, { method: 'DELETE' })
        if (error?.value) throw error.value
        toast.add({ title: 'Member removed', color: 'green', icon: 'i-heroicons-check-circle' })
        await fetchMembers()
    } catch (e: any) {
        console.error('Failed to remove member:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    }
}

// ---- MODEL -------------------------------------------------------------
const models = ref<any[]>([])
const loadingModels = ref(false)
const savingModel = ref(false)
const modelId = computed(() => props.studio?.config?.model_id || '')

const loadModels = async () => {
    loadingModels.value = true
    try {
        const { data } = await useMyFetch<any[]>('/api/llm/models?is_enabled=true')
        models.value = Array.isArray(data.value) ? data.value : []
    } catch (e: any) {
        console.error('Failed to load models:', e)
    } finally {
        loadingModels.value = false
    }
}

const setModel = async (value: string) => {
    if (!props.canEdit) return
    savingModel.value = true
    try {
        // Preserve every other config key — only change model_id (empty = clear override).
        const nextConfig = { ...(props.studio?.config || {}) }
        if (value) nextConfig.model_id = value
        else delete nextConfig.model_id
        const { error } = await useMyFetch(`/studios/${props.studioId}`, {
            method: 'PATCH',
            body: { config: nextConfig },
        })
        if (error?.value) throw error.value
        emit('config-updated', nextConfig)
        toast.add({ title: value ? 'Model updated' : 'Reverted to org default', color: 'green', icon: 'i-heroicons-check-circle' })
    } catch (e: any) {
        console.error('Failed to update model:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    } finally {
        savingModel.value = false
    }
}

// ---- CONNECTION --------------------------------------------------------
const credentialMode = (s: Source) => {
    const m = (s.credential_mode || '').toLowerCase()
    if (m === 'shared' || m === 'org') return 'shared creds'
    if (m === 'user' || m === 'per_user') return 'per-user creds'
    return s.type || 'data source'
}

// ---- CHANNELS ----------------------------------------------------------
const channels = ref<Channel[]>([])
const loadingChannels = ref(false)
const channelsUnavailable = ref(false)

const platformLabel = (p: string) => p === 'telegram' ? 'Telegram' : (p || 'Channel')
const audienceLabel = (a: string) => a === 'anyone' ? 'Anyone' : 'Members only'

const fetchChannels = async () => {
    loadingChannels.value = true
    try {
        const { data, error } = await useMyFetch<Channel[]>(`/studios/${props.studioId}/channels`, { method: 'GET' })
        if (error?.value) throw error.value
        channels.value = data.value || []
        channelsUnavailable.value = false
    } catch (e: any) {
        // 404 / not enabled → hide the section gracefully, never crash.
        if (e?.statusCode === 404 || e?.status === 404) channelsUnavailable.value = true
        else console.error('Failed to load channels:', e)
    } finally {
        loadingChannels.value = false
    }
}

// Telegram modal
const showTelegram = ref(false)
const botToken = ref('')
const audience = ref<'members' | 'anyone'>('members')
const addingChannel = ref(false)
const audienceOptions = [
    { value: 'members', label: 'Members only', hint: 'Only agent members can talk to the bot.' },
    { value: 'anyone', label: 'Anyone', hint: 'Anyone who finds the bot can chat with it.' },
]

const openTelegramModal = () => {
    botToken.value = ''
    audience.value = 'members'
    showTelegram.value = true
}

const addTelegram = async () => {
    if (!botToken.value.trim()) return
    addingChannel.value = true
    try {
        const { error } = await useMyFetch(`/studios/${props.studioId}/channels/telegram`, {
            method: 'POST',
            body: { bot_token: botToken.value.trim(), audience: audience.value },
        })
        if (error?.value) throw error.value
        showTelegram.value = false
        botToken.value = ''
        toast.add({ title: 'Channel added', color: 'green', icon: 'i-heroicons-check-circle' })
        await fetchChannels()
    } catch (e: any) {
        console.error('Failed to add channel:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    } finally {
        addingChannel.value = false
    }
}

const toggleChannel = async (c: Channel) => {
    const action = c.is_active ? 'disable' : 'enable'
    try {
        const { error } = await useMyFetch(`/studios/${props.studioId}/channels/${c.id}/${action}`, { method: 'POST' })
        if (error?.value) throw error.value
        await fetchChannels()
    } catch (e: any) {
        console.error('Failed to toggle channel:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    }
}

const deleteChannel = async (c: Channel) => {
    if (!window.confirm('Delete this channel?')) return
    try {
        const { error } = await useMyFetch(`/studios/${props.studioId}/channels/${c.id}`, { method: 'DELETE' })
        if (error?.value) throw error.value
        toast.add({ title: 'Channel deleted', color: 'green', icon: 'i-heroicons-check-circle' })
        await fetchChannels()
    } catch (e: any) {
        console.error('Failed to delete channel:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    }
}

// Keep local scope/token in sync if the parent studio changes.
watch(() => props.studio, (s) => {
    scope.value = s?.share_scope || 'private'
    shareToken.value = s?.share_token ?? null
})

onMounted(() => {
    fetchMembers()
    loadModels()
    fetchChannels()
})
</script>
