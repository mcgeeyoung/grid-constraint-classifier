<template>
  <div class="mb-3">
    <h4 class="text-subtitle-2 mb-2">Duration Curve</h4>
    <svg
      :viewBox="`0 0 ${width} ${height}`"
      :width="width"
      :height="height"
      style="width: 100%; height: auto;"
    >
      <!-- Y-axis reference lines -->
      <line
        v-for="pct in [0.25, 0.5, 0.75, 1.0]"
        :key="pct"
        :x1="padLeft"
        :y1="padTop + plotH - pct * plotH"
        :x2="width - padRight"
        :y2="padTop + plotH - pct * plotH"
        stroke="rgba(255,255,255,0.08)"
        stroke-width="1"
      />

      <!-- Transfer limit line (if available) -->
      <line
        v-if="data.transfer_limit_mw"
        :x1="padLeft"
        :y1="limitY"
        :x2="width - padRight"
        :y2="limitY"
        stroke="#ef4444"
        stroke-width="1"
        stroke-dasharray="4,2"
      />

      <!-- Duration curve line -->
      <polyline
        :points="linePoints"
        fill="none"
        stroke="#38bdf8"
        stroke-width="2"
      />

      <!-- X-axis labels -->
      <text
        v-for="h in [0, 2190, 4380, 6570, 8760]"
        :key="h"
        :x="padLeft + (h / maxHours) * plotW"
        :y="height - 2"
        text-anchor="middle"
        fill="rgba(255,255,255,0.5)"
        font-size="8"
      >{{ h }}</text>

      <!-- Y-axis labels -->
      <text :x="padLeft - 3" :y="padTop + plotH" text-anchor="end" fill="rgba(255,255,255,0.5)" font-size="7">0</text>
      <text :x="padLeft - 3" :y="padTop" text-anchor="end" fill="rgba(255,255,255,0.5)" font-size="7">100%</text>
    </svg>

    <div v-if="data.transfer_limit_mw" class="d-flex align-center ga-2 mt-1 text-caption">
      <span style="width: 12px; height: 2px; background: #ef4444; display: inline-block;" />
      Transfer limit: {{ data.transfer_limit_mw }} MW
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DurationCurve } from '@/api/congestion'

const props = defineProps<{
  data: DurationCurve
}>()

const width = 360
const height = 140
const padLeft = 28
const padRight = 8
const padTop = 10
const padBottom = 16
const plotW = width - padLeft - padRight
const plotH = height - padTop - padBottom
const maxHours = computed(() => props.data.hours_count || 8760)

const maxValue = computed(() => {
  if (props.data.values.length === 0) return 100
  return Math.max(...props.data.values, props.data.transfer_limit_mw ?? 0) || 100
})

const limitY = computed(() => {
  if (!props.data.transfer_limit_mw) return 0
  const ratio = props.data.transfer_limit_mw / maxValue.value
  return padTop + plotH - ratio * plotH
})

const linePoints = computed(() => {
  const vals = props.data.values
  if (vals.length === 0) return ''
  const step = plotW / (vals.length - 1 || 1)
  return vals.map((v, i) => {
    const x = padLeft + i * step
    const y = padTop + plotH - (v / maxValue.value) * plotH
    return `${x},${y}`
  }).join(' ')
})
</script>
