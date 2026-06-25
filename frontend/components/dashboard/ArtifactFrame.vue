<template>
  <div class="h-full w-full flex flex-col bg-white">
    <!-- Header / Toolbar -->
    <div class="flex-shrink-0 flex items-center justify-between px-4 py-2 bg-gradient-to-b from-cyan-50/50 to-white border-b">
      <div class="flex items-center gap-3">
        <UTooltip text="Back to chat">
          <button @click="$emit('close')" class="hover:bg-gray-100 p-1 rounded">
            <Icon name="heroicons:x-mark" class="w-4 h-4 text-gray-500" />
          </button>
        </UTooltip>

        <!-- Artifact Selector Dropdown -->
        <div class="flex items-center gap-2">
          <USelectMenu
            v-if="artifactsList.length > 0"
            v-model="selectedArtifactId"
            :options="artifactOptions"
            value-attribute="value"
            option-attribute="label"
            size="xs"
            class="min-w-[280px]"
            placeholder="Select artifact..."
            :ui="{ option: { base: 'py-2' } }"
          >
            <template #label>
              <span class="truncate text-xs">{{ selectedArtifactLabel }}</span>
            </template>
            <template #option="{ option }">
              <div class="flex flex-col gap-0.5 w-full">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-medium text-gray-900 truncate">{{ option.artifact.title || 'Untitled' }}</span>
                  <span class="text-[10px] text-gray-400 ms-2">v{{ option.artifact.version }}</span>
                </div>
                <div class="flex items-center justify-between text-[10px] text-gray-400">
                  <span>{{ formatRelativeTime(option.artifact.created_at) }}</span>
                  <button
                    @click.stop="copyArtifactId(option.artifact.id)"
                    class="hover:text-gray-600 flex items-center gap-0.5 font-mono"
                    title="Click to copy ID"
                  >
                    <Icon name="heroicons:clipboard-document" class="w-3 h-3" />
                    {{ option.artifact.id.slice(0, 8) }}
                  </button>
                </div>
              </div>
            </template>
          </USelectMenu>
          <span v-else class="text-xs text-gray-400 italic">No artifacts yet</span>

          <!-- Use this version button (shown when non-latest is selected) -->
          <button
            v-if="!isLatestSelected && artifactsList.length > 1"
            @click="useThisVersion"
            :disabled="isDuplicating"
            class="text-xs px-2 py-1 bg-[#F6EFEA] text-[#C2683F] hover:bg-[#F4E5DA] rounded border border-[#E8C9B5] transition-colors disabled:opacity-50 flex items-center gap-1"
          >
            <Spinner v-if="isDuplicating" class="w-3 h-3" />
            <Icon v-else name="heroicons:arrow-uturn-up" class="w-3 h-3" />
            Use this version
          </button>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <span v-if="isLoading" class="text-xs text-gray-400">{{ t('artifactFrame.loading') }}</span>

        <!-- Refresh Dashboard (rerun + refresh) -->
        <UTooltip text="Refresh Data">
          <button
            @click="refreshDashboard"
            :disabled="isRefreshing"
            class="p-1.5 hover:bg-gray-100 rounded transition-colors disabled:opacity-50"
          >
            <Spinner v-if="isRefreshing" class="w-3.5 h-3.5 text-gray-500" />
            <Icon v-else name="heroicons:arrow-path" class="w-3.5 h-3.5 text-gray-500" />
          </button>
        </UTooltip>

        <!-- Schedule -->
        <CronModal v-if="report" :report="report" />

        <!-- Export PPTX (slides mode only) -->
        <UTooltip v-if="selectedArtifact?.mode === 'slides'" text="Export as PowerPoint">
          <button
            @click="exportPptx"
            :disabled="isExporting"
            class="text-lg items-center flex gap-1 hover:bg-gray-100 px-2 py-1 rounded disabled:opacity-50"
          >
            <Icon v-if="isExporting" name="heroicons:arrow-path" class="w-3.5 h-3.5 text-gray-500 animate-spin" />
            <Icon v-else name="heroicons:arrow-down-tray" class="w-3.5 h-3.5 text-purple-600" />
            <span class="text-xs text-purple-600 font-medium">PPTX</span>
          </button>
        </UTooltip>

        <!-- Fullscreen / collapse (true fullscreen of the deck) -->
        <UTooltip :text="isFullscreen ? 'Exit full screen' : 'Full screen'">
          <button @click="openFullscreen" class="text-lg items-center flex gap-1 hover:bg-gray-100 px-2 py-1 rounded">
            <Icon
              :name="isFullscreen ? 'heroicons:arrows-pointing-in' : 'heroicons:arrows-pointing-out'"
              class="w-3.5 h-3.5 text-gray-500"
            />
          </button>
        </UTooltip>

        <!-- Open in new tab (if published) -->
        <UTooltip text="Open in new tab" v-if="report?.status === 'published'">
          <a :href="`/r/${report.id}`" target="_blank" class="text-lg items-center flex gap-1 hover:bg-gray-100 px-2 py-1 rounded">
            <Icon name="heroicons:arrow-top-right-on-square" class="w-3.5 h-3.5 text-gray-500" />
          </a>
        </UTooltip>

        <!-- Share Dashboard -->
        <ShareModal v-if="report" :report="report" share-type="artifact" title="Share Dashboard" />
      </div>
    </div>

    <!-- Iframe Container -->
    <div class="flex-1 min-h-0 relative bg-white">
      <!-- Loading State -->
      <div v-if="isLoading" class="absolute inset-0 flex items-center justify-center bg-white">
        <div class="flex flex-col items-center gap-3">
          <Spinner class="w-6 h-6 text-gray-400" />
          <span class="text-sm text-gray-400">{{ t('artifactFrame.loading') }}</span>
        </div>
      </div>

      <!-- Empty State: Has visualizations but no artifact - show Generate Dashboard button -->
      <div v-else-if="!hasArtifact && hasSuccessfulVisualizations" class="absolute inset-0 flex flex-col items-center justify-center bg-white">
        <Icon name="heroicons:sparkles" class="w-8 h-8 text-gray-400 mb-3" />
        <h3 class="text-sm font-medium text-gray-700 mb-1">Ready to create a dashboard</h3>
        <p class="text-xs text-gray-400 mb-4 max-w-xs text-center">
          You have {{ visualizationsData.length }} visualization{{ visualizationsData.length !== 1 ? 's' : '' }} ready
        </p>
        <UButton
          @click="generateDashboardPrompt"
          size="xs"
          color="primary"
        >
          <Icon name="heroicons:bolt" class="w-4 h-4" />
          Generate Dashboard
        </UButton>
      </div>

      <!-- Empty State: No visualizations and no artifact -->
      <div v-else-if="!hasArtifact && !hasVisualizations" class="absolute inset-0 flex flex-col items-center justify-center bg-white">
        <Icon name="heroicons:chart-bar" class="w-6 h-6 text-gray-400 mb-2" />
        <span class="text-sm text-gray-400">No dashboard items yet</span>
      </div>

      <!-- Build Stopped / Timed-out State (anti-stuck) -->
      <div v-else-if="isPendingArtifact && buildError" class="absolute inset-0 flex flex-col items-center justify-center bg-[#FBFAF6] gap-2.5 text-center px-6">
        <Icon name="heroicons:exclamation-triangle" class="w-8 h-8 text-red-500 mb-1" />
        <h3 class="text-base font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, serif;">Dashboard build stopped</h3>
        <p class="text-xs text-[#6b6b6b] max-w-xs">The agent hit an error before finishing. No more spinning.</p>
        <button
          @click="retryBuild"
          class="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] border border-[#C2683F] transition-colors"
        >
          <Icon name="heroicons:arrow-path" class="w-4 h-4" />
          Retry build
        </button>
      </div>

      <!-- Pending Artifact State (generating) -->
      <div v-else-if="isPendingArtifact" class="absolute inset-0 bg-white">
        <DashboardSkeleton :mode="selectedArtifact?.mode === 'slides' ? 'slides' : 'page'" />
      </div>

      <!-- Slides Mode with Preview Images - Use SlideViewer -->
      <SlideViewer
        v-else-if="hasSlidesWithPreviews && selectedArtifact"
        :artifact-id="selectedArtifact.id"
        class="absolute inset-0"
      />

      <!-- Slides with no rendered preview (failed / not rendered) — clean state,
           never the python-pptx code dump. -->
      <div v-else-if="isUnrenderableSlides" class="absolute inset-0 flex flex-col items-center justify-center bg-[#FBFAF6] gap-2.5 text-center px-6">
        <Icon
          :name="selectedArtifact?.status === 'failed' ? 'heroicons:exclamation-triangle' : 'heroicons:presentation-chart-line'"
          class="w-8 h-8 mb-1"
          :class="selectedArtifact?.status === 'failed' ? 'text-red-500' : 'text-[#C2683F]'"
        />
        <h3 class="text-base font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, serif;">
          {{ selectedArtifact?.status === 'failed' ? 'Presentation generation failed' : 'No rendered slides yet' }}
        </h3>
        <p class="text-xs text-[#6b6b6b] max-w-xs">
          This deck has no rendered preview. Regenerate it{{ selectedArtifact?.pptx_path ? ', or download the PowerPoint.' : '.' }}
        </p>
        <div class="flex items-center gap-2 mt-1">
          <button
            @click="regenerateSlides"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-[#C2683F] hover:bg-[#A8542F] border border-[#C2683F] transition-colors"
          >
            <Icon name="heroicons:arrow-path" class="w-4 h-4" />
            Regenerate
          </button>
          <button
            v-if="selectedArtifact?.pptx_path"
            @click="exportPptx"
            class="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-[#1f2328] bg-white hover:bg-[#F4F1EA] border border-[#E7E5DD] transition-colors"
          >
            <Icon name="heroicons:arrow-down-tray" class="w-4 h-4" />
            Download .pptx
          </button>
        </div>
      </div>

      <!-- Iframe Render Error State -->
      <div v-else-if="iframeError" class="absolute inset-0 flex flex-col items-center justify-center bg-white">
        <Icon name="heroicons:exclamation-triangle" class="w-8 h-8 text-red-400 mb-3" />
        <h3 class="text-sm font-medium text-gray-700 mb-1">Dashboard failed to render</h3>
        <p class="text-xs text-gray-400 mb-3 max-w-md text-center font-mono bg-gray-50 rounded p-2 border">
          {{ iframeError.length > 200 ? iframeError.slice(0, 200) + '...' : iframeError }}
        </p>
        <UButton
          @click="fixRenderError"
          size="xs"
          color="red"
          variant="soft"
        >
          <Icon name="heroicons:wrench-screwdriver" class="w-4 h-4" />
          Fix Error
        </UButton>
      </div>

      <!-- Iframe (shown when artifact exists and data is ready) -->
      <iframe
        v-show="hasArtifact && !isLoading && !isPendingArtifact && !hasSlidesWithPreviews && !isUnrenderableSlides && !iframeError && iframeSrcdoc"
        ref="iframeRef"
        :srcdoc="iframeSrcdoc"
        sandbox="allow-scripts allow-same-origin"
        class="absolute inset-0 w-full h-full border-0 bg-white z-0"
        @load="onIframeLoad"
      />

      <!-- Polish Mode Button -->
      <div
        v-if="hasArtifact && !isLoading && !isPendingArtifact && !iframeError"
        class="absolute bottom-4 left-4 z-20"
      >
        <button
          @click="togglePolishMode"
          :class="[
            'flex items-center gap-2 px-3 py-2 rounded-full shadow-lg transition-all',
            isPolishMode
              ? 'bg-indigo-600 text-white hover:bg-indigo-700 ring-2 ring-indigo-300'
              : 'bg-gray-800 text-gray-100 hover:bg-gray-700'
          ]"
        >
          <Icon name="heroicons:paint-brush" class="w-4 h-4" />
          <span class="text-xs font-medium">{{ t('toolbar.polishDashboard') }}</span>
        </button>
      </div>

      <!-- Polish Prompt Box -->
      <div
        v-if="polishPromptVisible"
        class="absolute z-30 w-80 bg-white rounded-lg shadow-xl border border-gray-200 p-3"
        :style="polishPromptPosition"
      >
        <div class="flex items-center gap-2 mb-2">
          <Icon name="heroicons:paint-brush" class="w-3.5 h-3.5 text-indigo-500" />
          <span class="text-xs font-medium text-gray-700">Polish this element</span>
          <button @click="cancelPolishPrompt" class="ms-auto text-gray-400 hover:text-gray-600">
            <Icon name="heroicons:x-mark" class="w-3.5 h-3.5" />
          </button>
        </div>
        <div class="text-[10px] text-gray-400 mb-2 font-mono bg-gray-50 rounded px-2 py-1 truncate">
          &lt;{{ polishSelectedElement?.tag?.toLowerCase() }}&gt; {{ polishSelectedElement?.text?.slice(0, 60) }}
        </div>
        <form @submit.prevent="submitPolishPrompt" class="flex gap-2">
          <input
            ref="polishInputRef"
            v-model="polishInstruction"
            type="text"
            placeholder="e.g. make this bigger, change colors..."
            class="flex-1 text-sm border border-gray-200 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400"
            @keydown.escape="cancelPolishPrompt"
          />
          <button
            type="submit"
            :disabled="!polishInstruction.trim()"
            class="px-3 py-1.5 bg-indigo-500 text-white text-sm rounded-md hover:bg-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Apply
          </button>
        </form>
      </div>
    </div>

    <!-- True Fullscreen Deck Overlay -->
    <!-- This wrapper is the element we hand to the native Fullscreen API; it also
         doubles as the fixed full-viewport fallback when the API is unavailable.
         Esc closes it (native fullscreenchange OR our keydown handler). -->
    <Teleport to="body">
      <div
        v-if="isFullscreen"
        ref="fullscreenContainerRef"
        class="fixed inset-0 z-[100] bg-black/90 flex flex-col"
      >
        <!-- Overlay header: title + visible close affordance -->
        <div class="flex-shrink-0 flex items-center justify-between px-4 py-2 bg-black/60 text-white/90">
          <div class="flex items-center gap-3 min-w-0">
            <span class="text-sm font-medium truncate">{{ selectedArtifact?.title || reportData?.title || 'Artifact' }}</span>
            <span v-if="selectedArtifact" class="text-xs text-white/50">v{{ selectedArtifact.version }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="hidden sm:inline text-[11px] text-white/40">Esc to exit</span>
            <UTooltip text="Exit full screen">
              <button
                @click="closeFullscreen"
                class="flex items-center gap-1 px-2 py-1 rounded hover:bg-white/10 transition-colors"
              >
                <Icon name="heroicons:arrows-pointing-in" class="w-4 h-4 text-white/80" />
                <Icon name="heroicons:x-mark" class="w-4 h-4 text-white/80" />
              </button>
            </UTooltip>
          </div>
        </div>

        <!-- Deck content: scaled to fit the viewport, centered, no cropping. -->
        <div class="flex-1 min-h-0 relative flex items-center justify-center p-2 sm:p-4">
          <!-- Slides with previews use SlideViewer (internal prev/next nav) -->
          <SlideViewer
            v-if="hasSlidesWithPreviews && selectedArtifact"
            :artifact-id="selectedArtifact.id"
            class="absolute inset-2 sm:inset-4 rounded-lg overflow-hidden bg-white shadow-2xl"
          />
          <!-- Other artifacts use iframe. This is a SECOND iframe instance, so
               it must receive its own ARTIFACT_DATA — sendDataToIframe() posts
               to both this and the background iframe (else charts stay blank). -->
          <iframe
            v-else-if="iframeSrcdoc"
            ref="fullscreenIframeRef"
            :srcdoc="iframeSrcdoc"
            sandbox="allow-scripts allow-same-origin"
            class="absolute inset-2 sm:inset-4 w-auto h-auto border-0 rounded-lg bg-white shadow-2xl"
            @load="onFullscreenIframeLoad"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, toRaw, nextTick } from 'vue';
import { useMyFetch } from '~/composables/useMyFetch';
import CronModal from '../CronModal.vue';
import ShareModal from '../ShareModal.vue';
import Spinner from '../Spinner.vue';
import SlideViewer from './SlideViewer.vue';
import DashboardSkeleton from './DashboardSkeleton.vue';
import { buildArtifactIframeHtml } from '~/utils/artifactIframe';

const { t } = useI18n();
const toast = useToast();
const config = useRuntimeConfig();
const { token } = useAuth();
const { organization } = useOrganization();

// Format relative time (e.g., "2 hours ago")
function formatRelativeTime(dateString: string): string {
  // Append 'Z' to treat as UTC since backend stores UTC without timezone info
  const date = new Date(dateString.endsWith('Z') ? dateString : dateString + 'Z');
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

// Copy artifact ID to clipboard
async function copyArtifactId(id: string) {
  try {
    await navigator.clipboard.writeText(id);
    toast.add({ title: 'Copied', description: 'Artifact ID copied to clipboard', color: 'green' });
  } catch {
    toast.add({ title: 'Failed to copy', color: 'red' });
  }
}

interface ArtifactItem {
  id: string;
  title: string;
  version: number;
  created_at: string;
  mode: string;
  status?: string;
}

const props = defineProps<{
  reportId: string;
  report?: any;
  artifactCode?: string;
  // Optional: narrow which artifacts this frame shows by mode.
  // 'page' = dashboards only, 'slides' = presentations only.
  // Omitted/undefined = no filter (current behavior, every other caller unaffected).
  modeFilter?: 'page' | 'slides';
}>();

defineEmits<{
  (e: 'close'): void;
}>();

// True-fullscreen state: tracks whether the deck overlay is currently expanded.
// Synced with the browser Fullscreen API via a `fullscreenchange` listener so
// the icon and DOM stay correct even when the user exits via Esc / browser UI.
const isFullscreen = ref(false);
// Container element we request native fullscreen on. We fullscreen this wrapper
// (not the iframe directly) so a sandboxed/cross-origin deck iframe still works —
// the overlay also acts as the fallback when the Fullscreen API is unavailable.
const fullscreenContainerRef = ref<HTMLElement | null>(null);

// Export state
const isExporting = ref(false);

// Refresh state
const isRefreshing = ref(false);

// Iframe render error state
const iframeError = ref<string | null>(null);

// Anti-stuck: poll + timeout watcher for pending artifacts so the skeleton
// never spins forever if the agent fails mid-build.
const POLL_INTERVAL_MS = 5000;   // re-fetch artifact status every ~5s
const BUILD_TIMEOUT_MS = 90000;  // give up after ~90s → show error+retry
const buildError = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;
let pollStartedAt = 0;

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPolling() {
  // Guard against double-intervals.
  if (pollTimer) return;
  pollStartedAt = Date.now();
  pollTimer = setInterval(async () => {
    // Stop if no longer pending (status flipped) — defensive re-check.
    if (selectedArtifact.value?.status !== 'pending') {
      stopPolling();
      return;
    }
    // Timeout → error state.
    if (Date.now() - pollStartedAt > BUILD_TIMEOUT_MS) {
      buildError.value = true;
      stopPolling();
      return;
    }
    // Re-fetch status; fetch errors must never crash the component.
    try {
      await fetchSelectedArtifact();
    } catch (e) {
      console.error('[ArtifactFrame] Poll fetch failed:', e);
      buildError.value = true;
      stopPolling();
    }
  }, POLL_INTERVAL_MS);
}

// Retry a stuck build: reset error state, re-fetch, and (if available) re-run
// the report to regenerate, then resume polling.
async function retryBuild() {
  buildError.value = false;
  stopPolling();
  try {
    await fetchSelectedArtifact();
  } catch (e) {
    console.error('[ArtifactFrame] Retry fetch failed:', e);
  }
  // If a re-run hook exists, kick it (best-effort, never crash).
  try {
    if (props.reportId) {
      await useMyFetch(`/api/reports/${props.reportId}/rerun`, { method: 'POST' });
    }
  } catch (e) {
    console.error('[ArtifactFrame] Retry rerun failed:', e);
  }
  // Resume polling only if still pending.
  if (selectedArtifact.value?.status === 'pending') {
    startPolling();
  }
}

// Polish mode state
const isPolishMode = ref(false);
const polishPromptVisible = ref(false);
const polishInstruction = ref('');
const polishInputRef = ref<HTMLInputElement | null>(null);
const polishSelectedElement = ref<{ tag: string; classes: string; text: string; htmlSnippet: string; rect: { top: number; left: number; width: number; height: number } } | null>(null);

const polishPromptPosition = computed(() => {
  if (!polishSelectedElement.value?.rect) return { top: '50%', left: '50%' };
  const r = polishSelectedElement.value.rect;
  // Position below the element, clamped within the container
  const top = Math.min(Math.max(r.top + r.height + 8, 8), 500);
  const left = Math.min(Math.max(r.left, 8), 400);
  return { top: top + 'px', left: left + 'px' };
});

function togglePolishMode() {
  if (isPolishMode.value) {
    exitPolishMode();
  } else {
    enterPolishMode();
  }
}

function enterPolishMode() {
  isPolishMode.value = true;
  polishPromptVisible.value = false;
  polishSelectedElement.value = null;
  polishInstruction.value = '';
  // Tell iframe to enable pick mode (srcdoc iframe inherits parent origin)
  iframeRef.value?.contentWindow?.postMessage({ type: 'POLISH_ENTER' }, window.location.origin);
}

function exitPolishMode() {
  isPolishMode.value = false;
  polishPromptVisible.value = false;
  polishSelectedElement.value = null;
  polishInstruction.value = '';
  iframeRef.value?.contentWindow?.postMessage({ type: 'POLISH_EXIT' }, window.location.origin);
}

function cancelPolishPrompt() {
  polishPromptVisible.value = false;
  polishSelectedElement.value = null;
  polishInstruction.value = '';
  iframeRef.value?.contentWindow?.postMessage({ type: 'POLISH_ENTER' }, window.location.origin);
}

function submitPolishPrompt() {
  if (!polishInstruction.value.trim() || !polishSelectedElement.value) return;

  const artifactTitle = selectedArtifact.value?.title || 'the dashboard';
  const artifactId = selectedArtifact.value?.id || selectedArtifactId.value || '';
  const el = polishSelectedElement.value;
  const prompt = `Polish the dashboard "${artifactTitle}" (artifact_id: ${artifactId}).\nTarget element:\n\`\`\`html\n${el.htmlSnippet}\n\`\`\`\nInstruction: ${polishInstruction.value.trim()}`;

  window.dispatchEvent(new CustomEvent('prompt:prefill', {
    detail: { text: prompt, autoSubmit: true }
  }));

  exitPolishMode();
}

// Refresh Dashboard - reruns report queries and refreshes data
async function refreshDashboard() {
  if (isRefreshing.value) return;

  isRefreshing.value = true;
  isLoading.value = true;

  try {
    // Rerun the report (re-execute queries)
    const { error } = await useMyFetch(`/api/reports/${props.reportId}/rerun`, { method: 'POST' });
    if (error.value) throw error.value;

    // Refresh artifact data
    await refreshAll();

    toast.add({ title: 'Dashboard refreshed', color: 'green' });
  } catch (error: any) {
    console.error('Failed to refresh dashboard:', error);
    toast.add({ title: 'Error', description: `Failed to refresh dashboard. ${error.message || ''}`, color: 'red' });
  } finally {
    isRefreshing.value = false;
  }
}

// Toggle the deck into / out of a true fullscreen view of the current slide.
// Preferred path: the browser Fullscreen API on our overlay container element,
// which gives an edge-to-edge presenting view. If that's unavailable (older
// browser, blocked by policy, etc.) we fall back to a fixed full-viewport
// overlay — the overlay markup is rendered either way, so the deck shows large
// and the close affordance + Esc handling both still work.
function openFullscreen() {
  if (isFullscreen.value) {
    closeFullscreen();
    return;
  }
  // Show the overlay first so the container element exists, then request native
  // fullscreen on it on the next tick.
  isFullscreen.value = true;
  nextTick(() => {
    const el = fullscreenContainerRef.value;
    if (el && typeof el.requestFullscreen === 'function' && !document.fullscreenElement) {
      // Best-effort: if the API rejects (e.g. not user-gesture), the overlay
      // fallback already covers us — just keep going.
      el.requestFullscreen().catch((err) => {
        console.warn('[ArtifactFrame] requestFullscreen failed, using overlay fallback:', err);
      });
    }
  });
}

// Close fullscreen: exit the native Fullscreen API if active; the
// `fullscreenchange` handler then flips `isFullscreen` off. When we're in the
// overlay fallback (no native fullscreen element), close it directly.
function closeFullscreen() {
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {
      // If exit fails, force the overlay down so the user is never trapped.
      isFullscreen.value = false;
    });
  } else {
    isFullscreen.value = false;
  }
}

// Keep `isFullscreen` in sync with the native Fullscreen API. This fires when
// the user exits via Esc or browser chrome, so our overlay tears down too.
function handleFullscreenChange() {
  if (!document.fullscreenElement) {
    isFullscreen.value = false;
  }
}

// Esc-to-close for the overlay fallback (when native fullscreen isn't active,
// the browser won't emit `fullscreenchange`, so we handle the key ourselves).
function handleFullscreenKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isFullscreen.value && !document.fullscreenElement) {
    e.preventDefault();
    closeFullscreen();
  }
}

// Export artifact as PPTX
async function exportPptx() {
  if (!selectedArtifactId.value || isExporting.value) return;

  isExporting.value = true;
  try {
    // Use native fetch for blob download with same auth pattern as useMyFetch
    const headers: Record<string, string> = {
      Authorization: `${token.value}`,
    };
    if (organization.value?.id) {
      headers['X-Organization-Id'] = organization.value.id;
    }

    const response = await fetch(`${config.public.baseURL}/artifacts/${selectedArtifactId.value}/export/pptx`, {
      method: 'GET',
      headers
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    // Materialise the response body as bytes, then wrap in a fresh local
    // Blob with an explicit MIME type. Going through ArrayBuffer + new Blob
    // detaches the download URL from the remote response (binary content
    // never reaches the DOM as HTML).
    const arrayBuffer = await response.arrayBuffer();
    const localBlob = new Blob([arrayBuffer], {
      type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    });
    const rawTitle = selectedArtifact.value?.title || 'presentation';
    const safeName = String(rawTitle).replace(/[^\w\s.-]/g, '').slice(0, 120) || 'presentation';
    const url = window.URL.createObjectURL(localBlob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `${safeName}.pptx`);
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);

    toast.add({ title: 'Export complete', description: 'PowerPoint file downloaded successfully.' });
  } catch (error: any) {
    console.error('Failed to export PPTX:', error);
    toast.add({ title: 'Export failed', description: error.message || 'Failed to export PowerPoint file.', color: 'red' });
  } finally {
    isExporting.value = false;
  }
}

const iframeRef = ref<HTMLIFrameElement | null>(null);
// Second iframe used by the true-fullscreen overlay. It's a distinct instance
// from iframeRef, so it needs its own ARTIFACT_DATA postMessage.
const fullscreenIframeRef = ref<HTMLIFrameElement | null>(null);
const isLoading = ref(true);
const dataReady = ref(false);  // Guards iframeSrcdoc to prevent rendering before data loads
const iframeReady = ref(false);
const visualizationsData = ref<any[]>([]);
const reportData = ref<any>(null);

// Artifact selection state
const artifactsList = ref<ArtifactItem[]>([]);
const selectedArtifactId = ref<string | undefined>(undefined);
const selectedArtifact = ref<any>(null);

// Computed options for dropdown
const artifactOptions = computed(() => {
  return artifactsList.value.map(a => ({
    value: a.id,
    label: `${a.title || 'Untitled'} (v${a.version})`,
    artifact: a
  }));
});

const selectedArtifactLabel = computed(() => {
  const selected = artifactsList.value.find(a => a.id === selectedArtifactId.value);
  if (selected) {
    return `${selected.title || 'Untitled'} (v${selected.version})`;
  }
  return 'Select artifact...';
});

// Check if selected artifact is the latest (first in list, sorted by created_at desc)
const isLatestSelected = computed(() => {
  if (!selectedArtifactId.value || artifactsList.value.length === 0) return true;
  return artifactsList.value[0].id === selectedArtifactId.value;
});

// Check if selected artifact is pending (still generating)
const isPendingArtifact = computed(() => {
  return selectedArtifact.value?.status === 'pending';
});

// Start polling whenever an artifact enters the pending state; stop otherwise.
watch(isPendingArtifact, (pending) => {
  if (pending) {
    buildError.value = false;
    startPolling();
  } else {
    buildError.value = false;
    stopPolling();
  }
}, { immediate: true });

// Check if any artifacts exist
const hasArtifact = computed(() => {
  return artifactsList.value.length > 0;
});

// Check if visualizations data exists
const hasVisualizations = computed(() => {
  return visualizationsData.value.length > 0;
});

// Check if any visualization has a successful step status
const hasSuccessfulVisualizations = computed(() => {
  return visualizationsData.value.some(viz => viz.stepStatus === 'success');
});

// Check if we have slides mode with preview images (use SlideViewer instead of iframe)
const hasSlidesWithPreviews = computed(() => {
  if (!selectedArtifact.value) return false;
  if (selectedArtifact.value.mode !== 'slides') return false;
  const previewImages = selectedArtifact.value.content?.preview_images;
  return Array.isArray(previewImages) && previewImages.length > 0;
});

// Slides artifact that can't be shown as a deck: no rendered preview images
// (generation failed, or the PPTX render never produced PNGs). We must NOT fall
// through to the iframe — a slides artifact's content.code is python-pptx, which
// the iframe would dump as raw text. Show a clean state instead.
const isUnrenderableSlides = computed(() => {
  if (!selectedArtifact.value) return false;
  if (selectedArtifact.value.mode !== 'slides') return false;
  if (isPendingArtifact.value) return false;
  return !hasSlidesWithPreviews.value;
});

// Re-run the slides generation for this report (best-effort).
async function regenerateSlides() {
  const title = selectedArtifact.value?.title || 'the presentation';
  window.dispatchEvent(new CustomEvent('prompt:prefill', {
    detail: { text: `Regenerate the presentation "${title}" as a slide deck.`, autoSubmit: true }
  }));
}

// Generate dashboard prompt - dispatches event to update and submit prompt box
function generateDashboardPrompt() {
  const prompt = `Create a dashboard covering the data and visualizations created in this report. Design it with a clean, modern layout and narrative that presents the insights effectively.`;

  // Dispatch custom event to update and auto-submit the prompt box
  window.dispatchEvent(new CustomEvent('prompt:prefill', {
    detail: { text: prompt, autoSubmit: true }
  }));
}

// Fix render error - prefill prompt with error details
function fixRenderError() {
  const errorMsg = iframeError.value || 'Unknown error';
  const artifactTitle = selectedArtifact.value?.title || 'the dashboard';
  const artifactId = selectedArtifact.value?.id || selectedArtifactId.value || '';
  const prompt = `The dashboard "${artifactTitle}" (artifact_id: ${artifactId}) failed to render with this error:\n\`\`\`\n${errorMsg}\n\`\`\`\nPlease fix the artifact code so it renders correctly.`;

  window.dispatchEvent(new CustomEvent('prompt:prefill', {
    detail: { text: prompt, autoSubmit: false }
  }));
}

// State for "Use this version" action
const isDuplicating = ref(false);

// Duplicate the selected artifact to make it the latest/default
async function useThisVersion() {
  if (!selectedArtifactId.value || isDuplicating.value) return;

  isDuplicating.value = true;
  try {
    const { data, error } = await useMyFetch(`/api/artifacts/${selectedArtifactId.value}/duplicate`, {
      method: 'POST'
    });

    if (error.value) throw error.value;

    // Refresh the list and select the new artifact
    await fetchArtifactsList();
    if (data.value && (data.value as any).id) {
      selectedArtifactId.value = (data.value as any).id;
    }

    toast.add({ title: 'Version set as default', color: 'green' });
  } catch (error: any) {
    console.error('Failed to set version as default:', error);
    toast.add({ title: 'Error', description: 'Failed to set version as default.', color: 'red' });
  } finally {
    isDuplicating.value = false;
  }
}

// Handle artifact:select event (select a specific artifact by ID)
function handleArtifactSelect(event: Event) {
  const artifactId = (event as CustomEvent).detail?.artifact_id;
  if (artifactId && artifactsList.value.some(a => a.id === artifactId)) {
    selectedArtifactId.value = artifactId;
  }
}

// Handle artifact:created event (refresh list and select new artifact)
async function handleArtifactCreated(event: Event) {
  const artifactId = (event as CustomEvent).detail?.artifact_id;
  // Reset dataReady BEFORE selecting the new artifact so iframeSrcdoc doesn't
  // render new code (with viz[N] refs) against stale visualization data.
  dataReady.value = false;
  await fetchArtifactsList();
  // Only adopt the newly-created artifact if it survives this frame's mode filter
  // (e.g. the Dash frame ignores a slides artifact, and vice-versa).
  if (artifactId && artifactsList.value.some(a => a.id === artifactId)) {
    selectedArtifactId.value = artifactId;
    // Force refetch in case same artifact transitioned from pending to completed
    await fetchSelectedArtifact();
    // Fetch visualization data for the new artifact before rendering
    await fetchData(artifactId);
  }
}

// Load artifacts and data on mount
onMounted(async () => {
  window.addEventListener('message', handleIframeMessage);
  window.addEventListener('artifact:select', handleArtifactSelect);
  window.addEventListener('artifact:created', handleArtifactCreated);
  document.addEventListener('fullscreenchange', handleFullscreenChange);
  window.addEventListener('keydown', handleFullscreenKeydown);

  // First fetch artifact list to know which artifact is selected
  await fetchArtifactsList();

  // Then fetch visualization data filtered by the selected artifact (if any)
  await fetchData(selectedArtifactId.value);
});

// Narrow a raw artifact list by the optional modeFilter prop.
// No filter (prop undefined) returns the list unchanged → identical to prior behavior.
function applyModeFilter(list: ArtifactItem[]): ArtifactItem[] {
  if (!props.modeFilter) return list;
  return list.filter(a => a.mode === props.modeFilter);
}

// Fetch list of all artifacts for the report
async function fetchArtifactsList() {
  try {
    const { data } = await useMyFetch(`/artifacts/report/${props.reportId}`);
    if (data.value && Array.isArray(data.value)) {
      artifactsList.value = applyModeFilter(data.value as ArtifactItem[]);

      // Auto-select the most recent artifact
      if (artifactsList.value.length > 0) {
        selectedArtifactId.value = artifactsList.value[0].id;
        await fetchSelectedArtifact();
      }
    }
  } catch (e) {
    console.log('[ArtifactFrame] No artifacts found');
  }
}

// Fetch the full artifact content when selection changes
async function fetchSelectedArtifact() {
  if (!selectedArtifactId.value) {
    selectedArtifact.value = null;
    return;
  }

  try {
    const { data } = await useMyFetch(`/api/artifacts/${selectedArtifactId.value}`);
    if (data.value) {
      selectedArtifact.value = data.value;
      console.log('[ArtifactFrame] Loaded artifact:', (data.value as any).title);
      // Broadcast active artifact viz IDs so ToolWidgetPreview can show "Added to Dashboard"
      const vizIds = (data.value as any)?.content?.visualization_ids || [];
      window.dispatchEvent(new CustomEvent('artifact:viz-ids', { detail: { visualization_ids: vizIds } }));
    }
  } catch (e) {
    console.error('[ArtifactFrame] Failed to fetch artifact:', e);
  }
}

// Watch for artifact selection changes - refetch data filtered by new artifact
watch(selectedArtifactId, async (newId, oldId) => {
  iframeError.value = null;
  iframeReady.value = false;
  if (isPolishMode.value) exitPolishMode();
  await fetchSelectedArtifact();
  // Only refetch data if this is a user-initiated change (not initial load)
  if (oldId !== undefined) {
    await fetchData(newId);
  }
});

onUnmounted(() => {
  window.removeEventListener('message', handleIframeMessage);
  window.removeEventListener('artifact:select', handleArtifactSelect);
  window.removeEventListener('artifact:created', handleArtifactCreated);
  document.removeEventListener('fullscreenchange', handleFullscreenChange);
  window.removeEventListener('keydown', handleFullscreenKeydown);
  // Make sure we leave native fullscreen if the component unmounts while expanded.
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
  }
  if (isPolishMode.value) exitPolishMode();
  stopPolling();
});

// Handle messages from iframe
function handleIframeMessage(event: MessageEvent) {
  if (event.data?.type === 'ARTIFACT_READY') {
    console.log('[ArtifactFrame] Iframe ready');
    iframeError.value = null;
    iframeReady.value = true;
    sendDataToIframe();
  } else if (event.data?.type === 'ARTIFACT_ERROR') {
    console.error('[ArtifactFrame] Iframe render error:', event.data.payload?.message);
    iframeError.value = event.data.payload?.message || 'Unknown render error';
  } else if (event.data?.type === 'POLISH_ELEMENT_SELECTED') {
    polishSelectedElement.value = event.data.element;
    polishPromptVisible.value = true;
    polishInstruction.value = '';
    nextTick(() => polishInputRef.value?.focus());
  }
}

// Send data to iframe(s) via postMessage. There can be TWO live iframe
// instances at once: the background one (iframeRef) and the fullscreen overlay
// one (fullscreenIframeRef). Both must receive ARTIFACT_DATA or the one that
// missed it renders its static chrome with empty/blank charts.
function sendDataToIframe() {
  if (!iframeReady.value) return;

  const wins = [iframeRef.value?.contentWindow, fullscreenIframeRef.value?.contentWindow]
    .filter((w): w is Window => !!w);
  if (!wins.length) return;

  const payload = JSON.parse(JSON.stringify({
    report: toRaw(reportData.value),
    visualizations: toRaw(visualizationsData.value)
  }));

  let sent = 0;
  for (const win of wins) {
    try {
      win.postMessage({ type: 'ARTIFACT_DATA', payload }, window.location.origin);
      sent++;
    } catch (err: any) {
      console.error('[ArtifactFrame] Failed to send data to an iframe:', err);
    }
  }
  if (!sent) {
    iframeError.value = 'Failed to send data to dashboard iframe';
    return;
  }

  dataReady.value = true;
  console.log('[ArtifactFrame] Data sent to', sent, 'iframe(s):', visualizationsData.value.length, 'visualizations');
}

// Fullscreen overlay iframe finished loading its srcdoc. Its inner script also
// posts ARTIFACT_READY, but push data here too as a belt-and-suspenders so the
// fullscreen deck never shows blank charts if the message ordering races.
function onFullscreenIframeLoad() {
  if (iframeReady.value) sendDataToIframe();
}

// Fetch visualization data for the report (optionally filtered by artifact)
async function fetchData(artifactId?: string) {
  isLoading.value = true;
  dataReady.value = false;

  try {
    // Fetch report info
    let reportDataSources: any[] = [];
    const { data: reportRes } = await useMyFetch(`/api/reports/${props.reportId}`);
    if (reportRes.value) {
      reportData.value = {
        id: (reportRes.value as any).id,
        title: (reportRes.value as any).title,
        theme: (reportRes.value as any).theme_name || (reportRes.value as any).report_theme_name
      };
      reportDataSources = (reportRes.value as any).data_sources || [];
    }
    // If the report uses a single data source, surface its name on every viz.
    const singleDataSourceName = reportDataSources.length === 1
      ? (reportDataSources[0]?.name || reportDataSources[0]?.title || null)
      : null;

    // Fetch queries with visualizations - filter by artifact_id if provided
    const queryParams = artifactId ? `?report_id=${props.reportId}&artifact_id=${artifactId}` : `?report_id=${props.reportId}`;
    const { data: queriesRes } = await useMyFetch(`/api/queries${queryParams}`);
    const queries = Array.isArray(queriesRes.value) ? queriesRes.value : [];

    // Build visualization data array
    const vizData: any[] = [];

    for (const query of queries) {
      // Fetch default step for this query
      const { data: stepRes } = await useMyFetch(`/api/queries/${query.id}/default_step`);
      const step = (stepRes.value as any)?.step;

      // Process each visualization in the query
      for (const viz of query.visualizations || []) {
        vizData.push({
          id: viz.id,
          title: viz.title || query.title || 'Untitled',
          view: viz.view || {},
          rows: step?.data?.rows || [],
          columns: step?.data?.columns || [],
          dataModel: step?.data_model || {},
          stepStatus: step?.status,
          // Provenance surfaced in the built-in InfoPopover on prebuilt comps
          code: step?.code || '',
          description: viz.description || query.description || step?.description || '',
          dataSource: singleDataSourceName,
        });
      }
    }

    // Reorder vizData to match artifact's visualization_ids order
    // (artifact code references viz[0], viz[1], etc. by index)
    const vizIds = selectedArtifact.value?.content?.visualization_ids;
    if (vizIds && vizIds.length > 0) {
      const vizMap = new Map(vizData.map(v => [v.id, v]));
      const ordered = vizIds.map((id: string) => vizMap.get(id)).filter(Boolean);
      // Append any extras not in visualization_ids
      const orderedIds = new Set(vizIds);
      for (const v of vizData) {
        if (!orderedIds.has(v.id)) ordered.push(v);
      }
      visualizationsData.value = ordered;
    } else {
      visualizationsData.value = vizData;
    }
    console.log('[ArtifactFrame] Fetched', visualizationsData.value.length, 'visualizations');

    // Mark data as ready - triggers iframeSrcdoc to compute with loaded data
    dataReady.value = true;

  } catch (e) {
    console.error('[ArtifactFrame] Failed to fetch data:', e);
  } finally {
    isLoading.value = false;
    if (iframeReady.value) {
      sendDataToIframe();
    }
  }
}

// Refresh everything
async function refreshAll() {
  await fetchArtifactsList();
  await fetchData(selectedArtifactId.value);
}

// Called when iframe loads
function onIframeLoad() {
  // Iframe loaded, but we wait for ARTIFACT_READY message
}

// Sample React code for when no artifact exists
const sampleArtifactCode = computed(() => {
  const SC = '</' + 'script>';
  return `
<script type="text/babel">
// Default Artifact - Create one with the agent!
function App() {
  const data = useArtifactData();

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  const { report, visualizations } = data;

  return (
    <div className="min-h-full bg-gradient-to-br from-slate-50 to-slate-100 p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 tracking-tight">
          {report?.title || 'Dashboard'}
        </h1>
        <p className="text-sm text-gray-500 mt-2">
          {visualizations.length} visualization{visualizations.length !== 1 ? 's' : ''} available
        </p>
      </div>

      {/* Empty state */}
      {visualizations.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-1">No visualizations yet</h3>
          <p className="text-sm text-gray-500 max-w-sm">
            Ask the agent to create visualizations, then generate an artifact to see them here.
          </p>
        </div>
      ) : (
        /* Grid of visualizations */
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {visualizations.map((viz) => (
            <VisualizationCard key={viz.id} viz={viz} />
          ))}
        </div>
      )}
    </div>
  );
}

function VisualizationCard({ viz }) {
  const chartRef = React.useRef(null);
  const chartInstance = React.useRef(null);

  React.useEffect(() => {
    if (!chartRef.current || !viz.rows?.length) return;

    if (chartInstance.current) {
      chartInstance.current.dispose();
    }

    const chart = echarts.init(chartRef.current);
    chartInstance.current = chart;

    const options = buildChartOptions(viz);
    if (options) {
      chart.setOption(options);
    }

    const resizeHandler = () => chart.resize();
    window.addEventListener('resize', resizeHandler);

    return () => {
      window.removeEventListener('resize', resizeHandler);
      chart.dispose();
    };
  }, [viz]);

  const viewType = viz.view?.view?.type || viz.view?.type || viz.dataModel?.type || 'table';

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden hover:shadow-md transition-shadow">
      <div className="px-5 py-4 border-b border-gray-50">
        <h3 className="font-semibold text-gray-900">{viz.title}</h3>
        <span className="text-xs text-gray-400 uppercase tracking-wide">{viewType}</span>
      </div>
      <div className="p-5">
        {viz.rows?.length > 0 ? (
          viewType === 'table' ? (
            <TableView data={viz} />
          ) : (
            <div ref={chartRef} className="h-72 w-full" />
          )
        ) : (
          <div className="h-72 flex items-center justify-center text-gray-400">
            No data available
          </div>
        )}
      </div>
      <div className="px-5 py-3 bg-gray-50/50 text-xs text-gray-500">
        {viz.rows?.length || 0} rows
      </div>
    </div>
  );
}

function TableView({ data }) {
  const { rows, columns } = data;
  const cols = columns?.length
    ? columns.map(c => c.field || c.colId || c.headerName)
    : Object.keys(rows[0] || {});

  return (
    <div className="overflow-x-auto max-h-72 rounded-lg border border-gray-100">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 sticky top-0">
          <tr>
            {cols.slice(0, 6).map((col) => (
              <th key={col} className="text-left px-3 py-2 font-medium text-gray-600 border-b border-gray-100">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 10).map((row, i) => (
            <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50">
              {cols.slice(0, 6).map((col) => (
                <td key={col} className="px-3 py-2 text-gray-700">
                  {formatValue(row[col] ?? row[col.toLowerCase()])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 10 && (
        <div className="text-xs text-gray-400 p-2 text-center bg-gray-50">
          Showing 10 of {rows.length} rows
        </div>
      )}
    </div>
  );
}

function formatValue(val) {
  if (val === null || val === undefined) return '-';
  if (typeof val === 'number') return val.toLocaleString();
  return String(val);
}

function buildChartOptions(viz) {
  const { rows, view, dataModel } = viz;
  if (!rows?.length) return null;

  const type = (view?.view?.type || view?.type || dataModel?.type || '').toLowerCase();
  const colors = view?.view?.palette?.colors || ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

  const normalizedRows = rows.map(r => {
    const o = {};
    Object.keys(r).forEach(k => o[k.toLowerCase()] = r[k]);
    return o;
  });

  const series = dataModel?.series?.[0] || {};
  const categoryKey = (view?.view?.x || series.key || Object.keys(normalizedRows[0])[0])?.toLowerCase();
  const valueKey = (view?.view?.y || series.value || Object.keys(normalizedRows[0])[1])?.toLowerCase();

  if (!categoryKey) return null;

  const categories = [...new Set(normalizedRows.map(r => String(r[categoryKey] || '')))];
  const values = categories.map(cat => {
    const row = normalizedRows.find(r => String(r[categoryKey]) === cat);
    const v = row ? Number(row[valueKey]) : 0;
    return isNaN(v) ? 0 : v;
  });

  if (type === 'pie_chart' || type === 'pie') {
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      series: [{
        type: 'pie',
        radius: ['45%', '75%'],
        center: ['50%', '50%'],
        data: categories.map((name, i) => ({
          name,
          value: values[i],
          itemStyle: { color: colors[i % colors.length] }
        })),
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } }
      }]
    };
  }

  if (type === 'bar_chart' || type === 'bar' || !type || type === 'table') {
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 50, right: 20, bottom: 50, top: 20, containLabel: true },
      xAxis: {
        type: 'category',
        data: categories,
        axisLabel: { rotate: categories.length > 6 ? 45 : 0, fontSize: 11, color: '#6b7280' },
        axisLine: { lineStyle: { color: '#e5e7eb' } }
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        splitLine: { lineStyle: { color: '#f3f4f6' } }
      },
      series: [{
        type: 'bar',
        data: values,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: colors[0] },
            { offset: 1, color: colors[0] + '80' }
          ]),
          borderRadius: [6, 6, 0, 0]
        },
        barMaxWidth: 50
      }]
    };
  }

  if (type === 'line_chart' || type === 'line' || type === 'area_chart' || type === 'area') {
    const isArea = type.includes('area');
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, bottom: 50, top: 20, containLabel: true },
      xAxis: {
        type: 'category',
        data: categories,
        axisLabel: { rotate: categories.length > 6 ? 45 : 0, fontSize: 11, color: '#6b7280' },
        axisLine: { lineStyle: { color: '#e5e7eb' } }
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        splitLine: { lineStyle: { color: '#f3f4f6' } }
      },
      series: [{
        type: 'line',
        data: values,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: colors[0] },
        lineStyle: { width: 3 },
        areaStyle: isArea ? {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: colors[0] + '40' },
            { offset: 1, color: colors[0] + '05' }
          ])
        } : undefined
      }]
    };
  }

  return null;
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
${SC}
`;
});

// Build the full iframe srcdoc with embedded data
// Guard: only compute once ALL data is ready to prevent iframe loading with empty data
const iframeSrcdoc = computed(() => {
  // Wait for visualization data to be loaded
  if (!dataReady.value) return undefined;

  // If artifacts exist, wait for the selected artifact to be fully loaded
  if (artifactsList.value.length > 0 && !selectedArtifact.value?.content?.code) return undefined;

  // Priority: props > selected artifact from DB > sample code
  const artifactCode = props.artifactCode
    || selectedArtifact.value?.content?.code
    || sampleArtifactCode.value;

  return buildArtifactIframeHtml({
    data: {
      report: reportData.value,
      visualizations: visualizationsData.value,
    },
    code: artifactCode,
    mode: selectedArtifact.value?.mode || 'page',
    polishMode: true,
    loadingLabel: t('artifactFrame.loadingArtifact'),
    reactBuild: 'development',
  });
});

// Re-send data when it changes
watch([visualizationsData, iframeReady], () => {
  if (iframeReady.value && visualizationsData.value.length > 0) {
    sendDataToIframe();
  }
});
</script>
