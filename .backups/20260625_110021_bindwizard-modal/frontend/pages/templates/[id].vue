<template>
  <div class="flex justify-center px-4 md:px-6 text-sm bg-[#FBFAF6] min-h-full">
    <div class="w-full max-w-4xl py-2">
      <!-- Back -->
      <NuxtLink
        to="/templates"
        class="inline-flex items-center gap-1.5 text-xs font-medium text-[#9a958c] hover:text-[#1f2328] transition-colors cursor-pointer mb-4"
      >
        <UIcon name="i-heroicons-arrow-left" class="w-4 h-4" />
        Templates
      </NuxtLink>

      <!-- Loading -->
      <div
        v-if="loading"
        class="rounded-2xl border border-[#E7E5DD] bg-white px-6 py-12 text-center text-sm text-[#6b6b6b]"
      >Loading…</div>

      <!-- Not found -->
      <div
        v-else-if="!tpl"
        class="text-center py-14 px-6 bg-white border border-[#E7E5DD] rounded-2xl"
      >
        <div class="w-11 h-11 rounded-xl bg-[#F4F1EA] border border-[#E7E5DD] mx-auto flex items-center justify-center mb-3">
          <UIcon name="i-heroicons-exclamation-triangle" class="w-6 h-6 text-[#9a958c]" />
        </div>
        <p class="text-sm font-medium text-[#1f2328]" style="font-family: ui-serif, Georgia, serif">
          Template not available
        </p>
        <p class="text-xs text-[#9a958c] mt-1">It may have been removed or is not in your scope.</p>
      </div>

      <template v-else>
        <!-- Header -->
        <div class="rounded-2xl border border-[#E8C9B5] bg-[#F6EFEA] p-5 mb-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-xl bg-white border border-[#E8C9B5] text-[#A8542F] flex items-center justify-center flex-none">
              <UIcon name="i-heroicons-square-3-stack-3d" class="w-7 h-7" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 flex-wrap">
                <h1
                  class="text-2xl font-semibold tracking-tight text-[#1f2328]"
                  style="font-family: ui-serif, Georgia, 'Times New Roman', serif"
                >{{ tpl.name }}</h1>
                <span
                  v-if="tpl.version"
                  class="font-mono text-[11px] text-[#A8542F] bg-white border border-[#E8C9B5] rounded-md px-1.5 py-0.5"
                >v{{ tpl.version }}</span>
                <span
                  v-if="tpl.status"
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium"
                  :class="tpl.status === 'published'
                    ? 'bg-[#eef6f0] text-[#3f9e6a] border border-[#d7ebde]'
                    : 'bg-[#F4F1EA] text-[#9a958c] border border-[#E7E5DD]'"
                >{{ tpl.status }}</span>
              </div>
              <p class="mt-2 text-[#6b6b6b] leading-relaxed max-w-2xl">
                {{ tpl.description || 'No description.' }}
              </p>
              <div class="mt-2 flex items-center gap-2 text-xs text-[#9a958c]">
                <span>by {{ tpl.author || 'Unknown' }}</span>
                <span v-if="tpl.scope" class="text-[#cfcabf]">·</span>
                <span v-if="tpl.scope">{{ tpl.scope }} scope</span>
              </div>
              <!-- Domain tags -->
              <div v-if="tpl.domain_tags && tpl.domain_tags.length" class="mt-3 flex flex-wrap gap-1.5">
                <span
                  v-for="tag in tpl.domain_tags"
                  :key="tag"
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-white text-[#6b6b6b] border border-[#E7E5DD]"
                >{{ tag }}</span>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="mt-4 flex items-center gap-2.5">
            <button
              type="button"
              class="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-xl bg-[#C2683F] text-white hover:bg-[#A8542F] transition-colors cursor-pointer"
              @click="wizardOpen = true"
            >
              <UIcon name="i-heroicons-sparkles" class="w-4 h-4" />
              Use template
            </button>
            <button
              v-if="tpl.status === 'draft'"
              type="button"
              :disabled="publishing"
              class="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border border-[#E7E5DD] text-[#1f2328] bg-white hover:bg-[#F4F1EA] transition-colors cursor-pointer"
              :class="publishing ? 'opacity-65 cursor-default' : ''"
              @click="publish"
            >
              <UIcon name="i-heroicons-globe-alt" class="w-4 h-4" />
              {{ publishing ? 'Publishing…' : 'Publish' }}
            </button>
            <span v-if="publishErr" class="text-xs text-red-600">{{ publishErr }}</span>
          </div>
        </div>

        <!-- Requires (binding contract) -->
        <div v-if="requiresColumns.length" class="bg-white border border-[#E7E5DD] rounded-2xl p-5 mb-6">
          <h2
            class="text-[15px] font-semibold text-[#1f2328] mb-1"
            style="font-family: ui-serif, Georgia, serif"
          >Requires</h2>
          <p class="text-xs text-[#9a958c] mb-3">
            Map each role to one of your own columns when you bind the template.
          </p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="(rc, i) in requiresColumns"
              :key="i"
              class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[12px] bg-[#F3E7DF] border border-[#E8C9B5]"
            >
              <span class="font-mono font-medium text-[#A8542F]">{{ rc.role }}</span>
              <UIcon name="i-heroicons-arrow-long-right" class="w-3.5 h-3.5 text-[#9a958c]" />
              <span class="font-mono text-[#6b6b6b]">{{ rc.as }}</span>
            </span>
          </div>
        </div>

        <!-- Example questions -->
        <div
          v-if="exampleQuestions.length"
          class="bg-white border border-[#E7E5DD] rounded-2xl p-5 mb-6"
        >
          <h2
            class="text-[15px] font-semibold text-[#1f2328] mb-3"
            style="font-family: ui-serif, Georgia, serif"
          >Example questions</h2>
          <ul class="space-y-2">
            <li
              v-for="(qn, i) in exampleQuestions"
              :key="i"
              class="flex items-start gap-2 text-[13px] text-[#444] leading-snug"
            >
              <span class="mt-1.5 w-1 h-1 rounded-full flex-none" style="background:#C2683F" />
              <span>{{ qn }}</span>
            </li>
          </ul>
        </div>

        <!-- Skills used -->
        <div v-if="usesSkills.length" class="bg-white border border-[#E7E5DD] rounded-2xl p-5 mb-6">
          <h2
            class="text-[15px] font-semibold text-[#1f2328] mb-3"
            style="font-family: ui-serif, Georgia, serif"
          >Skills</h2>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="(sk, i) in usesSkills"
              :key="i"
              class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-[#F4F1EA] text-[#6b6b6b] border border-[#E7E5DD]"
            >{{ skillLabel(sk) }}</span>
          </div>
        </div>

        <!-- Body / rules preview -->
        <div v-if="tpl.body_md" class="bg-white border border-[#E7E5DD] rounded-2xl p-5 mb-6">
          <h2
            class="text-[15px] font-semibold text-[#1f2328] mb-3"
            style="font-family: ui-serif, Georgia, serif"
          >Details</h2>
          <pre class="whitespace-pre-wrap text-[13px] text-[#444] leading-relaxed font-sans">{{ tpl.body_md }}</pre>
        </div>
      </template>
    </div>

    <!-- Bind wizard (explicit import — avoids Nuxt path-prefix no-op) -->
    <BindWizard
      v-if="tpl && wizardOpen"
      :template-id="tpl.id"
      :template-name="tpl.name"
      :requires-columns="requiresColumns"
      @close="wizardOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { useMyFetch } from '~/composables/useMyFetch'
import BindWizard from '~/components/templates/BindWizard.vue'

const route = useRoute()
const templateId = computed(() => String(route.params.id || ''))

const tpl = ref<any>(null)
const loading = ref(true)
const wizardOpen = ref(false)
const publishing = ref(false)
const publishErr = ref('')

const requiresColumns = computed<any[]>(() => {
  const m = tpl.value?.manifest || {}
  return Array.isArray(m.requires_columns) ? m.requires_columns : []
})
const exampleQuestions = computed<any[]>(() => {
  const m = tpl.value?.manifest || {}
  return Array.isArray(m.example_questions) ? m.example_questions : []
})
const usesSkills = computed<any[]>(() => {
  const m = tpl.value?.manifest || {}
  return Array.isArray(m.uses_skills) ? m.uses_skills : []
})

function skillLabel(sk: any) {
  if (typeof sk === 'string') return sk
  return sk?.name || sk?.slug || sk?.id || 'skill'
}

async function loadTemplate() {
  loading.value = true
  try {
    const { data, error } = await useMyFetch<any>(
      `/templates/${encodeURIComponent(templateId.value)}`, { method: 'GET' }
    )
    if (error.value) throw error.value
    tpl.value = data.value || null
    if (route.query.use === '1' && tpl.value) wizardOpen.value = true
  } catch {
    tpl.value = null
  } finally {
    loading.value = false
  }
}

async function publish() {
  if (publishing.value || !tpl.value) return
  publishErr.value = ''
  publishing.value = true
  const prevStatus = tpl.value.status
  try {
    const { error } = await useMyFetch(
      `/templates/${encodeURIComponent(tpl.value.id)}/publish`,
      { method: 'POST', body: { scope: tpl.value.scope || 'org' } }
    )
    if (error.value) throw error.value
    tpl.value.status = 'published' // optimistic
  } catch {
    tpl.value.status = prevStatus
    publishErr.value = 'Could not publish (needs manage access).'
  } finally {
    publishing.value = false
  }
}

onMounted(loadTemplate)
</script>
