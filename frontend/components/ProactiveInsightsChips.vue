<template>
  <!-- Proactive Insights chips — rendered when step.data._insights is present.
       Read-only: chips are informational only, no click handler.
       Mirrors the follow-up chip style (rounded-full border bg-gray-50) with
       severity-colour accents so the user can visually triage at a glance.
  -->
  <div v-if="insights.length > 0" class="mt-2">
    <div class="text-[11px] text-gray-400 mb-1.5 flex items-center gap-1">
      <Icon name="heroicons-light-bulb" class="w-3 h-3 text-amber-400" />
      Insights
    </div>
    <div class="flex flex-wrap gap-1.5">
      <span
        v-for="(insight, idx) in insights"
        :key="idx"
        :title="insight.message"
        class="px-2.5 py-1 text-[11px] rounded-full border flex items-center gap-1 max-w-[340px] truncate cursor-default select-none"
        :class="chipClass(insight.severity)"
      >
        <Icon :name="kindIcon(insight.kind)" class="w-3 h-3 flex-none opacity-70" />
        <span class="truncate">{{ insight.message }}</span>
      </span>
    </div>
  </div>
</template>

<script lang="ts" setup>
interface Insight {
  kind: 'outlier' | 'spike' | 'trend' | string
  column: string
  message: string
  severity: 'high' | 'medium' | 'low' | string
}

const props = defineProps<{
  /** The step.data object from the completion widget step. */
  stepData?: Record<string, any> | null
}>()

const insights = computed<Insight[]>(() => {
  const raw = props.stepData?.['_insights']
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (r) =>
      r &&
      typeof r.message === 'string' &&
      typeof r.severity === 'string'
  )
})

function chipClass(severity: string): string {
  if (severity === 'high') {
    return 'border-red-200 bg-red-50 text-red-700'
  }
  if (severity === 'medium') {
    return 'border-amber-200 bg-amber-50 text-amber-700'
  }
  return 'border-gray-200 bg-gray-50 text-gray-600'
}

function kindIcon(kind: string): string {
  if (kind === 'outlier') return 'heroicons-exclamation-triangle'
  if (kind === 'spike') return 'heroicons-arrow-trending-up'
  return 'heroicons-information-circle'
}
</script>
