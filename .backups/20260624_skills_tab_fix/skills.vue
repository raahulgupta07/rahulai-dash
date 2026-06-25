<template>
    <div class="flex justify-center px-4 md:px-6 text-sm bg-[#FBFAF6] min-h-full">
        <div class="w-full max-w-7xl py-2 text-[#1f2328]">
            <!-- Header -->
            <div class="flex items-start justify-between gap-4 mb-6">
                <div>
                    <h1
                        class="text-2xl font-semibold text-[#1f2328] tracking-tight flex items-center"
                        style="font-family: ui-serif, Georgia, 'Times New Roman', serif"
                    >Skills</h1>
                    <p class="mt-2 text-[#6b6b6b] leading-relaxed max-w-2xl">
                        Reusable SKILL.md playbooks the agent can load on demand. Authored from a
                        solved chat via "Save as skill", scoped personal, org, or global.
                    </p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                    <!-- Author from completion (real flow) -->
                    <div class="flex items-center gap-1.5 rounded-xl border border-[#E7E5DD] bg-white px-2.5 py-1.5 focus-within:border-[#C2683F]">
                        <Icon name="heroicons:bars-3-bottom-left" class="w-4 h-4 text-[#9a958c] shrink-0" />
                        <input
                            v-model="completionId"
                            type="text"
                            placeholder="Completion ID…"
                            class="w-40 bg-transparent text-sm outline-none placeholder:text-[#9a958c]"
                            :disabled="authoring"
                            @keyup.enter="authorFromCompletion"
                        />
                    </div>
                    <button
                        type="button"
                        class="inline-flex items-center gap-1.5 rounded-lg border border-[#E7E5DD] bg-white px-3 py-2 text-sm font-medium text-[#1f2328] cursor-pointer transition-colors hover:bg-[#F4F1EA] disabled:opacity-50 disabled:cursor-not-allowed"
                        :disabled="!completionId.trim() || authoring"
                        @click="authorFromCompletion"
                    >
                        <Icon
                            :name="authoring ? 'heroicons:arrow-path' : 'heroicons:sparkles'"
                            class="w-4 h-4 text-[#C2683F]"
                            :class="{ 'animate-spin': authoring }"
                        />
                        Author from completion
                    </button>
                </div>
            </div>

            <!-- Author error -->
            <div v-if="authorError" class="mb-5 rounded-xl border border-[#E7E5DD] bg-[#F3E7DF] p-3 text-xs text-[#A8542F]">
                {{ authorError }}
            </div>

            <!-- Loading -->
            <div v-if="loading" class="flex items-center justify-center py-20 text-[#9a958c]">
                <Icon name="heroicons:arrow-path" class="w-5 h-5 animate-spin me-2" />
                <span class="text-sm">Loading skills…</span>
            </div>

            <!-- Error -->
            <div v-else-if="error" class="rounded-2xl border border-[#E7E5DD] bg-[#F3E7DF] p-4 text-sm text-[#A8542F]">
                {{ error }}
                <button
                    type="button"
                    class="ms-2 rounded-lg px-2 py-0.5 text-xs font-medium text-[#C2683F] hover:bg-white/60"
                    @click="fetchSkills"
                >
                    Retry
                </button>
            </div>

            <template v-else>
                <!-- Tabs -->
                <div class="flex items-center gap-1 border-b border-[#E7E5DD] mb-5">
                    <button
                        v-for="tab in [
                            { label: 'All', count: skills.length },
                            { label: 'Personal', count: skills.filter(s => scopeLabel(s.scope) === 'Personal').length },
                            { label: 'Organization', count: skills.filter(s => scopeLabel(s.scope) === 'Organization').length },
                            { label: 'Global', count: skills.filter(s => scopeLabel(s.scope) === 'Global').length },
                        ]"
                        :key="tab.label"
                        type="button"
                        @click="activeTab = tab.label as any"
                        class="-mb-px flex items-center gap-1.5 rounded-t-lg px-3 py-2 text-sm transition"
                        :class="tab.label === activeTab
                            ? 'bg-[#ECEAE1] text-[#1f2328] font-medium border-b-2 border-[#C2683F]'
                            : 'text-[#6b6b6b] hover:text-[#1f2328] hover:bg-[#F4F1EA] border-b-2 border-transparent'"
                    >
                        {{ tab.label }}
                        <span
                            class="rounded-full px-1.5 py-0.5 text-[11px]"
                            :class="tab.label === activeTab ? 'bg-white text-[#6b6b6b]' : 'bg-[#ECEAE1] text-[#9a958c]'"
                        >{{ tab.count }}</span>
                    </button>
                </div>

                <!-- Summary strip -->
                <div class="flex items-center gap-2 mb-4 text-xs">
                    <span class="inline-flex items-center gap-1.5 rounded-full border border-[#d7ebde] bg-[#eef6f0] px-2.5 py-1 font-medium text-[#3f9e6a]">
                        <span class="inline-block w-1.5 h-1.5 rounded-full bg-[#3f9e6a]"></span>
                        {{ skills.filter(s => (s.status || '').toLowerCase() !== 'draft').length }} enabled
                    </span>
                    <span v-if="skills.filter(s => (s.status || '').toLowerCase() === 'draft').length" class="inline-flex items-center rounded-full border border-[#E7E5DD] bg-[#F4F1EA] px-2.5 py-1 font-medium text-[#6b6b6b]">
                        {{ skills.filter(s => (s.status || '').toLowerCase() === 'draft').length }} draft
                    </span>
                    <span class="ms-auto text-[#9a958c]">Drafts a personal skill from a solved completion.</span>
                </div>

                <!-- Empty state -->
                <div v-if="skills.length === 0" class="flex flex-col items-center justify-center py-20 text-center">
                    <span class="inline-flex w-11 h-11 mx-auto mb-3 items-center justify-center rounded-xl bg-[#F4F1EA] border border-[#E7E5DD] text-[#C2683F]">
                        <UIcon name="i-heroicons-sparkles" class="w-6 h-6" />
                    </span>
                    <h3 class="text-[15px] font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">No skills yet</h3>
                    <p class="mt-1 text-sm text-[#9a958c] max-w-md leading-relaxed">
                        Skills are authored from a solved chat using the "Save as skill" action on
                        a completion. Once authored, they appear here as personal drafts you can
                        review and promote to your organization.
                    </p>
                </div>

                <!-- Filtered-empty note (e.g. Global = 0) -->
                <div v-else-if="filteredSkills.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
                    <span class="inline-flex w-11 h-11 mx-auto mb-3 items-center justify-center rounded-xl bg-[#F4F1EA] border border-[#E7E5DD] text-[#C2683F]">
                        <UIcon name="i-heroicons-sparkles" class="w-6 h-6" />
                    </span>
                    <h3 class="text-[15px] font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">No {{ activeTab.toLowerCase() }} skills</h3>
                    <p class="mt-1 text-sm text-[#9a958c]">Nothing scoped to {{ activeTab }} yet.</p>
                </div>

                <!-- Skill card grid -->
                <div v-else class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                    <!-- Skill cards -->
                    <div
                        v-for="skill in filteredSkills"
                        :key="skill.id"
                        class="flex flex-col gap-3 rounded-2xl border border-[#E7E5DD] bg-white p-4 cursor-pointer transition hover:-translate-y-0.5 hover:shadow-md"
                        @click="openSkill(skill)"
                    >
                        <!-- Tile: scope + enabled -->
                        <div class="flex items-center justify-between gap-2 rounded-xl border border-[#E7E5DD] bg-[#F4F1EA] px-3 py-2">
                            <span class="inline-flex items-center rounded-full border border-[#E7E5DD] bg-white px-2 py-0.5 text-[11px] font-medium text-[#6b6b6b]">
                                {{ scopeLabel(skill.scope) }}
                            </span>
                            <span class="inline-flex items-center gap-1.5 rounded-full border border-[#d7ebde] bg-[#eef6f0] px-2 py-0.5 text-[11px] font-medium text-[#3f9e6a]">
                                <span class="inline-block w-1.5 h-1.5 rounded-full bg-[#3f9e6a]"></span>
                                Enabled
                            </span>
                        </div>

                        <!-- Name -->
                        <div class="flex items-center gap-2 text-[15px] font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">
                            <Icon name="heroicons:bolt" class="w-[17px] h-[17px] text-[#C2683F] shrink-0" />
                            {{ skill.name }}
                        </div>

                        <!-- Description -->
                        <p class="text-xs text-[#6b6b6b] leading-relaxed line-clamp-3">
                            {{ skill.description || '—' }}
                        </p>

                        <!-- Footer: status / origin / path -->
                        <div class="mt-auto pt-3 border-t border-[#E7E5DD] flex items-center gap-2">
                            <span
                                v-if="skill.status"
                                class="inline-flex items-center rounded-full border border-[#E7E5DD] bg-[#F4F1EA] px-2 py-0.5 text-[11px] font-medium text-[#6b6b6b]"
                            >{{ skill.status }}</span>
                            <span
                                v-if="(skill.origin || 'manual') === 'auto'"
                                class="inline-flex items-center gap-1 rounded-full border border-[#e7ddf3] bg-[#f3eefb] px-2 py-0.5 text-[11px] font-medium text-[#7c3aed]"
                            >
                                <Icon name="heroicons:sparkles" class="w-3 h-3 shrink-0" />
                                Auto-proposed
                            </span>
                            <span class="ms-auto text-[11px] text-[#9a958c]" style="font-family: ui-monospace, monospace">/{{ skill.name }}</span>
                        </div>
                    </div>

                    <!-- Ghost card — author a new skill -->
                    <button
                        type="button"
                        class="flex flex-col items-center justify-center gap-2 text-center rounded-2xl border border-dashed border-[#E7E5DD] bg-[#F4F1EA]/40 p-4 min-h-[180px] cursor-pointer transition hover:-translate-y-0.5 hover:shadow-md hover:bg-[#F4F1EA]"
                        :disabled="!completionId.trim() || authoring"
                        @click="authorFromCompletion"
                    >
                        <div class="flex items-center justify-center w-12 h-12 rounded-2xl border border-[#E7E5DD] bg-white">
                            <Icon name="heroicons:plus" class="w-6 h-6 text-[#C2683F]" />
                        </div>
                        <div class="text-[15px] font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Author skill</div>
                        <p class="max-w-[200px] text-xs text-[#6b6b6b] leading-relaxed">
                            Save a solved chat as a SKILL.md playbook, or draft one from a completion ID.
                        </p>
                    </button>
                </div>
            </template>

            <!-- Details modal -->
            <SkillDetailsModal
                v-model="showDetailsModal"
                :skill="selectedSkill"
                :all-skills="skills"
                @promoted="handleChanged"
                @deleted="handleChanged"
                @changed="handleChanged"
            />
        </div>
    </div>
</template>

<script setup lang="ts">
import SkillDetailsModal from '~/components/SkillDetailsModal.vue'

definePageMeta({
    auth: true,
    layout: 'default'
})

interface Skill {
    id: string
    name: string
    description?: string
    scope?: string
    status?: string
    origin?: 'auto' | 'manual'
    skill_md?: string
    valid_at?: string | null
    invalid_at?: string | null
    superseded_by?: string | null
}

const skills = ref<Skill[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const completionId = ref('')
const authoring = ref(false)
const authorError = ref<string | null>(null)

const showDetailsModal = ref(false)
const selectedSkill = ref<Skill | null>(null)

const scopeLabel = (scope?: string) => {
    const s = (scope || '').toLowerCase()
    if (s === 'org' || s === 'organization') return 'Organization'
    if (s === 'global') return 'Global'
    return 'Personal'
}

// Scope tab filter (All | Personal | Organization | Global)
const activeTab = ref<'All' | 'Personal' | 'Organization' | 'Global'>('All')
const filteredSkills = computed(() =>
    activeTab.value === 'All'
        ? skills.value
        : skills.value.filter(s => scopeLabel(s.scope) === activeTab.value)
)

const scopeBadgeClass = (scope?: string) => {
    const s = (scope || '').toLowerCase()
    if (s === 'org' || s === 'organization') return 'bg-[#F3E7DF] text-[#A8542F]'
    if (s === 'global') return 'bg-[#F4F1EA] text-[#C2683F]'
    return 'bg-[#F4F1EA] text-[#6b6b6b]'
}

const fetchSkills = async () => {
    loading.value = true
    error.value = null
    try {
        const { data, error: fetchErr } = await useMyFetch<Skill[]>('/api/skills', { method: 'GET' })
        if (fetchErr?.value) {
            throw fetchErr.value
        }
        skills.value = data.value || []
    } catch (e: any) {
        console.error('Failed to fetch skills:', e)
        error.value = 'Failed to load skills.'
    } finally {
        loading.value = false
    }
}

const openSkill = (skill: Skill) => {
    selectedSkill.value = skill
    showDetailsModal.value = true
}

const authorFromCompletion = async () => {
    const id = completionId.value.trim()
    if (!id) return
    authoring.value = true
    authorError.value = null
    try {
        const { error: fetchErr } = await useMyFetch(`/api/skills/from-completion/${id}`, { method: 'POST' })
        if (fetchErr?.value) {
            throw fetchErr.value
        }
        completionId.value = ''
        await fetchSkills()
    } catch (e: any) {
        console.error('Failed to author skill from completion:', e)
        authorError.value = 'Failed to author skill from that completion. Check the completion ID.'
    } finally {
        authoring.value = false
    }
}

const handleChanged = () => {
    fetchSkills()
}

onMounted(() => {
    fetchSkills()
})
</script>
