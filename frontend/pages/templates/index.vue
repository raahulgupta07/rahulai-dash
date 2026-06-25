<template>
  <div class="flex justify-center px-4 md:px-6 text-sm bg-[#FBFAF6] min-h-full">
    <div class="w-full max-w-7xl py-2">
      <!-- Header -->
      <div class="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1
            class="text-2xl font-semibold tracking-tight text-[#1f2328]"
            style="font-family: ui-serif, Georgia, 'Times New Roman', serif"
          >Templates</h1>
          <p class="mt-2 text-[#6b6b6b] leading-relaxed max-w-2xl">
            Reusable agent know-how — rules, metric formulas and example patterns. Bind one to
            your own columns and get your own agent. Your data never leaves.
          </p>
        </div>
        <NuxtLink
          to="/studios"
          class="flex-none inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border border-dashed border-[#E7E5DD] text-[#C2683F] hover:border-[#C2683F] hover:bg-[#F3E7DF] transition-colors cursor-pointer"
        >
          <UIcon name="i-heroicons-plus" class="w-4 h-4" />
          Publish
        </NuxtLink>
      </div>

      <!-- Controls: scope toggle + search -->
      <div class="flex flex-wrap items-center justify-between gap-3 mb-5">
        <!-- Scope toggle -->
        <div class="inline-flex items-center gap-1 bg-white border border-[#E7E5DD] rounded-lg p-1">
          <button
            v-for="opt in scopes"
            :key="opt.value"
            type="button"
            class="px-3 py-1.5 text-[13px] font-medium rounded-md transition-colors cursor-pointer"
            :class="scope === opt.value
              ? 'bg-[#C2683F] text-white'
              : 'text-[#6b6b6b] hover:bg-[#F4F1EA]'"
            @click="setScope(opt.value)"
          >{{ opt.label }}</button>
        </div>

        <!-- Search -->
        <div class="relative w-full sm:w-72">
          <UIcon
            name="i-heroicons-magnifying-glass"
            class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9a958c]"
          />
          <input
            v-model="q"
            type="text"
            placeholder="Search templates…"
            class="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-[#E7E5DD] bg-white text-[#1f2328] placeholder:text-[#9a958c] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C2683F] transition-colors"
            @input="onSearch"
          />
        </div>
      </div>

      <!-- Loading skeletons -->
      <div v-if="loading" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        <div
          v-for="n in 6"
          :key="n"
          class="animate-pulse rounded-2xl border border-[#E7E5DD] bg-white p-4"
        >
          <div class="h-11 w-11 bg-[#F4F1EA] rounded-xl mb-3" />
          <div class="h-3 w-1/2 bg-[#F4F1EA] rounded mb-3" />
          <div class="h-16 bg-[#F4F1EA] rounded" />
        </div>
      </div>

      <!-- Grid -->
      <div
        v-else-if="templates.length"
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
      >
        <div
          v-for="t in templates"
          :key="t.id"
          class="flex flex-col rounded-2xl border border-[#E7E5DD] bg-white p-4 hover:shadow-md hover:-translate-y-0.5 transition-all cursor-pointer"
          @click="openDetail(t.id)"
        >
          <!-- Icon tile + version -->
          <div class="flex items-start justify-between gap-2 mb-3">
            <div class="w-11 h-11 rounded-xl bg-[#F3E7DF] border border-[#E8C9B5] text-[#A8542F] flex items-center justify-center flex-none">
              <UIcon name="i-heroicons-square-3-stack-3d" class="w-6 h-6" />
            </div>
            <span
              v-if="t.version"
              class="font-mono text-[11px] text-[#9a958c] bg-[#F4F1EA] border border-[#E7E5DD] rounded-md px-1.5 py-0.5"
            >v{{ t.version }}</span>
          </div>

          <!-- Name + description -->
          <h3
            class="text-sm font-medium text-[#1f2328] mb-1"
            style="font-family: ui-serif, Georgia, serif"
          >{{ t.name }}</h3>
          <p class="text-[13px] text-[#6b6b6b] leading-snug line-clamp-2 mb-3 min-h-[34px]">
            {{ t.description || 'No description.' }}
          </p>

          <!-- Domain tags -->
          <div v-if="t.domain_tags && t.domain_tags.length" class="flex flex-wrap gap-1.5 mb-3">
            <span
              v-for="tag in t.domain_tags.slice(0, 4)"
              :key="tag"
              class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-[#F4F1EA] text-[#6b6b6b] border border-[#E7E5DD]"
            >{{ tag }}</span>
          </div>

          <!-- Footer: author + uses + CTA -->
          <div class="mt-auto pt-3 border-t border-[#E7E5DD] flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-xs text-[#9a958c] truncate">{{ t.author || 'Unknown' }}</span>
              <span class="text-[#cfcabf]">·</span>
              <span class="text-xs text-[#9a958c] inline-flex items-center gap-0.5 flex-none">
                <UIcon name="i-heroicons-star" class="w-3.5 h-3.5" />{{ t.uses ?? 0 }}
              </span>
            </div>
            <button
              type="button"
              class="flex-none inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium rounded-lg bg-[#C2683F] text-white hover:bg-[#A8542F] transition-colors cursor-pointer"
              @click.stop="openDetail(t.id)"
            >Use template</button>
          </div>
        </div>
      </div>

      <!-- Empty -->
      <div
        v-else
        class="text-center py-14 px-6 bg-white border border-[#E7E5DD] rounded-2xl"
      >
        <div class="w-11 h-11 rounded-xl bg-[#F4F1EA] border border-[#E7E5DD] mx-auto flex items-center justify-center mb-3">
          <UIcon name="i-heroicons-square-3-stack-3d" class="w-6 h-6 text-[#9a958c]" />
        </div>
        <p class="text-sm font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, serif">
          No templates {{ q ? 'match your search' : 'yet' }}
        </p>
        <p class="text-xs text-[#9a958c] mt-1">
          Export an agent's know-how from a Studio to share it here.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useMyFetch } from '~/composables/useMyFetch'

const scopes = [
  { value: 'org', label: 'Org' },
  { value: 'global', label: 'Global' },
  { value: 'all', label: 'All' },
]

const scope = ref<string>('all')
const q = ref<string>('')
const templates = ref<any[]>([])
const loading = ref(true)

let searchTimer: any = null
function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadTemplates, 300)
}

function setScope(v: string) {
  if (scope.value === v) return
  scope.value = v
  loadTemplates()
}

function openDetail(id: string) {
  navigateTo(`/templates/${id}`)
}

async function loadTemplates() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('scope', scope.value)
    if (q.value.trim()) params.set('q', q.value.trim())
    const { data, error } = await useMyFetch<any>(`/templates?${params.toString()}`, { method: 'GET' })
    if (error.value) throw error.value
    const d = data.value || {}
    templates.value = Array.isArray(d.templates) ? d.templates : []
  } catch {
    templates.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadTemplates)
</script>
