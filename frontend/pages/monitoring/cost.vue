<template>
    <div class="mt-6">
        <!-- Header + date range toggle -->
        <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
            <div>
                <h2 class="text-lg font-semibold text-[#1f2328]" style="font-family: 'Spectral', ui-serif, Georgia, serif">
                    {{ $t('monitoring.cost.title') }}
                </h2>
                <p class="text-sm text-[#6b6b6b]">{{ $t('monitoring.cost.subtitle') }}</p>
            </div>
            <div class="inline-flex rounded-lg border border-[#E9E0D3] bg-white p-0.5">
                <button
                    v-for="opt in rangeOptions"
                    :key="opt.value"
                    @click="setRange(opt.value)"
                    :class="[
                        selectedRange === opt.value
                            ? 'bg-[#C2541E] text-white'
                            : 'text-[#6b6b6b] hover:text-[#1f2328]',
                        'px-3 py-1 text-xs font-medium rounded-md transition-colors'
                    ]"
                >
                    {{ opt.label }}
                </button>
            </div>
        </div>

        <!-- Loading skeleton -->
        <div v-if="isLoading" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-5 gap-4">
                <div v-for="i in 5" :key="i" class="bg-white p-5 border border-[#E9E0D3] rounded-xl">
                    <div class="h-6 w-24 bg-[#F1ECE3] rounded animate-pulse"></div>
                    <div class="h-3 w-16 bg-[#F1ECE3] rounded animate-pulse mt-3"></div>
                </div>
            </div>
            <div class="bg-white p-5 border border-[#E9E0D3] rounded-xl">
                <div class="h-40 w-full bg-[#F1ECE3] rounded animate-pulse"></div>
            </div>
        </div>

        <!-- Empty state -->
        <div v-else-if="isEmpty" class="text-center py-16">
            <UIcon name="i-heroicons-banknotes" class="mx-auto h-12 w-12 text-[#C9BEAD]" />
            <h3 class="mt-2 text-sm font-medium text-[#1f2328]">{{ $t('monitoring.cost.empty') }}</h3>
        </div>

        <!-- Content -->
        <div v-else class="space-y-8">
            <!-- KPI Row -->
            <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div class="bg-white p-5 border border-[#E9E0D3] rounded-xl shadow-sm">
                    <div class="text-2xl font-bold text-[#1f2328]">{{ formatMoney(kpis.total_cost) }}</div>
                    <div class="text-xs font-medium text-[#6b6b6b] mt-1">{{ $t('monitoring.cost.totalSpend') }}</div>
                </div>
                <div class="bg-white p-5 border border-[#E9E0D3] rounded-xl shadow-sm">
                    <div class="text-2xl font-bold text-[#1f2328]">
                        {{ formatTokens(kpis.prompt_tokens) }} <span class="text-[#C9BEAD]">/</span> {{ formatTokens(kpis.completion_tokens) }}
                    </div>
                    <div class="text-xs font-medium text-[#6b6b6b] mt-1">{{ $t('monitoring.cost.tokens') }}</div>
                </div>
                <div class="bg-white p-5 border border-[#E9E0D3] rounded-xl shadow-sm">
                    <div class="text-2xl font-bold text-[#1f2328]">{{ formatMoney(kpis.avg_cost_per_call) }}</div>
                    <div class="text-xs font-medium text-[#6b6b6b] mt-1">{{ $t('monitoring.cost.avgPerRun') }}</div>
                </div>
                <div class="bg-white p-5 border border-[#E9E0D3] rounded-xl shadow-sm">
                    <div class="text-2xl font-bold text-[#1f2328]">{{ formatTokens(kpis.cache_read_tokens) }}</div>
                    <div class="text-xs font-medium text-[#6b6b6b] mt-1">{{ $t('monitoring.cost.cacheReads') }}</div>
                </div>
                <div class="bg-white p-5 border border-[#E9E0D3] rounded-xl shadow-sm">
                    <div class="text-2xl font-bold text-[#1f2328]">{{ (kpis.total_calls || 0).toLocaleString() }}</div>
                    <div class="text-xs font-medium text-[#6b6b6b] mt-1">{{ $t('monitoring.cost.totalCalls') }}</div>
                </div>
            </div>

            <!-- Daily spend chart (CSS bars) -->
            <div v-if="daily.length" class="bg-white p-5 border border-[#E9E0D3] rounded-xl shadow-sm">
                <h3 class="text-sm font-semibold text-[#1f2328] mb-4">{{ $t('monitoring.cost.dailySpend') }}</h3>
                <div class="flex items-end gap-1 h-40">
                    <div
                        v-for="(d, idx) in daily"
                        :key="idx"
                        class="flex-1 min-w-0 flex flex-col justify-end group relative cursor-default"
                        :title="`${formatDate(d.date)} · ${formatMoney(d.cost)}`"
                    >
                        <div
                            class="w-full rounded-t bg-[#C2541E] hover:bg-[#A8330F] transition-colors"
                            :style="{ height: barHeight(d.cost) }"
                        ></div>
                        <div class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-10 hidden group-hover:block whitespace-nowrap bg-[#1e1e1e] text-white text-[11px] px-2 py-1 rounded shadow">
                            {{ formatDate(d.date) }} · {{ formatMoney(d.cost) }}
                        </div>
                    </div>
                </div>
            </div>

            <!-- Breakdown cards -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <CostBreakdownCard :title="$t('monitoring.cost.byModel')" :rows="modelRows" />
                <CostBreakdownCard :title="$t('monitoring.cost.byProvider')" :rows="providerRows" />
                <CostBreakdownCard :title="$t('monitoring.cost.byScope')" :rows="scopeRows" />
                <CostBreakdownCard v-if="userRows.length" :title="$t('monitoring.cost.byUser')" :rows="userRows" />
                <CostBreakdownCard v-if="agentRows.length" :title="$t('monitoring.cost.byAgent')" :rows="agentRows" />
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import CostBreakdownCard from '~/components/console/CostBreakdownCard.vue'

const { t } = useI18n()

definePageMeta({
    auth: true,
    layout: 'monitoring',
    resourcePermissionAny: { permission: 'manage', resourceType: 'data_source' }
})

interface DateRange { start: string; end: string }
interface BreakdownRow { label: string; cost: number; pct: number }

const isLoading = ref(false)
const data = ref<any | null>(null)

// Date range toggle 7d / 30d / 90d (default 30)
const rangeOptions = [
    { label: t('monitoring.overview.last7d'), value: 7 },
    { label: t('monitoring.overview.last30d'), value: 30 },
    { label: t('monitoring.overview.last90d'), value: 90 }
]
const selectedRange = ref(30)
const dateRange = ref<DateRange>({ start: '', end: '' })

const kpis = computed(() => data.value?.kpis || {})
const daily = computed<any[]>(() => data.value?.daily || [])

const isEmpty = computed(() => {
    const k = kpis.value
    return !data.value || (!k.total_cost && !k.total_calls && !daily.value.length)
})

// --- Formatters ---
const formatMoney = (v: number | null | undefined) => `$${(Number(v) || 0).toFixed(2)}`

const formatTokens = (v: number | null | undefined) => {
    const n = Number(v) || 0
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
    return n.toLocaleString()
}

const formatDate = (dateString: string) => {
    if (!dateString) return ''
    const d = new Date(dateString)
    return `${d.getMonth() + 1}/${d.getDate()}`
}

// --- Daily bar heights ---
const maxDaily = computed(() => Math.max(1, ...daily.value.map(d => Number(d.cost) || 0)))
const barHeight = (cost: number) => {
    const pct = (Number(cost) || 0) / maxDaily.value
    // floor at 2% so a nonzero-but-tiny bar is still visible
    return `${Math.max(cost > 0 ? 2 : 0, pct * 100)}%`
}

// --- Breakdown row builder (bar + $ + %) ---
const toRows = (arr: any[] | undefined, labelKey: string): BreakdownRow[] => {
    if (!arr?.length) return []
    const total = arr.reduce((s, r) => s + (Number(r.cost) || 0), 0) || 1
    return arr
        .map(r => ({
            label: String(r[labelKey] ?? r.label ?? '—'),
            cost: Number(r.cost) || 0,
            pct: ((Number(r.cost) || 0) / total) * 100
        }))
        .sort((a, b) => b.cost - a.cost)
}

const modelRows = computed(() => toRows(data.value?.by_model, 'model_name'))
const providerRows = computed(() => toRows(data.value?.by_provider, 'provider_type'))
const scopeRows = computed(() => toRows(data.value?.by_scope, 'scope'))
const userRows = computed(() => toRows(data.value?.by_user, 'label'))
const agentRows = computed(() => toRows(data.value?.by_agent, 'label'))

// --- Date range handling ---
const applyRange = (days: number) => {
    const end = new Date()
    const start = new Date(); start.setDate(start.getDate() - days)
    dateRange.value = {
        start: start.toISOString().split('T')[0],
        end: end.toISOString().split('T')[0]
    }
}

const setRange = (days: number) => {
    selectedRange.value = days
    applyRange(days)
    fetchCost()
}

const fetchCost = async () => {
    isLoading.value = true
    try {
        const params = new URLSearchParams()
        if (dateRange.value.start) params.append('start_date', new Date(dateRange.value.start).toISOString())
        if (dateRange.value.end) params.append('end_date', new Date(dateRange.value.end).toISOString())

        const res = await useMyFetch<any>(`/console/llm-cost?${params}`)
        if (res.error.value) {
            console.error('Failed to fetch LLM cost:', res.error.value)
            data.value = null
        } else {
            data.value = res.data.value || null
        }
    } catch (error) {
        console.error('Failed to fetch LLM cost:', error)
        data.value = null
    } finally {
        isLoading.value = false
    }
}

onMounted(() => {
    applyRange(selectedRange.value)
    fetchCost()
})
</script>
