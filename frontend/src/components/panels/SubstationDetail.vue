<template>
  <div v-if="hierarchyStore.selectedSubstation">
    <h3 class="text-h6 mb-2">{{ hierarchyStore.selectedSubstation.substation_name }}</h3>
    <p v-if="hierarchyStore.selectedSubstation.bank_name" class="text-body-2 text-medium-emphasis mb-3">
      Bank: {{ hierarchyStore.selectedSubstation.bank_name }}
    </p>

    <v-chip
      :color="loadingColor"
      size="small"
      class="mb-3"
    >
      {{ loadingLabel }}
    </v-chip>

    <v-table density="compact">
      <tbody>
        <tr>
          <td class="text-medium-emphasis">Rating</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.facility_rating_mw?.toFixed(1) ?? '-' }} MW</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Loading</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.facility_loading_mw?.toFixed(1) ?? '-' }} MW</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Peak Loading</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.peak_loading_pct?.toFixed(1) ?? '-' }}%</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Type</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.facility_type ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Zone</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.zone_code ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Feeders</td>
          <td class="text-right">{{ hierarchyStore.selectedSubstation.feeder_count }}</td>
        </tr>
      </tbody>
    </v-table>

    <!-- Congestion Profile -->
    <div class="mt-4">
      <v-divider class="mb-3" />
      <div
        class="d-flex align-center justify-space-between"
        style="cursor: pointer;"
        @click="showCongestionProfile = !showCongestionProfile"
      >
        <h4 class="text-subtitle-2">Congestion Profile</h4>
        <v-icon size="16">{{ showCongestionProfile ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
      </div>

      <div v-if="showCongestionProfile" class="mt-2">
        <v-select
          v-model="selectedMonth"
          :items="monthOptions"
          density="compact"
          variant="outlined"
          hide-details
          class="mb-2"
          style="max-width: 160px;"
        />

        <div v-if="loadshapeLoading" class="text-center pa-2">
          <v-progress-circular indeterminate size="20" color="primary" />
        </div>

        <div v-else-if="loadshapeData.length > 0">
          <svg
            :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
            :width="chartWidth"
            :height="chartHeight"
            style="width: 100%; height: auto;"
          >
            <rect
              v-for="bar in bars"
              :key="bar.hour"
              :x="bar.x"
              :y="bar.y"
              :width="bar.width"
              :height="bar.height"
              :fill="bar.color"
              rx="1"
            />
            <text
              v-for="label in xLabels"
              :key="label.hour"
              :x="label.x"
              :y="chartHeight - 1"
              text-anchor="middle"
              fill="rgba(255,255,255,0.5)"
              font-size="8"
            >{{ label.hour }}</text>
          </svg>

          <div class="d-flex justify-space-between mt-2 text-caption">
            <div>
              <span class="text-medium-emphasis">Avg:</span>
              ${{ loadshapeStats.avg.toFixed(2) }}
            </div>
            <div>
              <span class="text-medium-emphasis">Peak hr:</span>
              {{ loadshapeStats.peakHour }}:00
            </div>
            <div>
              <span class="text-medium-emphasis">Peak:</span>
              ${{ loadshapeStats.max.toFixed(2) }}
            </div>
          </div>
          <div class="text-caption text-medium-emphasis mt-1">
            Based on zone {{ hierarchyStore.selectedSubstation?.zone_code ?? '' }} congestion
          </div>
        </div>

        <div v-else class="text-caption text-medium-emphasis">
          No congestion data available
        </div>
      </div>
    </div>

    <div v-if="hierarchyStore.feeders.length > 0" class="mt-4">
      <h4 class="text-subtitle-2 mb-2">Feeders</h4>
      <v-list density="compact">
        <v-list-item
          v-for="feeder in hierarchyStore.feeders"
          :key="feeder.id"
          :subtitle="`${feeder.capacity_mw?.toFixed(1) ?? '?'} MW cap, ${feeder.peak_loading_pct?.toFixed(0) ?? '?'}% loaded`"
        >
          <template v-slot:title>
            <span class="text-body-2">{{ feeder.feeder_id_external ?? `Feeder #${feeder.id}` }}</span>
          </template>
        </v-list-item>
      </v-list>
    </div>
  </div>
  <div v-else class="text-center text-medium-emphasis pa-4">
    Click a substation marker to see details
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useHierarchyStore } from '@/stores/hierarchyStore'
import { fetchSubstationLoadshape, type LoadshapeHour } from '@/api/hierarchy'

const hierarchyStore = useHierarchyStore()

const loadingPct = computed(() => hierarchyStore.selectedSubstation?.peak_loading_pct ?? 0)

const loadingColor = computed(() => {
  if (loadingPct.value > 100) return '#e74c3c'
  if (loadingPct.value >= 80) return '#e67e22'
  if (loadingPct.value >= 60) return '#f1c40f'
  return '#2ecc71'
})

const loadingLabel = computed(() => {
  if (loadingPct.value > 100) return 'Overloaded'
  if (loadingPct.value >= 80) return 'Near Capacity'
  if (loadingPct.value >= 60) return 'Moderate'
  return 'Normal'
})

// Congestion profile state
const showCongestionProfile = ref(false)
const loadshapeData = ref<LoadshapeHour[]>([])
const loadshapeLoading = ref(false)
const selectedMonth = ref<number | null>(null)

const monthOptions = [
  { title: 'All Months', value: null },
  { title: 'January', value: 1 },
  { title: 'February', value: 2 },
  { title: 'March', value: 3 },
  { title: 'April', value: 4 },
  { title: 'May', value: 5 },
  { title: 'June', value: 6 },
  { title: 'July', value: 7 },
  { title: 'August', value: 8 },
  { title: 'September', value: 9 },
  { title: 'October', value: 10 },
  { title: 'November', value: 11 },
  { title: 'December', value: 12 },
]

watch(
  [() => hierarchyStore.selectedSubstation?.id, showCongestionProfile, selectedMonth],
  async ([subId, show, month]) => {
    if (!subId || !show) {
      loadshapeData.value = []
      return
    }
    loadshapeLoading.value = true
    try {
      loadshapeData.value = await fetchSubstationLoadshape(subId, month ?? undefined)
    } catch {
      loadshapeData.value = []
    } finally {
      loadshapeLoading.value = false
    }
  },
  { immediate: true },
)

const chartWidth = 320
const chartHeight = 80
const chartPadTop = 4
const chartPadBottom = 14
const barGap = 2

const loadshapeStats = computed(() => {
  const data = loadshapeData.value
  if (data.length === 0) return { avg: 0, max: 0, peakHour: 0 }
  const vals = data.map(d => d.avg_congestion)
  const avg = vals.reduce((s, v) => s + v, 0) / vals.length
  const max = Math.max(...vals)
  const peakHour = data[vals.indexOf(max)]?.hour ?? 0
  return { avg, max, peakHour }
})

const bars = computed(() => {
  const data = loadshapeData.value
  if (data.length === 0) return []
  const maxVal = loadshapeStats.value.max || 1
  const barWidth = (chartWidth - barGap * 24) / 24
  const plotHeight = chartHeight - chartPadTop - chartPadBottom

  return data.map(d => {
    const ratio = d.avg_congestion / maxVal
    const height = Math.max(ratio * plotHeight, 1)
    const x = d.hour * (barWidth + barGap)
    const y = chartPadTop + plotHeight - height
    const r = Math.round(140 + ratio * 91)
    const g = Math.round(100 - ratio * 24)
    const b = Math.round(100 - ratio * 40)
    const alpha = 0.4 + ratio * 0.6
    return { hour: d.hour, x, y, width: barWidth, height, color: `rgba(${r},${g},${b},${alpha})` }
  })
})

const xLabels = computed(() => {
  const hours = [0, 6, 12, 18, 23]
  const barWidth = (chartWidth - barGap * 24) / 24
  return hours.map(h => ({
    hour: h,
    x: h * (barWidth + barGap) + barWidth / 2,
  }))
})
</script>
