<template>
  <div>
    <!-- flag off (404) → fail-soft notice -->
    <div v-if="disabled" class="flex flex-col items-center justify-center py-16 text-center">
      <span class="inline-flex w-11 h-11 mx-auto mb-3 items-center justify-center rounded-xl bg-[#FBF4EF] border border-[#E8C9B5] text-[#C2683F]">
        <UIcon name="i-heroicons-lock-closed" class="w-6 h-6" />
      </span>
      <h3 class="text-[15px] font-semibold text-[#2B2622]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Folder Sync isn't enabled</h3>
      <p class="text-[12px] text-[#8A7E76] mt-1 max-w-md">Ask an admin to enable the <code>HYBRID_FOLDER_SYNC</code> feature flag in Settings → Feature Flags.</p>
    </div>

    <template v-else>
      <!-- header / explainer -->
      <div class="flex items-start justify-between gap-4 mb-5">
        <p class="text-[13px] text-[#8A7E76] leading-relaxed max-w-2xl">
          Folder Sync runs a tiny desktop helper that watches a local folder and auto-ingests new and
          changed files into one of your agents — like Claude Code. Generate a sync key, install the
          desktop app, and point it at a folder.
        </p>
        <button type="button"
                class="shrink-0 inline-flex items-center gap-1.5 text-[12px] font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3.5 py-2 transition-colors"
                @click="showModal = true">
          <UIcon name="i-heroicons-key" class="w-3.5 h-3.5" /> Generate sync key
        </button>
      </div>

      <!-- connected machines -->
      <div class="flex items-center gap-2 mb-2">
        <h3 class="text-sm font-semibold text-[#2B2622]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Connected machines</h3>
        <span v-if="machines.length" class="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-[#F4E5DA] text-[#A8542F]">{{ machines.length }}</span>
        <button type="button" class="ms-auto inline-flex items-center gap-1 text-[11px] font-medium text-[#8A7E76] hover:text-[#2B2622]" :disabled="loading" @click="loadStatus">
          <Spinner v-if="loading" class="h-3 w-3" /><UIcon v-else name="i-heroicons-arrow-path" class="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      <!-- loading -->
      <div v-if="loading && !loaded" class="flex items-center justify-center py-10 text-[#8A7E76]">
        <Spinner class="h-4 w-4" /><span class="ms-2 text-xs">Loading…</span>
      </div>

      <!-- empty -->
      <div v-else-if="!machines.length" class="py-10 text-center border border-dashed border-[#E8C9B5] rounded-xl bg-[#FBF4EF]">
        <UIcon name="i-heroicons-computer-desktop" class="w-7 h-7 mx-auto text-[#C2683F] mb-1.5" />
        <p class="text-[12px] text-[#2B2622] font-medium">No machines connected yet.</p>
        <p class="text-[11.5px] text-[#8A7E76] mt-0.5">Generate a key and set up the desktop app.</p>
      </div>

      <!-- machines list -->
      <div v-else class="space-y-3">
        <div v-for="(m, mi) in machines" :key="mi" class="rounded-xl border border-[#E8C9B5] bg-white overflow-hidden">
          <div class="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-[#F4E5DA] bg-[#FBF4EF]">
            <div class="flex items-center gap-2 min-w-0">
              <UIcon name="i-heroicons-computer-desktop" class="w-4 h-4 text-[#C2683F] shrink-0" />
              <span class="text-[13px] font-semibold text-[#2B2622] truncate">{{ m.machine_label || 'Unnamed machine' }}</span>
            </div>
            <div class="flex items-center gap-3 text-[11px] text-[#8A7E76] shrink-0">
              <span>{{ Number(m.files || 0) }} file{{ Number(m.files || 0) === 1 ? '' : 's' }}</span>
              <span v-if="m.last_sync_at">synced {{ timeAgo(m.last_sync_at) }} ago</span>
            </div>
          </div>

          <!-- folder → agent mappings -->
          <ul v-if="(m.paths || []).length" class="divide-y divide-[#F4E5DA]">
            <li v-for="(p, pi) in m.paths" :key="pi" class="flex items-center gap-2 px-4 py-2 min-w-0">
              <UIcon name="i-heroicons-folder" class="w-3.5 h-3.5 text-[#C2683F] shrink-0" />
              <code class="text-[11px] font-mono text-[#2B2622] truncate">{{ p.source_path }}</code>
              <span v-if="p.file_name" class="text-[10.5px] text-[#8A7E76] truncate">/ {{ p.file_name }}</span>
              <UIcon name="i-heroicons-arrow-right" class="w-3 h-3 text-[#8A7E76] shrink-0" />
              <span class="text-[11px] text-[#2B2622] truncate">
                <template v-if="p.studio_id">agent <code class="font-mono text-[10.5px]">{{ shortId(p.studio_id) }}</code></template>
                <template v-else-if="p.data_source_id">source <code class="font-mono text-[10.5px]">{{ shortId(p.data_source_id) }}</code></template>
                <template v-else>unassigned</template>
              </span>
              <span :class="['ms-auto shrink-0 text-[9.5px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded', statusClass(p.status)]">{{ p.status || '—' }}</span>
            </li>
          </ul>
          <p v-else class="px-4 py-2.5 text-[11px] text-[#8A7E76]">No folders mapped on this machine yet.</p>
        </div>
      </div>
    </template>

    <FolderSyncSetupModal v-model:open="showModal" />
  </div>
</template>

<script setup lang="ts">
// Settings → Folder Sync panel. Lists connected machines + folder→agent mappings
// from GET /sync/status. Generate-key action reuses FolderSyncSetupModal. Fail-soft on 404.
import Spinner from '~/components/Spinner.vue'
import FolderSyncSetupModal from '~/components/sync/FolderSyncSetupModal.vue'

const machines = ref<any[]>([])
const loading = ref(false)
const loaded = ref(false)
const disabled = ref(false)
const showModal = ref(false)

function timeAgo(date: string) {
  const secs = Math.floor((Date.now() - new Date(date).getTime()) / 1000)
  if (secs < 0 || isNaN(secs)) return 'just now'
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`
  return `${Math.floor(secs / 86400)}d`
}
function shortId(id: any) { const s = String(id || ''); return s.length > 10 ? s.slice(0, 8) + '…' : s }
function statusClass(s?: string) {
  if (s === 'new' || s === 'updated') return 'bg-[#E7F1EB] text-[#3F8C5E]'
  if (s === 'error') return 'bg-red-100 text-red-600'
  return 'bg-[#F4E5DA] text-[#8A7E76]'   // skipped / unknown → muted
}

async function loadStatus() {
  loading.value = true
  try {
    const { data, error } = await useMyFetch<any>('/sync/status', { method: 'GET' })
    if (error?.value) throw error.value
    machines.value = (data.value as any)?.machines || []
    disabled.value = false
  } catch (e: any) {
    const status = e?.statusCode || e?.response?.status
    if (status === 404) disabled.value = true
    machines.value = []
  } finally {
    loading.value = false
    loaded.value = true
  }
}

// refresh the machines list when the modal closes (a key may have been generated)
watch(showModal, (o) => { if (!o) loadStatus() })

onMounted(loadStatus)
</script>
