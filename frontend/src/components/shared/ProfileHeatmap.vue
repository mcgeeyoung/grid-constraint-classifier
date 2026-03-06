<template>
  <div>
    <div v-if="showLabels" class="d-flex align-center justify-space-between mb-2">
      <h4 class="text-subtitle-2">Profile Overlay</h4>
      <v-btn-toggle v-model="viewMode" mandatory density="compact" variant="outlined" divided>
        <v-btn value="heatmap" size="x-small">Heatmap</v-btn>
        <v-btn value="line" size="x-small">Line</v-btn>
      </v-btn-toggle>
    </div>

    <!-- Month selector for line view -->
    <v-select
      v-if="viewMode === 'line' && showLabels"
      v-model="selectedMonth"
      :items="monthOptions"
      density="compact"
      variant="outlined"
      hide-details
      class="mb-2"
      style="max-width: 160px;"
    />

    <!-- Heatmap view: 24 columns (hours) x 12 rows (months) -->
    <div v-if="viewMode === 'heatmap'">
      <svg
        :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
        :width="svgWidth"
        :height="svgHeight"
        style="width: 100%; height: auto;"
      >
        <!-- Grid background -->
        <rect
          :x="padLeft"
          :y="padTop"
          :width="24 * cW"
          :height="12 * cH"
          fill="rgba(255,255,255,0.03)"
          rx="2"
        />
        <!-- Grid lines -->
        <line
          v-for="m in 11"
          :key="`gl-${m}`"
          :x1="padLeft"
          :y1="padTop + m * cH"
          :x2="padLeft + 24 * cW"
          :y2="padTop + m * cH"
          stroke="rgba(255,255,255,0.06)"
          stroke-width="0.5"
        />
        <!-- Constraint layer -->
        <rect
          v-for="cell in constraintCells"
          :key="`c-${cell.m}-${cell.h}`"
          :x="cell.x"
          :y="cell.y"
          :width="cW"
          :height="cH"
          :fill="cell.color"
          :opacity="0.7"
        />
        <!-- DER overlay -->
        <rect
          v-for="cell in derCells"
          :key="`d-${cell.m}-${cell.h}`"
          :x="cell.x"
          :y="cell.y"
          :width="cW"
          :height="cH"
          :fill="cell.color"
          :opacity="0.4"
        />
        <!-- Overlap highlight -->
        <rect
          v-for="cell in overlapCells"
          :key="`o-${cell.m}-${cell.h}`"
          :x="cell.x"
          :y="cell.y"
          :width="cW"
          :height="cH"
          fill="#c084fc"
          :opacity="cell.intensity * 0.6"
        />
        <!-- Peak highlight -->
        <rect
          v-if="highlightPeak && peakMonth && peakHour != null"
          :x="padLeft + peakHour * cW"
          :y="padTop + (peakMonth - 1) * cH"
          :width="cW"
          :height="cH"
          fill="none"
          stroke="#fff"
          stroke-width="1.5"
        />
        <!-- Hour labels (top) -->
        <template v-if="showLabels">
          <text
            v-for="h in [0, 6, 12, 18]"
            :key="`hl-${h}`"
            :x="padLeft + h * cW + cW / 2"
            :y="padTop - 3"
            text-anchor="middle"
            fill="rgba(255,255,255,0.5)"
            :font-size="labelFontSize"
          >{{ h }}</text>
        </template>
        <!-- Month labels (left) -->
        <template v-if="showLabels">
          <text
            v-for="m in 12"
            :key="`ml-${m}`"
            :x="padLeft - 3"
            :y="padTop + (m - 1) * cH + cH / 2"
            text-anchor="end"
            dominant-baseline="central"
            fill="rgba(255,255,255,0.5)"
            :font-size="labelFontSize"
          >{{ monthAbbr[m - 1] }}</text>
        </template>
      </svg>

    </div>

    <!-- Line chart view: 24-hour profile for selected month -->
    <div v-else>
      <svg
        :viewBox="`0 0 ${lineWidth} ${lineHeight}`"
        :width="lineWidth"
        :height="lineHeight"
        style="width: 100%; height: auto;"
      >
        <polyline
          :points="constraintLinePoints"
          fill="none"
          :stroke="`rgb(${constraintBaseColor.join(',')})`"
          stroke-width="2"
        />
        <polyline
          v-if="derProfile"
          :points="derLinePoints"
          fill="none"
          stroke="#38bdf8"
          stroke-width="2"
          stroke-dasharray="4,2"
        />
        <template v-if="showLabels">
          <text
            v-for="h in [0, 6, 12, 18, 23]"
            :key="`lh-${h}`"
            :x="linePadLeft + h * lineStepX"
            :y="lineHeight - 2"
            text-anchor="middle"
            fill="rgba(255,255,255,0.5)"
            font-size="8"
          >{{ h }}</text>
        </template>
      </svg>
    </div>

    <!-- Legend + score indicator -->
    <div
      v-if="showLegend || showScore"
      class="d-flex flex-wrap align-center ga-3 mt-1 text-caption"
    >
      <span v-if="showLegend" class="d-flex align-center ga-1">
        <span :style="{ width: '10px', height: '10px', borderRadius: '2px', background: `rgb(${constraintBaseColor.join(',')})`, display: 'inline-block' }" />
        {{ constraintLabel }}
      </span>
      <span v-if="showLegend && derProfile" class="d-flex align-center ga-1">
        <span style="width: 10px; height: 10px; border-radius: 2px; background: #38bdf8; display: inline-block;" />
        DER Output
      </span>
      <span v-if="showLegend && derProfile" class="d-flex align-center ga-1">
        <span style="width: 10px; height: 10px; border-radius: 2px; background: #c084fc; display: inline-block;" />
        Overlap
      </span>
      <span
        v-if="showScore"
        class="d-flex align-center ga-1"
        :class="{ 'ml-auto': showLegend }"
        style="font-variant-numeric: tabular-nums;"
      >
        <span
          :style="{
            width: '8px',
            height: '8px',
            borderRadius: '2px',
            background: scoreTierColor,
            display: 'inline-block',
            flexShrink: 0,
          }"
        />
        {{ displayScore }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = withDefaults(defineProps<{
  constraintProfile?: Record<string, number[]> | null
  derProfile?: Record<string, number[]> | null
  overlapProfile?: Record<string, number[]> | null
  size?: 'mini' | 'standard' | 'large'
  showLabels?: boolean
  showLegend?: boolean
  interactive?: boolean
  highlightPeak?: boolean
  peakMonth?: number
  peakHour?: number
  constraintBaseColor?: [number, number, number]
  constraintLabel?: string
  score?: number | null
}>(), {
  constraintProfile: null,
  derProfile: null,
  overlapProfile: null,
  size: 'standard',
  showLabels: undefined,
  showLegend: true,
  interactive: false,
  highlightPeak: false,
  constraintBaseColor: () => [239, 68, 68],
  constraintLabel: 'Constraint',
  score: undefined,
})

const viewMode = ref<'heatmap' | 'line'>('heatmap')
const selectedMonth = ref<number>(1)

const monthAbbr = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
const monthOptions = Array.from({ length: 12 }, (_, i) => ({
  title: ['January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December'][i],
  value: i + 1,
}))

// Size-dependent dimensions
const sizeConfig = computed(() => {
  switch (props.size) {
    case 'mini': return { cellW: 4, cellH: 3, padLeft: 0, padTop: 0, fontSize: 5 }
    case 'large': return { cellW: 14, cellH: 14, padLeft: 20, padTop: 16, fontSize: 8 }
    default: return { cellW: 12, cellH: 12, padLeft: 16, padTop: 14, fontSize: 7 }
  }
})

const cW = computed(() => sizeConfig.value.cellW)
const cH = computed(() => sizeConfig.value.cellH)
const padLeft = computed(() => sizeConfig.value.padLeft)
const padTop = computed(() => sizeConfig.value.padTop)
const labelFontSize = computed(() => sizeConfig.value.fontSize)

const showLabels = computed(() => {
  if (props.showLabels !== undefined) return props.showLabels
  return props.size !== 'mini'
})

const svgWidth = computed(() => padLeft.value + 24 * cW.value + 4)
const svgHeight = computed(() => padTop.value + 12 * cH.value + 4)

function getMaxVal(profile: Record<string, number[]> | null | undefined): number {
  if (!profile) return 1
  let max = 0
  for (let m = 1; m <= 12; m++) {
    const row = profile[String(m)] ?? []
    for (const v of row) {
      if (v > max) max = v
    }
  }
  return max || 1
}

const constraintMax = computed(() => getMaxVal(props.constraintProfile))
const derMax = computed(() => getMaxVal(props.derProfile))

// Score: mean/peak ratio (0-100) auto-computed from profile, or use prop
const profileStats = computed(() => {
  if (!props.constraintProfile) return null
  let sum = 0
  let count = 0
  let peak = 0
  for (let m = 1; m <= 12; m++) {
    const row = props.constraintProfile[String(m)] ?? []
    for (const v of row) {
      sum += v
      count++
      if (v > peak) peak = v
    }
  }
  if (peak === 0 || count === 0) return null
  return { score: Math.round((sum / count / peak) * 100), mean: sum / count, peak }
})

const displayScore = computed(() => {
  if (props.score != null) return Math.round(props.score)
  return profileStats.value?.score ?? null
})

const scoreTierColor = computed(() => {
  const s = displayScore.value
  if (s == null) return '#6b7280'
  if (s >= 75) return '#ef4444'
  if (s >= 50) return '#f59e0b'
  if (s >= 25) return '#eab308'
  return '#22c55e'
})

const showScore = computed(() => displayScore.value != null && props.size !== 'mini')

function intensityToColor(val: number, maxVal: number, baseColor: [number, number, number]): string {
  const ratio = Math.min(val / maxVal, 1)
  const [r, g, b] = baseColor
  return `rgba(${r},${g},${b},${ratio})`
}

interface HeatCell { m: number; h: number; x: number; y: number; color: string }
interface OverlapCell { m: number; h: number; x: number; y: number; intensity: number }

const constraintCells = computed<HeatCell[]>(() => {
  if (!props.constraintProfile) return []
  const cells: HeatCell[] = []
  for (let m = 1; m <= 12; m++) {
    const row = props.constraintProfile[String(m)] ?? []
    for (let h = 0; h < 24; h++) {
      cells.push({
        m, h,
        x: padLeft.value + h * cW.value,
        y: padTop.value + (m - 1) * cH.value,
        color: intensityToColor(row[h] ?? 0, constraintMax.value, props.constraintBaseColor),
      })
    }
  }
  return cells
})

const derCells = computed<HeatCell[]>(() => {
  if (!props.derProfile) return []
  const cells: HeatCell[] = []
  for (let m = 1; m <= 12; m++) {
    const row = props.derProfile[String(m)] ?? []
    for (let h = 0; h < 24; h++) {
      cells.push({
        m, h,
        x: padLeft.value + h * cW.value,
        y: padTop.value + (m - 1) * cH.value,
        color: intensityToColor(row[h] ?? 0, derMax.value, [56, 189, 248]),
      })
    }
  }
  return cells
})

const overlapCells = computed<OverlapCell[]>(() => {
  if (!props.overlapProfile) return []
  const maxO = getMaxVal(props.overlapProfile)
  const cells: OverlapCell[] = []
  for (let m = 1; m <= 12; m++) {
    const row = props.overlapProfile[String(m)] ?? []
    for (let h = 0; h < 24; h++) {
      const val = row[h] ?? 0
      if (val > 0) {
        cells.push({
          m, h,
          x: padLeft.value + h * cW.value,
          y: padTop.value + (m - 1) * cH.value,
          intensity: val / maxO,
        })
      }
    }
  }
  return cells
})

// Line chart dimensions
const lineWidth = 320
const lineHeight = 100
const linePadLeft = 10
const linePadTop = 10
const linePadBottom = 16
const lineStepX = (lineWidth - linePadLeft - 10) / 23
const linePlotH = lineHeight - linePadTop - linePadBottom

function profileLinePoints(profile: Record<string, number[]> | null | undefined, maxVal: number): string {
  if (!profile) return ''
  const row = profile[String(selectedMonth.value)] ?? []
  return row.map((v, h) => {
    const x = linePadLeft + h * lineStepX
    const y = linePadTop + linePlotH - (v / maxVal) * linePlotH
    return `${x},${y}`
  }).join(' ')
}

const constraintLinePoints = computed(() =>
  profileLinePoints(props.constraintProfile, constraintMax.value),
)

const derLinePoints = computed(() =>
  profileLinePoints(props.derProfile, derMax.value),
)
</script>
