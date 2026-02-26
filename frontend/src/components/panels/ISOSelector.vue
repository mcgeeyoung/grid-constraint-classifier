<template>
  <div class="d-flex align-center ga-1 mr-2">
    <v-chip
      v-for="iso in isoStore.isos"
      :key="iso.iso_code"
      :color="iso.iso_code === isoStore.selectedISO ? 'primary' : undefined"
      :variant="iso.iso_code === isoStore.selectedISO ? 'flat' : 'outlined'"
      size="small"
      @click="isoStore.selectISO(iso.iso_code)"
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
</script>
