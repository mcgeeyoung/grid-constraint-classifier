<template>
  <div v-if="store.selectedBA">
    <div class="d-flex align-center justify-space-between mb-2">
      <h3 class="text-h6">{{ store.selectedBA.ba_code }}</h3>
      <v-btn icon size="x-small" variant="text" @click="store.clearSelection()">
        <v-icon size="16">mdi-close</v-icon>
      </v-btn>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-1">{{ store.selectedBA.ba_name }}</p>
    <div class="d-flex ga-2 mb-3">
      <v-chip size="x-small" variant="flat" color="primary">{{ store.selectedBA.region }}</v-chip>
      <v-chip v-if="score" :color="qualityColor(score.data_quality_flag)" size="x-small" variant="flat">
        {{ score.data_quality_flag }}
      </v-chip>
      <v-chip v-if="score?.lmp_coverage && score.lmp_coverage !== 'none'" size="x-small" variant="flat" color="info">
        LMP: {{ score.lmp_coverage }}
      </v-chip>
    </div>

    <!-- Key metrics -->
    <v-table v-if="score" density="compact" class="mb-3">
      <tbody>
        <tr>
          <td class="text-medium-emphasis">Transfer Limit</td>
          <td class="text-right">{{ fmtMW(score.transfer_limit_used) }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Hours Importing</td>
          <td class="text-right">{{ score.hours_importing ?? '-' }} ({{ pctFmt(score.pct_hours_importing) }})</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Hours > 80% Util.</td>
          <td class="text-right font-weight-medium">{{ score.hours_above_80 ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Hours > 90%</td>
          <td class="text-right">{{ score.hours_above_90 ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Hours > 95%</td>
          <td class="text-right">{{ score.hours_above_95 ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Avg Import / Load</td>
          <td class="text-right">{{ pctFmt(score.avg_import_pct_of_load) }}</td>
        </tr>
        <tr v-if="score.congestion_opportunity_score != null">
          <td class="text-medium-emphasis">Congestion Opp. Score</td>
          <td class="text-right font-weight-medium">${{ score.congestion_opportunity_score.toFixed(2) }}/kW</td>
        </tr>
        <tr v-if="score.avg_congestion_premium != null">
          <td class="text-medium-emphasis">Avg LMP Premium</td>
          <td class="text-right">${{ score.avg_congestion_premium.toFixed(2) }}/MWh</td>
        </tr>
      </tbody>
    </v-table>

    <!-- Duration Curve -->
    <div class="mt-2">
      <v-divider class="mb-3" />
      <div
        class="d-flex align-center justify-space-between"
        style="cursor: pointer;"
        @click="showDuration = !showDuration"
      >
        <h4 class="text-subtitle-2">Import Utilization Duration Curve</h4>
        <v-icon size="16">{{ showDuration ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
      </div>

      <div v-if="showDuration" class="mt-2">
        <div v-if="store.isDetailLoading" class="text-center pa-2">
          <v-progress-circular indeterminate size="20" color="primary" />
        </div>
        <div v-else-if="durationData && durationData.values.length > 0">
          <svg
            :viewBox="`0 0 ${chartW} ${chartH}`"
            :width="chartW"
            :height="chartH"
            style="width: 100%; height: auto;"
          >
            <!-- 80% threshold line -->
            <line
              :x1="0" :y1="thresholdY(0.8)" :x2="chartW" :y2="thresholdY(0.8)"
              stroke="rgba(231,76,60,0.4)" stroke-width="1" stroke-dasharray="4,3"
            />
            <text :x="chartW - 2" :y="thresholdY(0.8) - 2" text-anchor="end" fill="rgba(231,76,60,0.6)" font-size="7">80%</text>

            <!-- 100% line -->
            <line
              :x1="0" :y1="thresholdY(1.0)" :x2="chartW" :y2="thresholdY(1.0)"
              stroke="rgba(0,0,0,0.15)" stroke-width="0.5"
            />

            <!-- Zero line -->
            <line
              :x1="0" :y1="thresholdY(0)" :x2="chartW" :y2="thresholdY(0)"
              stroke="rgba(0,0,0,0.1)" stroke-width="0.5"
            />

            <!-- Duration curve area -->
            <path :d="areaPath" fill="rgba(52,152,219,0.25)" stroke="none" />
            <path :d="linePath" fill="none" stroke="#2980b9" stroke-width="1.5" />

            <!-- X-axis labels -->
            <text
              v-for="label in xLabels"
              :key="label.text"
              :x="label.x"
              :y="chartH - 1"
              text-anchor="middle"
              fill="rgba(0,0,0,0.5)"
              font-size="7"
            >{{ label.text }}</text>
          </svg>

          <div class="d-flex ga-3 mt-1 text-caption">
            <div class="d-flex align-center ga-1">
              <span style="display:inline-block;width:10px;height:2px;background:#2980b9;" />
              <span class="text-medium-emphasis">Utilization</span>
            </div>
            <div class="d-flex align-center ga-1">
              <span style="display:inline-block;width:10px;height:2px;background:rgba(231,76,60,0.4);border-style:dashed;" />
              <span class="text-medium-emphasis">80% threshold</span>
            </div>
          </div>
        </div>
        <div v-else class="text-caption text-medium-emphasis">
          No duration curve data available
        </div>
      </div>
    </div>

    <!-- Monthly Breakdown -->
    <div class="mt-2">
      <v-divider class="mb-3" />
      <div
        class="d-flex align-center justify-space-between"
        style="cursor: pointer;"
        @click="showMonthly = !showMonthly"
      >
        <h4 class="text-subtitle-2">Monthly Breakdown</h4>
        <v-icon size="16">{{ showMonthly ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
      </div>

      <div v-if="showMonthly" class="mt-2">
        <div v-if="store.isDetailLoading" class="text-center pa-2">
          <v-progress-circular indeterminate size="20" color="primary" />
        </div>
        <div v-else-if="store.selectedBAMonthly.length > 0">
          <!-- Monthly bar chart -->
          <svg
            :viewBox="`0 0 ${monthChartW} ${monthChartH}`"
            :width="monthChartW"
            :height="monthChartH"
            style="width: 100%; height: auto;"
          >
            <rect
              v-for="bar in monthBars"
              :key="bar.month"
              :x="bar.x"
              :y="bar.y"
              :width="bar.width"
              :height="bar.height"
              :fill="bar.color"
              rx="1"
            />
            <text
              v-for="bar in monthBars"
              :key="'l' + bar.month"
              :x="bar.x + bar.width / 2"
              :y="monthChartH - 1"
              text-anchor="middle"
              fill="rgba(0,0,0,0.5)"
              font-size="7"
            >{{ monthLabel(bar.month) }}</text>
          </svg>

          <div class="d-flex ga-3 mt-1 text-caption text-medium-emphasis">
            Hours above 80% utilization by month
          </div>

          <!-- Monthly table -->
          <v-table density="compact" class="mt-2 monthly-table">
            <thead>
              <tr>
                <th>Month</th>
                <th class="text-right">Hrs>80%</th>
                <th class="text-right">Import%</th>
                <th v-if="hasLMP" class="text-right">COS</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in store.selectedBAMonthly" :key="m.period_start">
                <td class="text-body-2">{{ monthName(m.period_start) }}</td>
                <td class="text-right">{{ m.hours_above_80 ?? '-' }}</td>
                <td class="text-right">{{ pctFmt(m.pct_hours_importing) }}</td>
                <td v-if="hasLMP" class="text-right">
                  <template v-if="m.congestion_opportunity_score != null">
                    ${{ m.congestion_opportunity_score.toFixed(2) }}
                  </template>
                  <template v-else>-</template>
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
        <div v-else class="text-caption text-medium-emphasis">
          No monthly data available
        </div>
      </div>
    </div>
  </div>
  <div v-else class="text-center text-medium-emphasis pa-4">
    Click a BA marker or table row to see details
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useCongestionStore } from '@/stores/congestionStore'

const store = useCongestionStore()

const showDuration = ref(true)
const showMonthly = ref(false)

const score = computed(() => store.selectedBAScore)
const durationData = computed(() => store.selectedBADuration)

const hasLMP = computed(() => {
  return store.selectedBAMonthly.some((m) => m.congestion_opportunity_score != null)
})

function pctFmt(v: number | null): string {
  if (v == null) return '-'
  return (v * 100).toFixed(1) + '%'
}

function fmtMW(v: number | null): string {
  if (v == null) return '-'
  return v.toFixed(0) + ' MW'
}

function qualityColor(flag: string | null): string {
  switch (flag) {
    case 'good': return 'success'
    case 'partial': return 'warning'
    case 'sparse': return 'error'
    default: return 'grey'
  }
}

// Duration curve chart
const chartW = 320
const chartH = 100
const padTop = 8
const padBottom = 14
const plotH = chartH - padTop - padBottom

function thresholdY(util: number): number {
  const maxUtil = Math.max(1.2, ...(durationData.value?.values ?? [1]))
  const minUtil = Math.min(0, ...(durationData.value?.values ?? [0]))
  const range = maxUtil - minUtil
  const ratio = (util - minUtil) / range
  return padTop + plotH - ratio * plotH
}

const linePath = computed(() => {
  const vals = durationData.value?.values ?? []
  if (vals.length === 0) return ''
  const maxUtil = Math.max(1.2, ...vals)
  const minUtil = Math.min(0, ...vals)
  const range = maxUtil - minUtil
  const stepX = chartW / vals.length

  return vals
    .map((v, i) => {
      const x = i * stepX
      const y = padTop + plotH - ((v - minUtil) / range) * plotH
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})

const areaPath = computed(() => {
  const vals = durationData.value?.values ?? []
  if (vals.length === 0) return ''
  const maxUtil = Math.max(1.2, ...vals)
  const minUtil = Math.min(0, ...vals)
  const range = maxUtil - minUtil
  const stepX = chartW / vals.length
  const zeroY = padTop + plotH - ((0 - minUtil) / range) * plotH

  const points = vals
    .map((v, i) => {
      const x = i * stepX
      const y = padTop + plotH - ((v - minUtil) / range) * plotH
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' L')

  return `M0,${zeroY.toFixed(1)} L${points} L${((vals.length - 1) * stepX).toFixed(1)},${zeroY.toFixed(1)} Z`
})

const xLabels = computed(() => {
  const vals = durationData.value?.values ?? []
  if (vals.length === 0) return []
  const n = vals.length
  const stepX = chartW / n
  const labels = [0, 2000, 4000, 6000, 8000].filter((h) => h < n)
  return labels.map((h) => ({
    text: h >= 1000 ? (h / 1000).toFixed(0) + 'k' : String(h),
    x: h * stepX,
  }))
})

// Monthly bar chart
const monthChartW = 320
const monthChartH = 60
const monthPadTop = 4
const monthPadBottom = 12
const monthPlotH = monthChartH - monthPadTop - monthPadBottom

const monthBars = computed(() => {
  const data = store.selectedBAMonthly
  if (data.length === 0) return []
  const maxH80 = Math.max(1, ...data.map((m) => m.hours_above_80 ?? 0))
  const barW = (monthChartW - data.length * 2) / data.length

  return data.map((m, i) => {
    const h80 = m.hours_above_80 ?? 0
    const height = Math.max((h80 / maxH80) * monthPlotH, 1)
    const month = new Date(m.period_start + 'T00:00:00').getMonth() + 1
    return {
      month,
      x: i * (barW + 2),
      y: monthPadTop + monthPlotH - height,
      width: barW,
      height,
      color: h80 >= 200 ? '#e74c3c' : h80 >= 50 ? '#e67e22' : '#2ecc71',
    }
  })
})

const MONTH_ABBR = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
const MONTH_NAMES = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

function monthLabel(m: number): string {
  return MONTH_ABBR[m - 1] ?? ''
}

function monthName(dateStr: string): string {
  const month = new Date(dateStr + 'T00:00:00').getMonth()
  return MONTH_NAMES[month] ?? dateStr
}
</script>

<style scoped>
.monthly-table td {
  padding-top: 2px !important;
  padding-bottom: 2px !important;
}
</style>
