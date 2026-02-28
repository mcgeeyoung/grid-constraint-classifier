<template>
  <div class="d-flex align-center ga-1 mr-2">
    <v-chip
      v-for="iso in isoStore.isos"
      :key="iso.iso_code"
      :color="isoStore.selectedISOs.includes(iso.iso_code) ? 'primary' : undefined"
      :variant="isoStore.selectedISOs.includes(iso.iso_code) ? 'flat' : 'outlined'"
      size="small"
      @click="onClick(iso.iso_code, $event)"
    >
      {{ iso.iso_code.toUpperCase() }}
    </v-chip>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useIsoStore } from '@/stores/isoStore'

const isoStore = useIsoStore()

onMounted(() => {
  if (isoStore.isos.length === 0) {
    isoStore.loadISOs()
  }
})

function onClick(isoCode: string, event: MouseEvent | KeyboardEvent) {
  if ('metaKey' in event && (event.metaKey || event.ctrlKey)) {
    // Multi-select: Cmd/Ctrl+click toggles individual ISO
    isoStore.toggleISO(isoCode)
  } else {
    // Single click: exclusive select
    isoStore.selectISO(isoCode)
  }
}
</script>
