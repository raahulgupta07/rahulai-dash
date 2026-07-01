<template>
  <div class="bg-[#F6F1EA] min-h-full">
    <div class="mx-auto max-w-5xl px-4 md:px-8 py-6 text-sm text-[#1f2328]">

      <!-- Header -->
      <div class="mb-5">
        <h1
          class="text-[32px] font-medium text-[#211B14] tracking-tight"
          style="font-family: 'Spectral', ui-serif, Georgia, serif"
        >Available Connectors</h1>
        <p class="mt-1 max-w-[560px] text-xs text-[#6b6b6b] leading-relaxed">
          Connect a shared source with your own account. Only the data your account can access is synced — privately to you.
        </p>
      </div>

      <!-- Loading skeleton -->
      <div v-if="loading" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div
          v-for="n in 4"
          :key="n"
          class="rounded-xl border border-[#E9E0D3] bg-white p-5 animate-pulse"
        >
          <div class="h-4 w-1/2 rounded bg-[#ECE7E0]"></div>
          <div class="mt-3 h-3 w-3/4 rounded bg-[#F1ECE3]"></div>
          <div class="mt-2 h-3 w-2/3 rounded bg-[#F1ECE3]"></div>
          <div class="mt-4 h-8 w-40 rounded-lg bg-[#F1ECE3]"></div>
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-else-if="templates.length === 0"
        class="rounded-xl border border-dashed border-[#E9E0D3] bg-white px-6 py-14 text-center"
      >
        <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[#FBEFE4] text-[#C2541E]">
          <UIcon name="heroicons-link" class="h-6 w-6" />
        </div>
        <p class="text-sm font-medium text-[#211B14]">No connectors available yet</p>
        <p class="mt-1 text-xs text-[#6b6b6b]">An admin needs to publish one before you can connect.</p>
      </div>

      <!-- Cards -->
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div
          v-for="tpl in templates"
          :key="tpl.id"
          class="flex flex-col rounded-xl border border-[#E9E0D3] bg-white p-5 transition hover:border-[#C2541E]"
        >
          <div class="flex items-start justify-between gap-2">
            <h3 class="text-[15px] font-semibold text-[#211B14] truncate">{{ tpl.name }}</h3>
            <span
              v-if="tpl.type"
              class="shrink-0 inline-flex items-center rounded-full bg-[#FBEFE4] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#C2541E]"
            >{{ tpl.type }}</span>
          </div>
          <p class="mt-1 flex-1 text-xs text-[#6b6b6b] leading-relaxed">
            {{ tpl.description || 'Connect this source with your own account.' }}
          </p>
          <button
            type="button"
            class="mt-4 inline-flex w-max items-center gap-2 rounded-lg bg-[#C2541E] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#A8330F] transition-colors"
            @click="openRegister(tpl)"
          >
            <UIcon name="heroicons-user-plus" class="h-4 w-4" />
            Connect with my account
          </button>
        </div>
      </div>

      <!-- Credentials modal -->
      <ConnectorsRegisterModal
        v-model="showModal"
        :template="activeTemplate"
        @registered="onRegistered"
      />
    </div>
  </div>
</template>

<script lang="ts" setup>
import ConnectorsRegisterModal from '~/components/connectors/ConnectorsRegisterModal.vue'

definePageMeta({ layout: 'default' })

const toast = useToast()
const router = useRouter()

const loading = ref(false)
const templates = ref<any[]>([])
const showModal = ref(false)
const activeTemplate = ref<any | null>(null)

async function loadTemplates() {
  loading.value = true
  try {
    const res = await useMyFetch('/connectors/available', { method: 'GET' })
    if (res.data.value) templates.value = res.data.value as any[]
  } catch (e) {
    console.error('Failed to load available connectors:', e)
  } finally {
    loading.value = false
  }
}

function openRegister(tpl: any) {
  activeTemplate.value = tpl
  showModal.value = true
}

function onRegistered(dataSource: any) {
  showModal.value = false
  toast.add({ title: 'Connected — your data is syncing privately.', color: 'green' })
  const id = dataSource?.id
  router.push(id ? `/agents/${id}` : '/agents')
}

onMounted(() => {
  loadTemplates()
})
</script>
