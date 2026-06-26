<template>
  <div class="logo-sec">
    <!-- Header: live preview + headings -->
    <div class="logo-head">
      <div class="logo-prev" v-html="currentSvg" />
      <div>
        <div class="logo-title">Connector logo</div>
        <div class="logo-sub">Pick a brand logo or upload your own (PNG/SVG, ≤300 KB)</div>
      </div>
    </div>

    <!-- Preset grid -->
    <div class="logo-grid">
      <button
        v-for="key in IDP_PRESET_KEYS"
        :key="key"
        type="button"
        class="ltile"
        :class="{ sel: modelValue === key }"
        :title="key"
        v-html="idpLogoSvg(key)"
        @click="selectPreset(key)"
      />

      <!-- Upload tile -->
      <label class="ltile upload" title="Upload custom logo">
        <span class="upload-icon">⤓</span>
        <input
          type="file"
          accept="image/png,image/svg+xml,image/jpeg"
          class="hidden-input"
          @change="onFileChange"
        />
      </label>
    </div>

    <!-- Upload error -->
    <p v-if="uploadError" class="upload-error">{{ uploadError }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { IDP_PRESET_KEYS, IDP_LOGOS, idpLogoSvg } from '~/utils/idpLogos'

// ---- props & emits ----
const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

// ---- state ----
const uploadError = ref<string | null>(null)

// ---- computed ----
const currentSvg = computed(() => idpLogoSvg(props.modelValue))

// ---- handlers ----
function selectPreset(key: string) {
  uploadError.value = null
  emit('update:modelValue', key)
}

function onFileChange(event: Event) {
  uploadError.value = null
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  if (file.size > 300 * 1024) {
    uploadError.value = 'Image too large (max 300 KB)'
    input.value = ''
    return
  }

  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = reader.result as string
    emit('update:modelValue', dataUrl)
  }
  reader.readAsDataURL(file)
  // reset so the same file can be re-selected if needed
  input.value = ''
}
</script>

<style scoped>
/* --- card container --- */
.logo-sec {
  background: #FBF7F1;
  border: 1px solid #ECE3D5;
  border-radius: 13px;
  padding: 14px;
  margin-bottom: 18px;
}

/* --- header row --- */
.logo-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.logo-prev {
  width: 46px;
  height: 46px;
  border-radius: 11px;
  border: 1px solid #E9E0D3;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  overflow: hidden;
  padding: 7px;
}

.logo-title {
  font-size: 12.5px;
  font-weight: 600;
  color: #1f2328;
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
}

.logo-sub {
  font-size: 11px;
  color: #9a958c;
  margin-top: 2px;
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
}

/* --- preset grid --- */
.logo-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* --- individual tile --- */
.ltile {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  border: 1px solid #E9E0D3;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.12s, box-shadow 0.12s;
  position: relative;
  padding: 9px;
  /* reset button defaults */
  appearance: none;
  -webkit-appearance: none;
  line-height: 1;
  font: inherit;
}

.ltile:hover {
  border-color: #C2541E;
}

/* selected state */
.ltile.sel {
  border-color: #C2541E;
  box-shadow: 0 0 0 2px rgba(194, 84, 30, 0.18);
}

/* check badge */
.ltile.sel::after {
  content: "✓";
  position: absolute;
  top: -7px;
  right: -7px;
  width: 16px;
  height: 16px;
  background: #C2541E;
  color: #fff;
  border-radius: 50%;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 16px;
  text-align: center;
  pointer-events: none;
}

/* upload tile */
.ltile.upload {
  border-style: dashed;
  cursor: pointer;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

.upload-icon {
  font-size: 18px;
  color: #9a958c;
  line-height: 1;
}

.hidden-input {
  display: none;
}

/* error message */
.upload-error {
  margin: 8px 0 0;
  font-size: 11.5px;
  color: #b91c1c;
  font-family: 'Hanken Grotesk', system-ui, sans-serif;
}
</style>
