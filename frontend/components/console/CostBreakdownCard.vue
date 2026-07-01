<template>
    <div class="bg-white p-5 border border-[#E9E0D3] rounded-xl shadow-sm">
        <h3 class="text-sm font-semibold text-[#1f2328] mb-4">{{ title }}</h3>
        <div v-if="!rows.length" class="text-xs text-[#9a9184] py-4">—</div>
        <div v-else class="space-y-3">
            <div v-for="(row, idx) in rows" :key="idx">
                <div class="flex items-baseline justify-between text-xs mb-1">
                    <span class="text-[#1f2328] font-medium truncate pr-2">{{ row.label }}</span>
                    <span class="text-[#6b6b6b] whitespace-nowrap">
                        {{ money(row.cost) }}
                        <span class="text-[#C9BEAD] ms-1">{{ row.pct.toFixed(0) }}%</span>
                    </span>
                </div>
                <div class="h-2 w-full bg-[#F1ECE3] rounded-full overflow-hidden">
                    <div
                        class="h-full rounded-full bg-[#C2541E]"
                        :style="{ width: `${Math.max(2, row.pct)}%` }"
                    ></div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
interface BreakdownRow { label: string; cost: number; pct: number }

defineProps<{
    title: string
    rows: BreakdownRow[]
}>()

const money = (v: number) => `$${(Number(v) || 0).toFixed(2)}`
</script>
