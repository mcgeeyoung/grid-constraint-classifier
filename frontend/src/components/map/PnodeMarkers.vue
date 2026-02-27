<template>
  <l-circle-marker
    v-for="pnode in visiblePnodes"
    :key="pnode.node_id_external"
    :lat-lng="[pnode.lat!, pnode.lon!]"
    :radius="pnodeRadius(pnode.severity_score)"
    :color="severityColor(pnode.tier)"
    :fill-color="severityColor(pnode.tier)"
    :fill-opacity="0.7"
    :weight="1"
  >
    <l-popup>
      <div style="font-size: 12px; min-width: 160px;">
        <strong>{{ pnode.node_name ?? pnode.node_id_external }}</strong><br />
        Severity: {{ pnode.severity_score.toFixed(2) }}<br />
        Tier: {{ pnode.tier }}<br />
        <span v-if="pnode.avg_congestion != null">Avg Congestion: ${{ pnode.avg_congestion.toFixed(2) }}/MWh<br /></span>
        <span v-if="pnode.max_congestion != null">Max Congestion: ${{ pnode.max_congestion.toFixed(2) }}/MWh<br /></span>
        <span v-if="pnode.congested_hours_pct != null">Congested Hours: {{ (pnode.congested_hours_pct * 100).toFixed(1) }}%</span>
      </div>
    </l-popup>
  </l-circle-marker>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { LCircleMarker, LPopup } from '@vue-leaflet/vue-leaflet'
import { useIsoStore } from '@/stores/isoStore'
import { useMapStore } from '@/stores/mapStore'
import { fetchAllPnodeScores, type PnodeScore } from '@/api/isos'

const isoStore = useIsoStore()
const mapStore = useMapStore()
const pnodes = ref<PnodeScore[]>([])

const visiblePnodes = computed(() => {
  if (mapStore.zoom < 7) return []
  return pnodes.value.filter(p => p.lat != null && p.lon != null)
})

// Load all pnodes when ISO is selected
watch(
  () => isoStore.selectedISO,
  async (iso) => {
    if (!iso) {
      pnodes.value = []
      return
    }
    try {
      pnodes.value = await fetchAllPnodeScores(iso)
    } catch {
      pnodes.value = []
    }
  },
  { immediate: true },
)

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#e74c3c',
  severe: '#e67e22',
  moderate: '#f1c40f',
  low: '#2ecc71',
  minimal: '#27ae60',
}

function severityColor(tier: string): string {
  return SEVERITY_COLORS[tier.toLowerCase()] ?? '#95a5a6'
}

function pnodeRadius(score: number): number {
  return Math.min(3 + score * 3, 12)
}
</script>
