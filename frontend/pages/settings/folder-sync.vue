<template>
  <FolderSyncPanel />
</template>

<script setup lang="ts">
import FolderSyncPanel from '~/components/sync/FolderSyncPanel.vue'

definePageMeta({
  layout: 'settings',
  auth: true,
})
</script>
