<template>
  <div v-if="topBAs.length > 0" class="mb-3">
    <v-divider class="mb-2" />
    <h4 class="text-subtitle-2 mb-2">BA Congestion</h4>

    <div
      v-for="ba in topBAs"
      :key="ba.ba_code"
      class="d-flex align-center justify-space-between mb-1 pa-1 rounded"
      style="border: 1px solid var(--border-subtle); cursor: pointer;"
      @click="selectionStore.selectBA(ba.ba_code)"
    >
      <span class="text-body-2">{{ ba.ba_name || ba.ba_code }}</span>
      <span class="text-caption">
        {{ (gridStore.scoresByBA.get(ba.ba_code)?.congestion_opportunity_score ?? 0).toFixed(2) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useGridDataStore } from '@/stores/gridDataStore'
import { useSelectionStore } from '@/stores/selectionStore'

const gridStore = useGridDataStore()
const selectionStore = useSelectionStore()

const topBAs = computed(() => {
  const scored = gridStore.mappableBAs
    .filter(ba => gridStore.scoresByBA.has(ba.ba_code))
    .sort((a, b) => {
      const sa = gridStore.scoresByBA.get(a.ba_code)?.congestion_opportunity_score ?? 0
      const sb = gridStore.scoresByBA.get(b.ba_code)?.congestion_opportunity_score ?? 0
      return sb - sa
    })
  return scored.slice(0, 3)
})
</script>
