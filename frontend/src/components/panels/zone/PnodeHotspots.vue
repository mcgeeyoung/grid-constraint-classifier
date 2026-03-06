<template>
  <div v-if="hotspots.length > 0" class="mb-3">
    <v-divider class="mb-2" />
    <h4 class="text-subtitle-2 mb-2">Pnode Hotspots ({{ hotspots.length }})</h4>

    <div
      v-for="p in hotspots.slice(0, 5)"
      :key="p.node_id_external"
      class="d-flex align-center justify-space-between mb-1 pa-1 rounded"
      style="border: 1px solid var(--border-subtle);"
    >
      <span class="text-body-2">{{ p.node_name || p.node_id_external }}</span>
      <div class="d-flex align-center ga-2">
        <div style="width: 40px; height: 6px; border-radius: 3px; background: var(--bg-surface-3); overflow: hidden;">
          <div
            :style="{
              width: (p.severity_score * 100) + '%',
              height: '100%',
              background: severityBarColor(p.severity_score),
              borderRadius: '3px',
            }"
          />
        </div>
        <span class="text-caption">{{ p.severity_score.toFixed(2) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PnodeScore } from '@/types/constraints'
import { severityBarColor } from '@/utils/tierColors'

defineProps<{
  hotspots: PnodeScore[]
}>()
</script>
