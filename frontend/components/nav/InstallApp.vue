<template>
  <!-- Only shows when the browser fired beforeinstallprompt AND not already installed.
       Browsers forbid silent auto-install — this is the one-click install entry point. -->
  <button
    v-if="canInstall"
    type="button"
    @click="install"
    :disabled="installing"
    class="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[12px] font-medium text-[#C2683F] border border-[#E8C9B5] bg-[#FBF4EF] hover:bg-[#F4E5DA] disabled:opacity-50 transition-colors shrink-0"
    title="Install CityAgent as a desktop app"
  >
    <UIcon name="i-heroicons-arrow-down-tray" class="w-4 h-4" />
    <span>{{ installing ? 'Installing…' : 'Install app' }}</span>
  </button>
</template>

<script setup lang="ts">
const canInstall = ref(false)
const installing = ref(false)
let deferred: any = null

function isStandalone(): boolean {
  try {
    return (
      window.matchMedia?.('(display-mode: standalone)')?.matches ||
      // iOS Safari
      (window.navigator as any)?.standalone === true
    )
  } catch {
    return false
  }
}

function onBeforeInstall(e: Event) {
  // Stop Chrome's mini-infobar; keep the event so we can prompt on our button.
  e.preventDefault()
  deferred = e
  if (!isStandalone()) canInstall.value = true
}

function onInstalled() {
  canInstall.value = false
  deferred = null
  try { localStorage.setItem('pwa_installed', '1') } catch {}
}

async function install() {
  if (!deferred || installing.value) return
  installing.value = true
  try {
    deferred.prompt()
    await deferred.userChoice
  } catch {
    // user dismissed or prompt unavailable — just hide quietly
  } finally {
    installing.value = false
    canInstall.value = false
    deferred = null
  }
}

onMounted(() => {
  if (isStandalone()) return
  window.addEventListener('beforeinstallprompt', onBeforeInstall)
  window.addEventListener('appinstalled', onInstalled)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeinstallprompt', onBeforeInstall)
  window.removeEventListener('appinstalled', onInstalled)
})
</script>
