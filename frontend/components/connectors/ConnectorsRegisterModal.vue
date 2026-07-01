<template>
  <div
    v-if="modelValue && template"
    class="fixed inset-0 z-[80] flex items-center justify-center bg-black/40 p-4"
    @click.self="close"
  >
    <div class="w-full max-w-md rounded-xl border border-[#E9E0D3] bg-white shadow-xl">
      <!-- Header -->
      <div class="flex items-start justify-between gap-3 border-b border-[#E9E0D3] px-5 py-4">
        <div class="min-w-0">
          <h2
            class="text-lg font-semibold text-[#211B14] truncate"
            style="font-family: 'Spectral', ui-serif, Georgia, serif"
          >Connect “{{ template.name }}”</h2>
          <p class="mt-0.5 text-[11px] text-[#6b6b6b] leading-relaxed">
            Sign in with your own account. Only the data your account can access is synced — privately to you.
          </p>
        </div>
        <button
          type="button"
          class="shrink-0 text-[#9a958c] hover:text-[#211B14]"
          :disabled="submitting"
          @click="close"
        >
          <UIcon name="heroicons-x-mark" class="h-5 w-5" />
        </button>
      </div>

      <!-- Body -->
      <form class="px-5 py-4 space-y-3" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Email</label>
          <input
            v-model="email"
            type="email"
            autocomplete="username"
            placeholder="you@company.com"
            :disabled="submitting"
            class="block w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-[#C2541E] focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Password</label>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="••••••••"
            :disabled="submitting"
            class="block w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-[#C2541E] focus:outline-none"
          />
        </div>

        <p v-if="isPowerBiUser" class="text-[11px] text-[#8a6d3b] bg-[#FBF3E2] border border-[#ECDCBB] rounded-md px-2.5 py-2 leading-relaxed">
          If your Power BI account uses multi-factor authentication, email + password may not be enough — a device-code sign-in option is available after connecting.
        </p>

        <!-- Error -->
        <p v-if="errorMessage" class="text-[12px] text-red-600 bg-red-50 border border-red-200 rounded-md px-2.5 py-2">
          {{ errorMessage }}
        </p>

        <!-- Actions -->
        <div class="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            class="rounded-lg px-3 py-1.5 text-sm text-[#6b6b6b] hover:text-[#211B14]"
            :disabled="submitting"
            @click="close"
          >Cancel</button>
          <button
            type="submit"
            class="inline-flex items-center gap-2 rounded-lg bg-[#C2541E] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#A8330F] transition-colors disabled:opacity-60"
            :disabled="submitting || !canSubmit"
          >
            <Spinner v-if="submitting" class="h-4 w-4 animate-spin" />
            {{ submitting ? 'Connecting & syncing your data…' : 'Connect with my account' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script lang="ts" setup>
import Spinner from '~/components/Spinner.vue'

const props = defineProps<{
  modelValue: boolean
  template: any | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'registered', dataSource: any): void
}>()

const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')

const isPowerBiUser = computed(() => props.template?.type === 'powerbi_user')

// auth_mode: powerbi_user signs in with userpass; otherwise fall back to the
// template's first allowed user auth mode.
const authMode = computed<string>(() => {
  if (isPowerBiUser.value) return 'userpass'
  return props.template?.allowed_user_auth_modes?.[0] || 'userpass'
})

const canSubmit = computed(() => !!email.value.trim() && !!password.value)

// Reset the form whenever a new template is opened.
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      email.value = ''
      password.value = ''
      errorMessage.value = ''
      submitting.value = false
    }
  }
)

function close() {
  if (submitting.value) return
  emit('update:modelValue', false)
}

async function submit() {
  if (submitting.value || !canSubmit.value || !props.template?.id) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const body = {
      auth_mode: authMode.value,
      credentials: {
        username: email.value.trim(),
        password: password.value,
      } as Record<string, string>,
    }
    const res = await useMyFetch(`/connectors/${props.template.id}/register`, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'Content-Type': 'application/json' },
    })
    if ((res.error as any)?.value) {
      errorMessage.value =
        (res.error as any).value?.data?.detail || 'Failed to connect. Please check your credentials.'
      return
    }
    const dataSource = (res.data as any)?.value
    emit('registered', dataSource)
  } catch (e: any) {
    errorMessage.value = e?.data?.detail || e?.message || 'Failed to connect. Please check your credentials.'
  } finally {
    submitting.value = false
  }
}
</script>
