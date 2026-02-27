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

    <!-- Load Profile -->
    <div class="mt-4">
      <v-divider class="mb-3" />
      <div
        class="d-flex align-center justify-space-between"
        style="cursor: pointer;"
        @click="showLoadProfile = !showLoadProfile"
      >
        <h4 class="text-subtitle-2">Load Profile</h4>
        <v-icon size="16">{{ showLoadProfile ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
      </div>

      <div v-if="showLoadProfile" class="mt-2">
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
            <!-- Low (base) bar -->
            <rect
              v-for="bar in bars"
              :key="`low-${bar.hour}`"
              :x="bar.x"
              :y="bar.yLow"
              :width="bar.width"
              :height="bar.heightLow"
              fill="rgba(52, 152, 219, 0.5)"
              rx="1"
            />
            <!-- High (range above low) bar -->
            <rect
              v-for="bar in bars"
              :key="`high-${bar.hour}`"
              :x="bar.x"
              :y="bar.yHigh"
              :width="bar.width"
              :height="bar.heightRange"
              fill="rgba(231, 76, 60, 0.6)"
              rx="1"
            />
            <!-- Rating line -->
            <line
              v-if="ratingLineY !== null"
              :x1="0" :y1="ratingLineY" :x2="chartWidth" :y2="ratingLineY"
              stroke="rgba(241, 196, 15, 0.7)" stroke-width="1" stroke-dasharray="4,3"
            />
            <text
              v-for="label in xLabels"
              :key="label.hour"
              :x="label.x"
              :y="chartHeight - 1"
              text-anchor="middle"
              fill="rgba(0,0,0,0.5)"
              font-size="8"
            >{{ label.hour }}</text>
          </svg>

          <div class="d-flex ga-3 mt-1 text-caption">
            <div class="d-flex align-center ga-1">
              <span style="display:inline-block;width:10px;height:10px;background:rgba(52,152,219,0.5);border-radius:2px;" />
              <span class="text-medium-emphasis">Low</span>
            </div>
            <div class="d-flex align-center ga-1">
              <span style="display:inline-block;width:10px;height:10px;background:rgba(231,76,60,0.6);border-radius:2px;" />
              <span class="text-medium-emphasis">High</span>
            </div>
            <div v-if="ratingLineY !== null" class="d-flex align-center ga-1">
              <span style="display:inline-block;width:10px;height:2px;background:rgba(241,196,15,0.7);" />
              <span class="text-medium-emphasis">Rating</span>
            </div>
          </div>

          <div class="d-flex justify-space-between mt-2 text-caption">
            <div>
              <span class="text-medium-emphasis">Peak hr:</span>
              {{ loadshapeStats.peakHour }}:00
            </div>
            <div>
              <span class="text-medium-emphasis">Peak:</span>
              {{ formatLoad(loadshapeStats.peakHigh) }}
            </div>
            <div>
              <span class="text-medium-emphasis">Avg:</span>
              {{ formatLoad(loadshapeStats.avgHigh) }}
            </div>
          </div>
        </div>

        <div v-else class="text-caption text-medium-emphasis">
          No load profile data available
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
import { fetchSubstationLoadshape, type SubstationLoadshapeHour } from '@/api/hierarchy'

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

// Load profile state
const showLoadProfile = ref(false)
const loadshapeData = ref<SubstationLoadshapeHour[]>([])
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
  [() => hierarchyStore.selectedSubstation?.id, showLoadProfile, selectedMonth],
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

function formatLoad(kw: number): string {
  if (kw >= 1000) return (kw / 1000).toFixed(1) + ' MW'
  return kw.toFixed(0) + ' kW'
}

const loadshapeStats = computed(() => {
  const data = loadshapeData.value
  if (data.length === 0) return { avgHigh: 0, peakHigh: 0, peakHour: 0 }
  const highs = data.map(d => d.load_high_kw)
  const avgHigh = highs.reduce((s, v) => s + v, 0) / highs.length
  const peakHigh = Math.max(...highs)
  const peakHour = data[highs.indexOf(peakHigh)]?.hour ?? 0
  return { avgHigh, peakHigh, peakHour }
})

// Rating in kW for the dashed reference line
const ratingKw = computed(() => {
  const mw = hierarchyStore.selectedSubstation?.facility_rating_mw
  return mw != null ? mw * 1000 : null
})

const chartMaxKw = computed(() => {
  const peak = loadshapeStats.value.peakHigh
  const rating = ratingKw.value
  if (rating != null) return Math.max(peak, rating) * 1.1
  return peak * 1.1 || 1
})

const ratingLineY = computed(() => {
  if (ratingKw.value == null) return null
  const plotHeight = chartHeight - chartPadTop - chartPadBottom
  const ratio = ratingKw.value / chartMaxKw.value
  return chartPadTop + plotHeight - ratio * plotHeight
})

const bars = computed(() => {
  const data = loadshapeData.value
  if (data.length === 0) return []
  const maxKw = chartMaxKw.value
  const barWidth = (chartWidth - barGap * 24) / 24
  const plotHeight = chartHeight - chartPadTop - chartPadBottom

  return data.map(d => {
    const ratioLow = d.load_low_kw / maxKw
    const ratioHigh = d.load_high_kw / maxKw
    const heightLow = Math.max(ratioLow * plotHeight, 1)
    const heightRange = Math.max((ratioHigh - ratioLow) * plotHeight, 0)
    const x = d.hour * (barWidth + barGap)
    const yLow = chartPadTop + plotHeight - heightLow
    const yHigh = chartPadTop + plotHeight - heightLow - heightRange
    return { hour: d.hour, x, width: barWidth, yLow, heightLow, yHigh, heightRange }
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
