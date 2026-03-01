<template>
  <l-circle-marker
    v-for="ba in visibleBAs"
    :key="ba.ba_code"
    :lat-lng="[ba.latitude!, ba.longitude!]"
    :radius="markerRadius(ba.ba_code)"
    :color="congestionColor(ba.ba_code)"
    :fill-color="congestionColor(ba.ba_code)"
    :fill-opacity="0.75"
    :weight="ba.ba_code === store.selectedBACode ? 3 : 1.5"
    @click="onBAClick(ba.ba_code)"
  >
    <l-popup>
      <div style="font-size: 12px; min-width: 180px;">
        <strong>{{ ba.ba_code }}</strong> - {{ ba.ba_name }}<br />
        <template v-if="scoreFor(ba.ba_code)">
          <span class="text-medium-emphasis">Hours importing:</span>
          {{ pctFmt(scoreFor(ba.ba_code)!.pct_hours_importing) }}<br />
          <span class="text-medium-emphasis">Hours > 80%:</span>
          {{ scoreFor(ba.ba_code)!.hours_above_80 ?? '-' }}<br />
          <template v-if="scoreFor(ba.ba_code)!.congestion_opportunity_score != null">
            <span class="text-medium-emphasis">COS:</span>
            ${{ scoreFor(ba.ba_code)!.congestion_opportunity_score!.toFixed(2) }}/kW
          </template>
        </template>
        <template v-else>
          <span class="text-medium-emphasis">No congestion data</span>
        </template>
      </div>
    </l-popup>
  </l-circle-marker>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { LCircleMarker, LPopup } from '@vue-leaflet/vue-leaflet'
import { useCongestionStore } from '@/stores/congestionStore'
import type { CongestionScore } from '@/api/congestion'

const store = useCongestionStore()

const visibleBAs = computed(() => store.mappableBAs)

function scoreFor(baCode: string): CongestionScore | undefined {
  return store.scoresByBA.get(baCode)
}

function congestionColor(baCode: string): string {
  const score = scoreFor(baCode)
  if (!score || score.hours_above_80 == null) return '#95a5a6'
  const h80 = score.hours_above_80
  if (h80 >= 1000) return '#c0392b'
  if (h80 >= 500) return '#e74c3c'
  if (h80 >= 200) return '#e67e22'
  if (h80 >= 50) return '#f1c40f'
  return '#2ecc71'
}

function markerRadius(baCode: string): number {
  const score = scoreFor(baCode)
  if (!score || score.hours_above_80 == null) return 5
  const h80 = score.hours_above_80
  if (h80 >= 1000) return 10
  if (h80 >= 500) return 8
  if (h80 >= 200) return 7
  return 5
}

function pctFmt(v: number | null): string {
  if (v == null) return '-'
  return (v * 100).toFixed(1) + '%'
}

function onBAClick(baCode: string) {
  store.selectBA(baCode)
}
</script>
