<template>
  <div>
    <h3 class="text-h6 mb-3">Grid Constraint Explorer</h3>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <template v-if="!loading">
      <div class="text-subtitle-2 mb-2">Select an ISO</div>
      <v-card
        v-for="iso in isosWithZones"
        :key="iso.iso_code"
        variant="outlined"
        class="pa-3 mb-2"
        style="cursor: pointer;"
        @click="onSelectISO(iso.iso_code)"
      >
        <div class="d-flex align-center justify-space-between">
          <v-chip size="small" color="primary" variant="flat">
            {{ iso.iso_code.toUpperCase() }}
          </v-chip>
        </div>
        <div class="text-caption mt-1" style="color: var(--text-secondary);">
          {{ iso.iso_name }}
        </div>
      </v-card>

      <div v-if="isosWithZones.length === 0" class="text-center pa-4" style="color: var(--text-secondary);">
        No ISOs with constraint data found.
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { listISOs } from '@/api/constraints'
import { useGridDataStore } from '@/stores/gridDataStore'
import type { ISO } from '@/types/constraints'

const gridStore = useGridDataStore()
const allISOs = ref<ISO[]>([])
const loading = ref(true)

const isosWithZones = computed(() =>
  allISOs.value.filter(iso => iso.is_rto && iso.iso_code === iso.iso_code.toLowerCase()),
)

onMounted(async () => {
  try {
    allISOs.value = await listISOs()
  } finally {
    loading.value = false
  }
})

function onSelectISO(isoCode: string) {
  gridStore.selectISO(isoCode)
}
</script>
