<template>
  <!-- Scrim -->
  <Teleport to="body">
    <Transition name="scrim-fade">
      <div
        v-if="open"
        class="scrim"
        @click.self="emit('close')"
      >
        <!-- Modal panel -->
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="idp-modal-title">
          <!-- Header -->
          <div class="mhead">
            <span id="idp-modal-title" class="mhead-title serif">Add a sign-in provider</span>
            <button class="close-btn" type="button" aria-label="Close" @click="emit('close')">✕</button>
          </div>

          <!-- Search -->
          <div class="search-wrap">
            <input
              v-model="query"
              class="search-input"
              placeholder="Search providers…"
              type="search"
              autocomplete="off"
            />
          </div>

          <!-- Catalog -->
          <div class="lib-body">
            <div class="lib-lbl">POPULAR</div>
            <div class="grid">
              <button
                v-for="tpl in filtered"
                :key="tpl.key"
                type="button"
                class="pcard"
                @click="selectTemplate(tpl)"
              >
                <div class="pcard-logo" v-html="idpLogoSvg(tpl.logo)" />
                <div class="pcard-name">{{ tpl.name }}</div>
                <div class="pcard-type">{{ tpl.type }}</div>
              </button>
            </div>

            <div v-if="filtered.length === 0" class="no-results">
              No providers match "<strong>{{ query }}</strong>"
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { idpLogoSvg } from '~/utils/idpLogos'
import { IDP_TEMPLATES, type IdpTemplate } from '~/utils/idpTemplates'

// ---- Props & emits ----
const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', template: IdpTemplate): void
}>()

// ---- State ----
const query = ref('')

// Reset search when modal opens
watch(
  () => props.open,
  (v) => {
    if (v) query.value = ''
  }
)

// ---- Computed ----
const filtered = computed<IdpTemplate[]>(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return IDP_TEMPLATES
  return IDP_TEMPLATES.filter(
    (t) => t.name.toLowerCase().includes(q) || t.type.toLowerCase().includes(q) || t.key.toLowerCase().includes(q)
  )
})

// ---- Handlers ----
function selectTemplate(tpl: IdpTemplate) {
  emit('select', tpl)
  emit('close')
}
</script>

<style scoped>
/* ---- scrim ---- */
.scrim {
  position: fixed;
  inset: 0;
  background: rgba(26, 22, 17, 0.42);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 40;
}

/* ---- modal panel ---- */
.modal {
  width: 700px;
  max-width: 94vw;
  max-height: 90vh;
  background: #fff;
  border-radius: 18px;
  border: 1px solid #E9E0D3;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.25);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ---- header ---- */
.mhead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid #E9E0D3;
  flex: none;
}

.mhead-title {
  font-size: 17px;
  font-weight: 600;
  color: #1f2328;
  font-family: 'Spectral', ui-serif, Georgia, serif;
}

.serif {
  font-family: 'Spectral', ui-serif, Georgia, serif;
}

.close-btn {
  width: 30px;
  height: 30px;
  border: none;
  background: none;
  color: #9a958c;
  cursor: pointer;
  font-size: 18px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  transition: background 0.12s, color 0.12s;
}

.close-btn:hover {
  background: #F4EEE5;
  color: #1f2328;
}

/* ---- search ---- */
.search-wrap {
  padding: 16px 22px 0;
  flex: none;
}

.search-input {
  width: 100%;
  border: 1px solid #E9E0D3;
  border-radius: 11px;
  padding: 10px 14px;
  font-size: 13px;
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
  color: #1f2328;
  background: #fff;
  outline: none;
  transition: border-color 0.15s;
}

.search-input:focus {
  border-color: #C2541E;
}

/* ---- scrollable body ---- */
.lib-body {
  overflow-y: auto;
  flex: 1;
  padding-bottom: 22px;
}

/* ---- section label ---- */
.lib-lbl {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.07em;
  color: #9a958c;
  padding: 12px 22px 8px;
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
}

/* ---- provider grid ---- */
.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 0 22px;
}

@media (min-width: 480px) {
  .grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (min-width: 640px) {
  .grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

/* ---- provider card ---- */
.pcard {
  border: 1px solid #E9E0D3;
  border-radius: 13px;
  padding: 14px 10px;
  text-align: center;
  cursor: pointer;
  background: #fff;
  transition: border-color 0.14s, box-shadow 0.14s, transform 0.14s;
  /* reset button defaults */
  appearance: none;
  -webkit-appearance: none;
  font: inherit;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.pcard:hover {
  border-color: #C2541E;
  box-shadow: 0 4px 14px rgba(194, 84, 30, 0.12);
  transform: translateY(-1px);
}

.pcard-logo {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #E9E0D3;
  margin: 0 auto 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 7px;
  overflow: hidden;
}

.pcard-name {
  font-size: 12.5px;
  font-weight: 600;
  color: #1f2328;
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
}

.pcard-type {
  font-size: 10.5px;
  color: #9a958c;
  margin-top: 1px;
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
}

/* ---- empty state ---- */
.no-results {
  padding: 24px 22px;
  font-size: 13px;
  color: #9a958c;
  text-align: center;
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
}

/* ---- transition ---- */
.scrim-fade-enter-active,
.scrim-fade-leave-active {
  transition: opacity 0.18s ease;
}

.scrim-fade-enter-from,
.scrim-fade-leave-to {
  opacity: 0;
}
</style>
