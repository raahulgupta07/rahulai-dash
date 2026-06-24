<template>
    <div class="flex justify-center px-4 md:px-6 text-sm bg-[#FBFAF6] min-h-full">
        <div class="w-full max-w-7xl py-2 text-[#1f2328]">
            <!-- Header -->
            <div class="flex items-start justify-between gap-4 mb-5">
                <div>
                    <h1
                        class="text-2xl font-semibold text-[#1f2328] tracking-tight flex items-center"
                        style="font-family: ui-serif, Georgia, 'Times New Roman', serif"
                    >Skills</h1>
                    <p class="mt-1.5 text-[#6b6b6b] leading-relaxed max-w-2xl">
                        Data-gated <b>Domain Packs</b> (auto-bind to a studio's columns at Auto-train) and reusable
                        <b>SKILL.md playbooks</b>. <template v-if="packs.length"><span class="text-[#3f9e6a] font-medium">{{ packTotals.in_use || 0 }} in use</span> · {{ packTotals.library || 0 }} shipped + {{ packTotals.org || 0 }} org.</template>
                    </p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                    <!-- Search -->
                    <div class="flex items-center gap-1.5 rounded-xl border border-[#E7E5DD] bg-white px-2.5 py-1.5 focus-within:border-[#C2683F]">
                        <Icon name="heroicons:magnifying-glass" class="w-4 h-4 text-[#9a958c] shrink-0" />
                        <input
                            v-model="search"
                            type="text"
                            placeholder="Search skills…"
                            class="w-44 bg-transparent text-sm outline-none placeholder:text-[#9a958c]"
                        />
                        <button v-if="search" type="button" class="text-[#9a958c] hover:text-[#1f2328]" @click="search = ''">
                            <Icon name="heroicons:x-mark" class="w-3.5 h-3.5" />
                        </button>
                    </div>
                    <!-- Author a playbook from a completion -->
                    <div class="flex items-center gap-1.5 rounded-xl border border-[#E7E5DD] bg-white px-2.5 py-1.5 focus-within:border-[#C2683F]">
                        <Icon name="heroicons:bars-3-bottom-left" class="w-4 h-4 text-[#9a958c] shrink-0" />
                        <input
                            v-model="completionId"
                            type="text"
                            placeholder="Completion ID…"
                            class="w-32 bg-transparent text-sm outline-none placeholder:text-[#9a958c]"
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
                        New playbook
                    </button>
                </div>
            </div>

            <!-- Author error -->
            <div v-if="authorError" class="mb-4 rounded-xl border border-[#E7E5DD] bg-[#F3E7DF] p-3 text-xs text-[#A8542F]">
                {{ authorError }}
            </div>

            <!-- ===================== Rail + grid ===================== -->
            <div class="flex gap-6 items-start">
                <!-- LEFT RAIL -->
                <aside class="w-52 shrink-0 sticky top-2">
                    <p class="px-2 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-[#9a958c]">Categories</p>
                    <nav class="flex flex-col gap-0.5 mb-5">
                        <button
                            v-for="c in categoryRail"
                            :key="c.key"
                            type="button"
                            class="group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition"
                            :class="selectedCategory === c.key
                                ? 'bg-[#ECEAE1] text-[#1f2328] font-medium'
                                : 'text-[#6b6b6b] hover:bg-[#F4F1EA] hover:text-[#1f2328]'"
                            @click="selectedCategory = c.key"
                        >
                            <Icon
                                :name="categoryIcon(c.key)"
                                class="w-4 h-4 shrink-0"
                                :class="selectedCategory === c.key ? 'text-[#C2683F]' : 'text-[#9a958c] group-hover:text-[#6b6b6b]'"
                            />
                            <span class="truncate">{{ c.label }}</span>
                            <span v-if="c.active" class="w-1.5 h-1.5 rounded-full bg-[#3f9e6a] shrink-0" title="has active packs"></span>
                            <span
                                class="ms-auto rounded-full px-1.5 py-0.5 text-[11px]"
                                :class="selectedCategory === c.key ? 'bg-white text-[#6b6b6b]' : 'bg-[#ECEAE1] text-[#9a958c]'"
                            >{{ c.count }}</span>
                        </button>
                    </nav>

                    <!-- TIER filter (packs only) -->
                    <template v-if="selectedCategory !== 'Playbooks'">
                        <p class="px-2 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-[#9a958c]">Data readiness</p>
                        <div class="flex flex-col gap-1 px-2">
                            <label v-for="t in tierFilters" :key="t.key" class="flex items-center gap-2 text-[12px] text-[#6b6b6b] cursor-pointer select-none">
                                <input type="checkbox" v-model="t.on" class="accent-[#C2683F] w-3.5 h-3.5" />
                                <span>{{ t.label }}</span>
                            </label>
                        </div>
                    </template>
                </aside>

                <!-- MAIN -->
                <main class="flex-1 min-w-0">
                    <!-- loading / error (playbooks fetch) -->
                    <div v-if="loading && selectedCategory === 'Playbooks'" class="flex items-center justify-center py-20 text-[#9a958c]">
                        <Icon name="heroicons:arrow-path" class="w-5 h-5 animate-spin me-2" />
                        <span class="text-sm">Loading…</span>
                    </div>

                    <!-- ===== PLAYBOOKS view (SKILL.md) ===== -->
                    <template v-else-if="selectedCategory === 'Playbooks'">
                        <div v-if="error" class="rounded-2xl border border-[#E7E5DD] bg-[#F3E7DF] p-4 text-sm text-[#A8542F]">
                            {{ error }}
                            <button type="button" class="ms-2 rounded-lg px-2 py-0.5 text-xs font-medium text-[#C2683F] hover:bg-white/60" @click="fetchSkills">Retry</button>
                        </div>
                        <div v-else-if="filteredPlaybooks.length === 0" class="flex flex-col items-center justify-center py-20 text-center">
                            <span class="inline-flex w-11 h-11 mx-auto mb-3 items-center justify-center rounded-xl bg-[#F4F1EA] border border-[#E7E5DD] text-[#C2683F]">
                                <UIcon name="i-heroicons-document-text" class="w-6 h-6" />
                            </span>
                            <h3 class="text-[15px] font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">No playbooks yet</h3>
                            <p class="mt-1 text-sm text-[#9a958c] max-w-md leading-relaxed">
                                A playbook is authored from a solved chat ("Save as skill") or drafted from a completion ID above.
                                It appears here as a personal draft you can review and promote.
                            </p>
                        </div>
                        <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                            <div
                                v-for="skill in filteredPlaybooks"
                                :key="skill.id"
                                class="flex flex-col gap-3 rounded-2xl border border-[#E7E5DD] bg-white p-4 cursor-pointer transition hover:-translate-y-0.5 hover:shadow-md"
                                @click="openSkill(skill)"
                            >
                                <div class="flex items-center justify-between gap-2 rounded-xl border border-[#E7E5DD] bg-[#F4F1EA] px-3 py-2">
                                    <span class="inline-flex items-center rounded-full border border-[#E7E5DD] bg-white px-2 py-0.5 text-[11px] font-medium text-[#6b6b6b]">{{ scopeLabel(skill.scope) }}</span>
                                    <span class="inline-flex items-center gap-1.5 rounded-full border border-[#d7ebde] bg-[#eef6f0] px-2 py-0.5 text-[11px] font-medium text-[#3f9e6a]">
                                        <span class="inline-block w-1.5 h-1.5 rounded-full bg-[#3f9e6a]"></span>Enabled
                                    </span>
                                </div>
                                <div class="flex items-center gap-2 text-[15px] font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">
                                    <Icon name="heroicons:bolt" class="w-[17px] h-[17px] text-[#C2683F] shrink-0" />{{ skill.name }}
                                </div>
                                <p class="text-xs text-[#6b6b6b] leading-relaxed line-clamp-3">{{ skill.description || '—' }}</p>
                                <div class="mt-auto pt-3 border-t border-[#E7E5DD] flex items-center gap-2">
                                    <span v-if="skill.status" class="inline-flex items-center rounded-full border border-[#E7E5DD] bg-[#F4F1EA] px-2 py-0.5 text-[11px] font-medium text-[#6b6b6b]">{{ skill.status }}</span>
                                    <span v-if="(skill.origin || 'manual') === 'auto'" class="inline-flex items-center gap-1 rounded-full border border-[#e7ddf3] bg-[#f3eefb] px-2 py-0.5 text-[11px] font-medium text-[#7c3aed]">
                                        <Icon name="heroicons:sparkles" class="w-3 h-3 shrink-0" />Auto-proposed
                                    </span>
                                    <span class="ms-auto text-[11px] text-[#9a958c]" style="font-family: ui-monospace, monospace">/{{ skill.name }}</span>
                                </div>
                            </div>
                        </div>
                    </template>

                    <!-- ===== PACKS view ===== -->
                    <template v-else>
                        <div v-if="!packs.length" class="flex flex-col items-center justify-center py-20 text-center">
                            <span class="inline-flex w-11 h-11 mx-auto mb-3 items-center justify-center rounded-xl bg-[#F4F1EA] border border-[#E7E5DD] text-[#C2683F]">
                                <UIcon name="i-heroicons-puzzle-piece" class="w-6 h-6" />
                            </span>
                            <h3 class="text-[15px] font-semibold text-[#1f2328]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Domain Packs are off</h3>
                            <p class="mt-1 text-sm text-[#9a958c] max-w-md leading-relaxed">Enable the <b>Domain Packs</b> feature flag (Settings → Feature Flags) to see the pack library.</p>
                        </div>
                        <div v-else-if="visiblePackGroups.length === 0" class="py-16 text-center text-sm text-[#9a958c]">
                            No skills match <template v-if="search">“{{ search }}”</template><template v-else>this filter</template>.
                        </div>
                        <div v-else>
                            <div v-for="grp in visiblePackGroups" :key="grp.key" class="mb-6">
                                <div class="flex items-center gap-2 mb-2.5">
                                    <h2 class="text-[13px] font-semibold uppercase tracking-wide text-[#6b6b6b]">{{ grp.label }}</h2>
                                    <span class="text-[11px] text-[#bcb8ae]">{{ grp.note }}</span>
                                    <NuxtLink v-if="grp.key === categoryRail[0].key" to="/settings/pack-analytics" class="ms-auto text-xs font-medium text-[#C2683F] hover:underline">Pack analytics →</NuxtLink>
                                    <span v-else class="ms-auto text-[11px] text-[#9a958c]">{{ grp.items.length }}</span>
                                </div>
                                <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                                    <div
                                        v-for="p in grp.items"
                                        :key="p.pack_id"
                                        class="flex flex-col gap-2 rounded-2xl border border-[#E7E5DD] bg-white p-3.5"
                                    >
                                        <div class="flex items-start justify-between gap-2">
                                            <div class="flex items-center gap-1.5 min-w-0">
                                                <Icon name="heroicons:puzzle-piece" class="w-4 h-4 text-[#C2683F] shrink-0" />
                                                <span class="text-[13px] font-semibold text-[#1f2328] leading-snug">{{ p.name }}</span>
                                            </div>
                                            <span
                                                v-if="p.active_studios > 0"
                                                class="shrink-0 inline-flex items-center gap-1 rounded-full border border-[#d7ebde] bg-[#eef6f0] px-2 py-0.5 text-[11px] font-medium text-[#3f9e6a]"
                                            >
                                                <span class="inline-block w-1.5 h-1.5 rounded-full bg-[#3f9e6a]"></span>{{ p.active_studios }} active
                                            </span>
                                            <span v-else class="shrink-0 inline-flex items-center rounded-full border border-[#E7E5DD] bg-[#F4F1EA] px-2 py-0.5 text-[11px] font-medium text-[#9a958c]">dormant</span>
                                        </div>
                                        <div class="flex items-center gap-1.5">
                                            <span class="text-[11px] text-[#9a958c] font-mono">{{ p.domain }}</span>
                                            <span class="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium" :class="tierBadgeClass(p.tier)">{{ tierShort(p.tier) }}</span>
                                        </div>
                                        <div v-if="p.inputs && p.inputs.length" class="flex flex-wrap gap-1">
                                            <span
                                                v-for="inp in p.inputs"
                                                :key="inp.key"
                                                class="inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium"
                                                :class="inp.optional ? 'border-[#E7E5DD] bg-[#F4F1EA] text-[#9a958c]' : 'border-[#e6dcd2] bg-[#faf3ee] text-[#A8542F]'"
                                                :title="(inp.role || '') + (inp.optional ? ' (optional)' : ' (required)') + (inp.desc ? ' — ' + inp.desc : '')"
                                            >{{ inp.key }}<span v-if="inp.optional" class="opacity-60">?</span></span>
                                        </div>
                                        <p v-if="p.triggers && p.triggers.length" class="text-[11px] text-[#6b6b6b] line-clamp-1">
                                            <span class="text-[#bcb8ae]">fires on:</span> {{ p.triggers.slice(0, 4).join(' · ') }}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </template>
                </main>
            </div>

            <!-- Details modal (playbooks) -->
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

definePageMeta({ auth: true, layout: 'default' })

// ---- SKILL.md playbooks ----------------------------------------------------
interface Skill {
    id: string
    name: string
    description?: string
    scope?: string
    status?: string
    origin?: 'auto' | 'manual'
    skill_md?: string
}
const skills = ref<Skill[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const completionId = ref('')
const authoring = ref(false)
const authorError = ref<string | null>(null)

const showDetailsModal = ref(false)
const selectedSkill = ref<Skill | null>(null)

const search = ref('')
const selectedCategory = ref('All')

// Rail icons per category (matches the studio sidebar look).
const CATEGORY_ICON: Record<string, string> = {
    All: 'heroicons:squares-2x2',
    Performance: 'heroicons:chart-bar',
    Valuation: 'heroicons:scale',
    'Fund / PE': 'heroicons:briefcase',
    Accounting: 'heroicons:calculator',
    Output: 'heroicons:presentation-chart-line',
    Analysis: 'heroicons:magnifying-glass-circle',
    'Data Quality': 'heroicons:shield-check',
    Storytelling: 'heroicons:sparkles',
    Stakeholder: 'heroicons:users',
    Documentation: 'heroicons:book-open',
    Workflow: 'heroicons:arrow-path-rounded-square',
    Org: 'heroicons:building-office-2',
    Playbooks: 'heroicons:bolt',
}
const categoryIcon = (key: string) => CATEGORY_ICON[key] || 'heroicons:puzzle-piece'

const scopeLabel = (scope?: string) => {
    const s = (scope || '').toLowerCase()
    if (s === 'org' || s === 'organization') return 'Organization'
    if (s === 'global') return 'Global'
    return 'Personal'
}

// ---- Domain Packs catalog --------------------------------------------------
interface PackInput { key: string; role?: string; optional?: boolean; desc?: string }
interface Pack {
    pack_id: string; name: string; domain: string; tier: string; category: string; source: string
    triggers?: string[]; inputs?: PackInput[]; output?: string
    bound_studios: number; active_studios: number; status?: string
}
const packs = ref<Pack[]>([])
const packTotals = ref<Record<string, number>>({})

// Fixed category order for the rail (only those present are shown).
const CATEGORY_ORDER = ['Performance', 'Valuation', 'Fund / PE', 'Accounting', 'Output', 'Analysis', 'Data Quality', 'Storytelling', 'Stakeholder', 'Documentation', 'Workflow', 'Finance', 'General', 'Org']
const TIER_NOTE: Record<string, string> = {
    A: 'binds to your columns', C: 'output / deliverables', B: 'needs a market-data feed', Org: 'promoted from a studio',
}

// Tier filter (packs only)
const tierFilters = reactive([
    { key: 'A', label: 'Runs on your data', on: true },
    { key: 'C', label: 'Output / deliverables', on: true },
    { key: 'B', label: 'Needs a feed', on: true },
    { key: 'Org', label: 'Org packs', on: true },
])
const activeTiers = computed(() => new Set(tierFilters.filter(t => t.on).map(t => t.key)))

const tierShort = (t: string) => ({ A: 'A', B: 'B', C: 'C', Org: 'Org' } as any)[t] || t
const tierBadgeClass = (t: string) => {
    if (t === 'A') return 'border border-[#d7ebde] bg-[#eef6f0] text-[#3f9e6a]'
    if (t === 'B') return 'border border-[#E7E5DD] bg-[#F4F1EA] text-[#9a958c]'
    if (t === 'C') return 'border border-[#e7ddf3] bg-[#f3eefb] text-[#7c3aed]'
    return 'border border-[#e6dcd2] bg-[#faf3ee] text-[#A8542F]'
}

const matchesSearch = (p: Pack) => {
    const q = search.value.trim().toLowerCase()
    if (!q) return true
    if (p.name.toLowerCase().includes(q)) return true
    if ((p.domain || '').toLowerCase().includes(q)) return true
    if ((p.triggers || []).some(t => t.toLowerCase().includes(q))) return true
    if ((p.inputs || []).some(i => i.key.toLowerCase().includes(q))) return true
    return false
}

// Packs after search + tier filter (category applied per-group).
const searchedPacks = computed(() => packs.value.filter(p => matchesSearch(p) && activeTiers.value.has(p.tier)))

// Left-rail categories: All + each present category (in order) + Playbooks.
const categoryRail = computed(() => {
    const present: Record<string, { count: number; active: number }> = {}
    for (const p of packs.value) {
        const c = p.category || 'General'
        present[c] = present[c] || { count: 0, active: 0 }
        present[c].count++
        if (p.active_studios > 0) present[c].active++
    }
    const rail: { key: string; label: string; count: number; active: boolean }[] = [
        { key: 'All', label: 'All', count: packs.value.length, active: (packTotals.value.in_use || 0) > 0 },
    ]
    for (const cat of CATEGORY_ORDER) {
        if (present[cat]) rail.push({ key: cat, label: cat, count: present[cat].count, active: present[cat].active > 0 })
    }
    rail.push({ key: 'Playbooks', label: 'Playbooks', count: skills.value.length, active: false })
    return rail
})

// Grouped packs for the main grid. 'All' → grouped by category; a specific
// category → a single group.
const visiblePackGroups = computed(() => {
    const cat = selectedCategory.value
    const groups: { key: string; label: string; note: string; items: Pack[] }[] = []
    const cats = cat === 'All' ? CATEGORY_ORDER : [cat]
    for (const c of cats) {
        const items = searchedPacks.value.filter(p => (p.category || 'General') === c)
        if (items.length) {
            const tierNote = items.length ? (TIER_NOTE[items[0].tier] || '') : ''
            groups.push({ key: c, label: c, note: cat === 'All' ? tierNote : '', items })
        }
    }
    return groups
})

// Playbooks after search.
const filteredPlaybooks = computed(() => {
    const q = search.value.trim().toLowerCase()
    if (!q) return skills.value
    return skills.value.filter(s => (s.name || '').toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q))
})

const fetchSkills = async () => {
    loading.value = true
    error.value = null
    try {
        const { data, error: fetchErr } = await useMyFetch<Skill[]>('/api/skills', { method: 'GET' })
        if (fetchErr?.value) throw fetchErr.value
        skills.value = data.value || []
    } catch (e: any) {
        console.error('Failed to fetch skills:', e)
        error.value = 'Failed to load playbooks.'
    } finally {
        loading.value = false
    }
}

const fetchPacks = async () => {
    try {
        const { data } = await useMyFetch<any>('/api/packs/library', { method: 'GET' })
        const d = data.value
        if (d && d.ok && Array.isArray(d.packs)) {
            packs.value = d.packs
            packTotals.value = d.totals || {}
        }
    } catch { /* feature off / error → leave empty */ }
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
        if (fetchErr?.value) throw fetchErr.value
        completionId.value = ''
        selectedCategory.value = 'Playbooks'
        await fetchSkills()
    } catch (e: any) {
        console.error('Failed to author skill from completion:', e)
        authorError.value = 'Failed to author a playbook from that completion. Check the completion ID.'
    } finally {
        authoring.value = false
    }
}

const handleChanged = () => fetchSkills()

onMounted(() => {
    fetchSkills()
    fetchPacks()
})
</script>
