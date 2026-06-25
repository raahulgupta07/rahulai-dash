<template>
  <UModal v-model="isOpen" :ui="{ width: 'sm:max-w-xl' }">
    <div class="bg-white rounded-2xl overflow-hidden">
      <!-- header -->
      <div class="flex items-start justify-between px-5 py-4 border-b border-[#EFEDE6]">
        <div>
          <h3 class="text-base font-semibold text-[#2B2622] flex items-center gap-1.5" style="font-family: ui-serif, Georgia, 'Times New Roman', serif">
            <span class="text-[#C2683F]">⟳</span> Set up Folder Sync
          </h3>
          <p class="text-[11.5px] text-[#8A7E76] mt-0.5">
            Auto-ingest a local folder into your agent — like Claude Code.
          </p>
        </div>
        <button type="button" class="text-[#8A7E76] hover:text-[#2B2622]" @click="close">
          <UIcon name="i-heroicons-x-mark" class="w-5 h-5" />
        </button>
      </div>

      <!-- flag-off / not-enabled -->
      <div v-if="disabled" class="px-5 py-10 text-center">
        <UIcon name="i-heroicons-lock-closed" class="w-8 h-8 mx-auto text-[#8A7E76] mb-2" />
        <p class="text-sm text-[#2B2622] font-medium">Folder Sync isn't enabled for your org yet.</p>
        <p class="text-[11.5px] text-[#8A7E76] mt-1">Ask an admin to enable the <code>HYBRID_FOLDER_SYNC</code> feature flag.</p>
      </div>

      <div v-else class="px-5 py-4 space-y-5 max-h-[70vh] overflow-y-auto">
        <!-- STEP 1 · DOWNLOAD -->
        <div class="relative border border-[#E8C9B5] rounded-xl bg-[#FBF4EF] p-4">
          <span class="absolute -top-2.5 left-4 bg-[#2B2622] text-white text-[9.5px] font-semibold px-2.5 py-0.5 rounded-full tracking-wide">1 · DOWNLOAD</span>
          <p class="text-[13px] font-semibold text-[#2B2622] mt-1">Download the sync app</p>
          <p class="text-[11.5px] text-[#8A7E76] mt-0.5 mb-3">A tiny background helper that watches a folder and pushes new/changed files to your agent.</p>
          <div class="flex flex-wrap gap-2">
            <a v-for="os in osButtons" :key="os.key" :href="os.href" download
               class="inline-flex items-center gap-1.5 text-[12px] font-medium text-[#2B2622] bg-white border border-[#E8C9B5] rounded-lg px-3 py-1.5 hover:bg-[#F4E5DA] transition-colors">
              <UIcon :name="os.icon" class="w-3.5 h-3.5 text-[#C2683F]" /> {{ os.label }}
            </a>
          </div>
          <p class="text-[10.5px] text-[#8A7E76] mt-2">Downloads the Python sync app (+ INSTALL.txt). Run <span class="font-mono">python sync_agent.py setup</span> then <span class="font-mono">run</span>.</p>
        </div>

        <!-- STEP 2 · KEY -->
        <div class="relative border border-[#E8C9B5] rounded-xl bg-white p-4">
          <span class="absolute -top-2.5 left-4 bg-[#2B2622] text-white text-[9.5px] font-semibold px-2.5 py-0.5 rounded-full tracking-wide">2 · KEY</span>
          <p class="text-[13px] font-semibold text-[#2B2622] mt-1">Copy your sync key</p>
          <p class="text-[11.5px] text-[#8A7E76] mt-0.5 mb-3">The key authenticates the desktop app as you. <b class="text-[#A8542F]">Shown once — store it safe.</b></p>

          <button v-if="!generated" type="button" :disabled="generating"
                  class="inline-flex items-center gap-1.5 text-[12px] font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-3.5 py-2 transition-colors disabled:opacity-50"
                  @click="generateKey">
            <Spinner v-if="generating" class="h-3.5 w-3.5 text-white" />
            <UIcon v-else name="i-heroicons-key" class="w-3.5 h-3.5" />
            {{ generating ? 'Generating…' : 'Generate sync key' }}
          </button>

          <div v-else class="space-y-3">
            <div>
              <div class="text-[10px] uppercase tracking-wide text-[#8A7E76] mb-1">Sync key</div>
              <div class="flex items-stretch gap-2">
                <code class="flex-1 text-[11.5px] font-mono text-[#2B2622] bg-[#FBF4EF] border border-dashed border-[#E8C9B5] rounded-lg px-3 py-2 break-all">{{ keyVal }}</code>
                <button type="button" class="shrink-0 inline-flex items-center gap-1 text-[11px] font-medium text-[#2B2622] bg-white border border-[#E8C9B5] rounded-lg px-2.5 hover:bg-[#F4E5DA]" @click="copy(keyVal, 'key')">
                  <UIcon :name="copied === 'key' ? 'i-heroicons-check' : 'i-heroicons-clipboard-document'" class="w-3.5 h-3.5" :class="copied === 'key' ? 'text-[#3F8C5E]' : 'text-[#C2683F]'" />
                  {{ copied === 'key' ? 'Copied' : 'Copy' }}
                </button>
              </div>
            </div>
            <div>
              <div class="text-[10px] uppercase tracking-wide text-[#8A7E76] mb-1">Server URL</div>
              <div class="flex items-stretch gap-2">
                <code class="flex-1 text-[11.5px] font-mono text-[#2B2622] bg-[#FBF4EF] border border-dashed border-[#E8C9B5] rounded-lg px-3 py-2 break-all">{{ serverUrl }}</code>
                <button type="button" class="shrink-0 inline-flex items-center gap-1 text-[11px] font-medium text-[#2B2622] bg-white border border-[#E8C9B5] rounded-lg px-2.5 hover:bg-[#F4E5DA]" @click="copy(serverUrl, 'url')">
                  <UIcon :name="copied === 'url' ? 'i-heroicons-check' : 'i-heroicons-clipboard-document'" class="w-3.5 h-3.5" :class="copied === 'url' ? 'text-[#3F8C5E]' : 'text-[#C2683F]'" />
                  {{ copied === 'url' ? 'Copied' : 'Copy' }}
                </button>
              </div>
            </div>
            <p v-if="prefix" class="text-[10.5px] text-[#8A7E76]">Key prefix <code class="font-mono">{{ prefix }}</code> — that's how you'll recognise it later (the full key won't be shown again).</p>
          </div>

          <p v-if="keyError" class="mt-2 flex items-start gap-1.5 text-[11.5px] text-red-600">
            <UIcon name="i-heroicons-exclamation-circle" class="w-4 h-4 shrink-0 mt-px" /> <span>{{ keyError }}</span>
          </p>
        </div>

        <!-- STEP 3 · FOLDER -->
        <div class="relative border border-[#E8C9B5] rounded-xl bg-white p-4">
          <span class="absolute -top-2.5 left-4 bg-[#2B2622] text-white text-[9.5px] font-semibold px-2.5 py-0.5 rounded-full tracking-wide">3 · FOLDER</span>
          <p class="text-[13px] font-semibold text-[#2B2622] mt-1">Pick a folder &amp; go</p>
          <ol class="text-[11.5px] text-[#8A7E76] mt-1.5 space-y-1 list-decimal pl-4">
            <li>Open the desktop sync app you downloaded.</li>
            <li>Paste your <b>sync key</b> and <b>server URL</b> from step 2.</li>
            <li>Choose a local folder to watch — new and changed files auto-ingest.</li>
          </ol>
          <p v-if="targetStudioName" class="text-[11.5px] text-[#2B2622] mt-2 bg-[#FBF4EF] border border-[#E8C9B5] rounded-lg px-3 py-2">
            This folder will sync into: <b>{{ targetStudioName }}</b>.
          </p>
          <p v-else class="text-[11.5px] text-[#8A7E76] mt-2">Pick which agent to sync into, inside the app.</p>
        </div>
      </div>

      <!-- footer -->
      <div class="flex items-center justify-end gap-2 px-5 py-3 border-t border-[#EFEDE6]">
        <button type="button" class="text-[12px] font-medium text-[#8A7E76] hover:text-[#2B2622] px-3 py-1.5" @click="close">Cancel</button>
        <button type="button" class="text-[12px] font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] rounded-lg px-4 py-1.5 transition-colors" @click="close">Done</button>
      </div>
    </div>
  </UModal>
</template>

<script setup lang="ts">
// Folder Sync setup modal — 3-step download → key → folder flow.
// v-model:open pattern (open prop + update:open emit). Fail-soft on 404 (flag off).
import Spinner from '~/components/Spinner.vue'

const props = defineProps<{
  open: boolean
  targetStudioId?: string
  targetStudioName?: string
}>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const isOpen = computed({
  get: () => props.open,
  set: (v: boolean) => { if (!v) close() },
})
function close() { emit('update:open', false) }

const osButtons = [
  { key: 'mac', label: 'macOS', icon: 'i-heroicons-computer-desktop', href: '/api/sync/download/macos' },
  { key: 'win', label: 'Windows', icon: 'i-heroicons-rectangle-group', href: '/api/sync/download/windows' },
  { key: 'linux', label: 'Linux', icon: 'i-heroicons-command-line', href: '/api/sync/download/linux' },
]

// ---- key generation ----
const generating = ref(false)
const generated = ref(false)
const keyVal = ref('')
const serverUrl = ref('')
const prefix = ref('')
const keyError = ref('')
const disabled = ref(false)
const copied = ref<string | null>(null)

async function generateKey() {
  if (generating.value) return
  generating.value = true
  keyError.value = ''
  try {
    const name = `Folder Sync — ${(typeof navigator !== 'undefined' && navigator.platform) || 'desktop'}`
    const { data, error } = await useMyFetch<any>('/sync/key', { method: 'POST', body: { name } })
    if (error?.value) throw error.value
    const r: any = data.value || {}
    keyVal.value = r.key || ''
    serverUrl.value = r.server_url || ''
    prefix.value = r.prefix || ''
    generated.value = true
  } catch (e: any) {
    const status = e?.statusCode || e?.response?.status
    if (status === 404) { disabled.value = true }
    else { keyError.value = e?.data?.message || e?.message || 'Could not generate a sync key.' }
  } finally {
    generating.value = false
  }
}

async function copy(text: string, which: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = which
    setTimeout(() => { if (copied.value === which) copied.value = null }, 1500)
  } catch { /* clipboard unavailable — no-op */ }
}

// reset transient state each time the modal re-opens
watch(() => props.open, (o) => {
  if (o) { keyError.value = ''; copied.value = null }
})
</script>
