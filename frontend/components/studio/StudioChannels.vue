<template>
    <div>
        <div class="mb-4">
            <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: 'Spectral', ui-serif, Georgia, serif">Channels</h2>
            <p class="text-xs text-[#6b6b6b] mt-0.5">
                Let people reach <span class="font-medium text-[#1f2328]">this agent</span> outside the app. Each channel answers only from this agent's data scope.
            </p>
        </div>

        <div v-if="channelsUnavailable" class="rounded-2xl border border-[#E9E0D3] bg-white p-6 text-[12px] text-[#9a958c] flex items-center gap-2">
            <UIcon name="i-heroicons-information-circle" class="w-4 h-4" /> Channels aren't enabled for this org yet.
        </div>

        <!-- TWO-PANE: platform list (left) + detail (right) -->
        <div v-else class="rounded-2xl border border-[#E9E0D3] bg-white p-4">
            <div class="text-[11px] text-[#8A4527] bg-[#FBF4EF] border border-[#f0ddd0] rounded-lg px-3 py-2 mb-4 flex items-start gap-1.5">
                <UIcon name="i-heroicons-shield-check" class="w-3.5 h-3.5 shrink-0 mt-0.5" />
                <span>Every channel answers only from <span class="font-medium">this agent's</span> data — whichever connection you pick.</span>
            </div>

            <div class="flex flex-col md:flex-row gap-4">
                <!-- left: platform list -->
                <ul class="md:w-64 shrink-0 space-y-0.5">
                    <li
                        v-for="ch in channelCatalog"
                        :key="ch.key"
                        class="group flex items-center gap-2.5 rounded-lg px-2.5 py-2 cursor-pointer transition-colors"
                        :class="selected === ch.key ? 'bg-[#F6EFEA] border border-[#E8C9B5]' : 'border border-transparent hover:bg-[#faf8f3]'"
                        @click="selected = ch.key"
                    >
                        <span class="w-6 h-6 shrink-0 flex items-center justify-center">
                            <img v-if="ch.iconType === 'img'" :src="ch.icon" :alt="ch.name" class="w-6 h-6" />
                            <UIcon v-else :name="ch.icon" class="w-5 h-5 text-[#6b6b6b]" />
                        </span>
                        <span class="flex-1 min-w-0 text-sm text-[#1f2328] truncate">{{ ch.name }}</span>
                        <span
                            class="w-2 h-2 shrink-0 rounded-full"
                            :class="isChannelOn(ch.key) ? 'bg-green-500' : 'bg-gray-300'"
                            :title="isChannelOn(ch.key) ? 'Active' : 'Not connected'"
                        />
                    </li>
                </ul>

                <!-- right: detail pane -->
                <div class="flex-1 min-w-0 rounded-xl border border-[#F0EEE6] bg-[#F9F6F0] p-5">
                    <div v-if="loadingChannels" class="flex items-center justify-center py-12 text-[#9a958c]">
                        <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">{{ $t('common.loading') }}</span>
                    </div>

                    <!-- empty / nothing selected -->
                    <div v-else-if="!selected" class="text-center py-10">
                        <div class="w-12 h-12 mx-auto rounded-xl border border-[#E9E0D3] bg-white flex items-center justify-center mb-3">
                            <UIcon name="i-heroicons-squares-plus" class="w-6 h-6 text-[#C2541E]" />
                        </div>
                        <p class="text-sm font-medium text-[#1f2328]" style="font-family: 'Spectral', ui-serif, Georgia, serif">Wire this agent to your tools</p>
                        <p class="text-[12px] text-[#9a958c] mt-1 max-w-xs mx-auto">
                            Pick a channel on the left. People there chat with this agent and see only its data.
                        </p>
                    </div>

                    <!-- selected platform detail -->
                    <div v-else>
                        <div class="flex items-start justify-between gap-3 mb-1">
                            <div class="flex items-center gap-2.5 min-w-0">
                                <span class="w-7 h-7 shrink-0 flex items-center justify-center">
                                    <img v-if="selectedMeta?.iconType === 'img'" :src="selectedMeta?.icon" :alt="selectedMeta?.name" class="w-7 h-7" />
                                    <UIcon v-else :name="selectedMeta?.icon || 'i-heroicons-megaphone'" class="w-6 h-6 text-[#6b6b6b]" />
                                </span>
                                <h3 class="text-sm font-semibold text-[#1f2328] truncate" style="font-family: 'Spectral', ui-serif, Georgia, serif">{{ selectedMeta?.name }}</h3>
                            </div>
                            <span
                                class="text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0"
                                :class="statusClass(selected)"
                            >
                                {{ statusLabel(selected) }}
                            </span>
                        </div>
                        <p class="text-[12px] text-[#6b6b6b] mb-4">{{ selectedMeta?.blurb }}</p>

                        <!-- connection mode: org default vs custom -->
                        <div class="space-y-2 mb-4">
                            <label
                                v-for="opt in connModeOptions"
                                :key="opt.value"
                                class="flex items-start gap-2 rounded-xl border p-2.5 transition-colors"
                                :class="[
                                    modeFor(selected) === opt.value ? 'border-[#E8C9B5] bg-[#F6EFEA]' : 'border-[#E9E0D3] bg-white',
                                    canEdit ? 'cursor-pointer hover:border-[#dcd9cf]' : 'opacity-70 cursor-default',
                                ]"
                            >
                                <input
                                    type="radio"
                                    :checked="modeFor(selected) === opt.value"
                                    :disabled="!canEdit"
                                    class="mt-0.5 text-[#C2541E] focus:ring-[#C2541E]"
                                    @change="setMode(selected, opt.value)"
                                />
                                <span>
                                    <span class="block text-xs font-medium text-[#1f2328]">{{ opt.label }}</span>
                                    <span class="block text-[11px] text-[#9a958c]">{{ opt.value === 'custom' ? opt.hint.replace('{name}', selectedMeta?.name || 'this platform') : opt.hint }}</span>
                                </span>
                            </label>
                        </div>

                        <!-- GLOBAL / org default -->
                        <template v-if="modeFor(selected) === 'global'">
                            <div class="text-[11px] text-[#6b6b6b] rounded-xl border border-[#F0EEE6] bg-[#F9F6F0] px-3 py-2.5">
                                Reaches this agent through the organization's shared {{ selectedMeta?.name }}, set up in
                                <span class="font-medium text-[#1f2328]">Settings → Integrations</span>. Nothing to configure here.
                            </div>
                            <div v-if="canEdit && channelFor(selected)" class="mt-3 flex items-center gap-2">
                                <span class="text-[11px] text-[#9a958c]">A custom connection exists — remove it to fall back to the org default.</span>
                                <UButton color="red" variant="ghost" size="xs" icon="i-heroicons-trash" @click="deleteChannel(channelFor(selected)!)">Remove custom</UButton>
                            </div>
                        </template>

                        <!-- CUSTOM / agent-owned -->
                        <template v-else>
                            <div v-if="channelFor(selected)" class="text-[11px] text-[#9a958c] mb-4 space-y-1">
                                <div>Audience: <span class="text-[#1f2328] font-medium">{{ audienceLabel(channelFor(selected)!.audience) }}</span></div>
                            </div>

                            <div v-if="canEdit" class="flex flex-wrap items-center gap-2">
                                <UButton color="orange" size="xs" @click="openChannelModal(selected)">
                                    {{ channelFor(selected) ? 'Reconfigure' : 'Set up' }}
                                </UButton>
                                <template v-if="channelFor(selected)">
                                    <UButton color="gray" variant="outline" size="xs" @click="toggleChannel(channelFor(selected)!)">
                                        {{ channelFor(selected)!.is_active ? 'Disable' : 'Enable' }}
                                    </UButton>
                                    <UButton color="red" variant="ghost" size="xs" icon="i-heroicons-trash" @click="deleteChannel(channelFor(selected)!)">Delete</UButton>
                                </template>
                            </div>
                            <p v-else class="text-[11px] text-[#9a958c]">You need editor access to configure channels.</p>
                        </template>
                    </div>
                </div>
            </div>
        </div>

        <!-- Reused org config modals (scoped to this studio) -->
        <UModal v-model="showSlack" :ui="{ width: 'sm:max-w-lg' }">
            <div class="relative">
                <SlackIntegrationModal :integrated="false" :studio-id="studioId" @close="showSlack = false" @updated="onChannelAdded(() => showSlack = false)" />
            </div>
        </UModal>
        <UModal v-model="showTeams" :ui="{ width: 'sm:max-w-lg' }">
            <div class="relative">
                <TeamsIntegrationModal :integrated="false" :studio-id="studioId" @close="showTeams = false" @updated="onChannelAdded(() => showTeams = false)" />
            </div>
        </UModal>
        <UModal v-model="showWhatsApp" :ui="{ width: 'sm:max-w-lg' }">
            <div class="relative">
                <WhatsAppIntegrationModal :integrated="false" :studio-id="studioId" @close="showWhatsApp = false" @updated="onChannelAdded(() => showWhatsApp = false)" />
            </div>
        </UModal>
        <UModal v-model="showEmail" :ui="{ width: 'sm:max-w-2xl' }">
            <div class="relative">
                <EmailIntegrationModal :integrated="false" :studio-id="studioId" @close="showEmail = false" @updated="onChannelAdded(() => showEmail = false)" />
            </div>
        </UModal>

        <!-- Telegram modal -->
        <UModal v-model="showTelegram" :ui="{ width: 'sm:max-w-md' }">
            <div class="p-6">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-lg font-medium text-[#1f2328]" style="font-family: 'Spectral', ui-serif, Georgia, serif">Add Telegram channel</h2>
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
                        :class="audience === opt.value ? 'border-[#E8C9B5] bg-[#F6EFEA]' : 'border-[#E9E0D3] hover:border-[#dcd9cf]'"
                    >
                        <input type="radio" :value="opt.value" v-model="audience" class="mt-0.5 text-[#C2541E] focus:ring-[#C2541E]" />
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
import SlackIntegrationModal from '~/components/SlackIntegrationModal.vue'
import TeamsIntegrationModal from '~/components/TeamsIntegrationModal.vue'
import WhatsAppIntegrationModal from '~/components/WhatsAppIntegrationModal.vue'
import EmailIntegrationModal from '~/components/EmailIntegrationModal.vue'

interface Channel { id: string; platform_type: string; audience: string; is_active: boolean; display?: string | null }

const props = defineProps<{
    studioId: string
    canEdit: boolean
}>()

const { t } = useI18n()
const toast = useToast()

const channels = ref<Channel[]>([])
const loadingChannels = ref(false)
const channelsUnavailable = ref(false)
const selected = ref<string>('slack')

// Mirrors the org Settings → Integrations grid (same icons/labels), scoped to THIS studio.
const channelCatalog = [
    { key: 'slack', name: 'Slack', iconType: 'img', icon: '/icons/slack.png', blurb: 'Agent-scoped Slack app. DMs and mentions answer only from this agent\'s data.' },
    { key: 'teams', name: 'Microsoft Teams', iconType: 'img', icon: '/icons/teams.png', blurb: 'A Teams bot wired to this agent. Replies stay within its data scope.' },
    { key: 'whatsapp', name: 'WhatsApp', iconType: 'img', icon: '/icons/whatsapp.png', blurb: 'WhatsApp Cloud API number routed to this agent.' },
    { key: 'email', name: 'AI Mailbox', iconType: 'uicon', icon: 'i-heroicons-sparkles', blurb: 'An inbox this agent answers from. Set its outbound sender in the Email / SMTP tab.' },
    { key: 'telegram', name: 'Telegram', iconType: 'uicon', icon: 'i-heroicons-paper-airplane', blurb: 'A Telegram bot that talks to this agent.' },
    { key: 'mcp', name: 'MCP Server', iconType: 'uicon', icon: 'i-heroicons-bolt', blurb: 'Expose this agent as an MCP server for tools that speak MCP.' },
] as const

const selectedMeta = computed(() => channelCatalog.find(c => c.key === selected.value) || null)
const audienceLabel = (a: string) => a === 'anyone' ? 'Anyone' : 'Org members only'
const channelFor = (key: string) => channels.value.find(c => c.platform_type === key) || null
const isChannelOn = (key: string) => !!channelFor(key)?.is_active

// Connection mode per platform: 'global' (org default) vs 'custom' (this agent's own).
// Derived from data — a per-studio channel row = custom; none = org default.
// A local override lets the user flip to 'custom' before any row exists.
const connModeOptions = [
    { value: 'global', label: 'Use organization default', hint: 'Reach this agent through the org-wide connection. No setup needed.' },
    { value: 'custom', label: 'Custom for this agent', hint: 'Connect this agent\'s own {name}.' },
] as const
const modeOverride = ref<Record<string, 'global' | 'custom'>>({})
const modeFor = (key: string): 'global' | 'custom' =>
    modeOverride.value[key] ?? (channelFor(key) ? 'custom' : 'global')
const setMode = (key: string, m: 'global' | 'custom') => {
    modeOverride.value = { ...modeOverride.value, [key]: m }
}

const statusLabel = (key: string) => {
    if (modeFor(key) === 'global') return '○ Org default'
    return isChannelOn(key) ? '● Connected' : '○ Not connected'
}
const statusClass = (key: string) => {
    if (modeFor(key) === 'custom' && isChannelOn(key)) return 'bg-[#E7F2EC] text-[#2f7a52]'
    return 'bg-[#F3F0E9] text-[#9a958c]'
}

// modals
const showSlack = ref(false)
const showTeams = ref(false)
const showWhatsApp = ref(false)
const showEmail = ref(false)

const openChannelModal = (key: string) => {
    if (channelsUnavailable.value) return
    if (key === 'slack') showSlack.value = true
    else if (key === 'teams') showTeams.value = true
    else if (key === 'whatsapp') showWhatsApp.value = true
    else if (key === 'email') showEmail.value = true
    else if (key === 'telegram') openTelegramModal()
    else if (key === 'mcp') addMcp()
}

const onChannelAdded = async (close: () => void) => {
    close()
    await fetchChannels()
}

const addMcp = async () => {
    if (channelFor('mcp')) {
        toast.add({ title: 'MCP is already enabled for this agent', color: 'green', icon: 'i-heroicons-check-circle' })
        return
    }
    try {
        const { error } = await useMyFetch(`/studios/${props.studioId}/channels/mcp`, {
            method: 'POST',
            body: { audience: 'members' },
        })
        if (error?.value) throw error.value
        toast.add({ title: 'MCP enabled', color: 'green', icon: 'i-heroicons-check-circle' })
        await fetchChannels()
    } catch (e: any) {
        console.error('Failed to enable MCP:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    }
}

const fetchChannels = async () => {
    loadingChannels.value = true
    try {
        const { data, error } = await useMyFetch<Channel[]>(`/studios/${props.studioId}/channels`, { method: 'GET' })
        if (error?.value) throw error.value
        channels.value = data.value || []
        channelsUnavailable.value = false
    } catch (e: any) {
        if (e?.statusCode === 404 || e?.status === 404) channelsUnavailable.value = true
        else console.error('Failed to load channels:', e)
    } finally {
        loadingChannels.value = false
    }
}

// Telegram
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
        setMode(c.platform_type, 'global')  // reverted to org default
        toast.add({ title: 'Channel removed — using org default', color: 'green', icon: 'i-heroicons-check-circle' })
        await fetchChannels()
    } catch (e: any) {
        console.error('Failed to delete channel:', e)
        toast.add({ title: t('studio.actionFailed') || 'Action failed', color: 'red' })
    }
}

onMounted(fetchChannels)
</script>
