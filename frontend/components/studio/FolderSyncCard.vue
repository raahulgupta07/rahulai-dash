<template>
  <!-- Hidden entirely when the flag is off (404) or status never loaded. -->
  <div v-if="!hidden">
    <!-- EMPTY STATE — no synced folder yet for this studio -->
    <div v-if="!paths.length" class="rounded-xl border border-dashed border-[#E8C9B5] bg-[#FBF4EF] px-4 py-3">
      <div class="flex items-center gap-1.5 mb-1">
        <span class="text-[#C2683F] text-sm">⟳</span>
        <h3 class="text-[13px] font-semibold text-[#2B2622]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Folder Sync</h3>
      </div>
      <p class="text-[11.5px] text-[#8A7E76] mb-2.5">Auto-ingest a local folder into this agent — like Claude Code.</p>
      <button type="button"
              class="inline-flex items-center gap-1.5 text-[12px] font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3 py-1.5 transition-colors"
              @click="showModal = true">
        <UIcon name="i-heroicons-folder-plus" class="w-3.5 h-3.5" />
        Set up folder sync
      </button>
    </div>

    <!-- LIVE CARD — this studio has synced paths -->
    <div v-else class="rounded-xl border border-[#E8C9B5] bg-[#FBF4EF] px-4 py-3">
      <div class="flex items-center justify-between gap-2 mb-2">
        <div class="flex items-center gap-1.5">
          <span class="text-[#C2683F] text-sm">⟳</span>
          <h3 class="text-[13px] font-semibold text-[#2B2622]" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">Folder Sync</h3>
          <span class="text-[#E8C9B5]">·</span>
          <span class="inline-flex items-center gap-1 text-[11px] font-medium text-[#3F8C5E]">
            <span class="w-1.5 h-1.5 rounded-full bg-[#3F8C5E]"></span> Live
          </span>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          <button type="button"
                  class="inline-flex items-center gap-1 text-[11px] font-medium text-[#2B2622] bg-white border border-[#E8C9B5] rounded-lg px-2.5 py-1 hover:bg-[#F4E5DA] transition-colors"
                  @click="showModal = true">
            <UIcon name="i-heroicons-cog-6-tooth" class="w-3.5 h-3.5 text-[#C2683F]" /> Manage
          </button>
          <UTooltip text="Pause from the desktop app">
            <button type="button" disabled
                    class="inline-flex items-center gap-1 text-[11px] font-medium text-[#8A7E76] bg-white border border-[#E8C9B5] rounded-lg px-2.5 py-1 opacity-60 cursor-not-allowed">
              <UIcon name="i-heroicons-pause" class="w-3.5 h-3.5" /> Pause
            </button>
          </UTooltip>
        </div>
      </div>

      <!-- folder path(s) -->
      <ul class="space-y-1 mb-2">
        <li v-for="(p, i) in paths" :key="i" class="flex items-center gap-1.5 min-w-0">
          <UIcon name="i-heroicons-folder" class="w-3.5 h-3.5 text-[#C2683F] shrink-0" />
          <code class="text-[11px] font-mono text-[#2B2622] truncate">{{ p.source_path }}</code>
          <span v-if="p.file_name" class="text-[10.5px] text-[#8A7E76] truncate">/ {{ p.file_name }}</span>
        </li>
      </ul>

      <p class="text-[11px] text-[#8A7E76]">
        {{ fileCount }} file{{ fileCount === 1 ? '' : 's' }} · synced {{ lastSyncedLabel }} · auto-updates
      </p>
    </div>

    <FolderSyncSetupModal
      v-model:open="showModal"
      :target-studio-id="studioId"
      :target-studio-name="studioName"
    />
  </div>
</template>

<script setup lang="ts">
// Per-agent Folder Sync card on a Studio's Sources tab. Reads GET /sync/status,
// filters paths by studio_id. Hidden when the flag is off (404). Fail-soft.
import FolderSyncSetupModal from '~/components/sync/FolderSyncSetupModal.vue'

const props = defineProps<{ studioId: string; studioName: string }>()

const hidden = ref(true)          // hidden until status loads (and stays hidden on 404)
const paths = ref<any[]>([])      // synced paths whose studio_id === this studio
const lastSyncAt = ref<string | null>(null)
const showModal = ref(false)

const fileCount = computed(() =>
  paths.value.reduce((n, p) => n + (Number(p.files) || 0), 0) || paths.value.length
)

const lastSyncedLabel = computed(() => lastSyncAt.value ? `${timeAgo(lastSyncAt.value)} ago` : 'just now')

function timeAgo(date: string) {
  const secs = Math.floor((Date.now() - new Date(date).getTime()) / 1000)
  if (secs < 0 || isNaN(secs)) return 'just now'
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`
  return `${Math.floor(secs / 86400)}d`
}

async function loadStatus() {
  try {
    const { data, error } = await useMyFetch<any>('/sync/status', { method: 'GET' })
    if (error?.value) throw error.value
    const machines: any[] = (data.value as any)?.machines || []
    const mine: any[] = []
    let latest: string | null = null
    for (const m of machines) {
      for (const p of (m.paths || [])) {
        if (String(p.studio_id || '') === String(props.studioId)) {
          mine.push({ ...p, files: p.files })
          const at = p.last_sync_at || m.last_sync_at
          if (at && (!latest || new Date(at) > new Date(latest))) latest = at
        }
      }
    }
    paths.value = mine
    lastSyncAt.value = latest
    hidden.value = false          // flag is on → render (empty-state or live)
  } catch (e: any) {
    // 404 (flag off) or any failure → render nothing.
    hidden.value = true
  }
}

onMounted(loadStatus)
</script>
