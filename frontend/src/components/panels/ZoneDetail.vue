<template>
  <div v-if="zone">
    <h3 class="text-h6 mb-2">{{ zone.zone_code }}</h3>
    <p v-if="zone.zone_name" class="text-body-2 text-medium-emphasis mb-3">
      {{ zone.zone_name }}
    </p>

    <v-chip
      :color="classificationColor(zone.classification)"
      size="small"
      class="mb-3"
    >
      {{ zone.classification }}
    </v-chip>

    <v-table density="compact">
      <tbody>
        <tr>
          <td class="text-medium-emphasis">Transmission Score</td>
          <td class="text-right">{{ zone.transmission_score?.toFixed(2) ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Generation Score</td>
          <td class="text-right">{{ zone.generation_score?.toFixed(2) ?? '-' }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Avg Congestion</td>
          <td class="text-right">{{ zone.avg_abs_congestion?.toFixed(2) ?? '-' }} $/MWh</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Max Congestion</td>
          <td class="text-right">{{ zone.max_congestion?.toFixed(2) ?? '-' }} $/MWh</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Congested Hours</td>
          <td class="text-right">{{ zone.congested_hours_pct != null ? (zone.congested_hours_pct * 100).toFixed(1) + '%' : '-' }}</td>
        </tr>
      </tbody>
    </v-table>

    <div class="mt-4">
      <h4 class="text-subtitle-2 mb-2">DER Locations in Zone</h4>
      <p class="text-body-2 text-medium-emphasis">
        {{ derCount }} DER{{ derCount !== 1 ? 's' : '' }} registered
      </p>
    </div>

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
        <!-- Month selector -->
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
          <!-- 24-hour bar chart -->
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
            <!-- X-axis labels -->
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

          <!-- Summary stats -->
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
        </div>

        <div v-else class="text-caption text-medium-emphasis">
          No congestion data available
        </div>
      </div>
    </div>

    <!-- Recommendations -->
    <div v-if="rec" class="mt-4">
      <v-divider class="mb-3" />
      <h4 class="text-subtitle-2 mb-2">DER Recommendations</h4>

      <p v-if="rec.rationale" class="text-body-2 text-medium-emphasis mb-3">
        {{ rec.rationale }}
      </p>

      <div v-if="rec.congestion_value" class="text-body-2 mb-3">
        Congestion value: <strong>${{ rec.congestion_value.toFixed(2) }}/MWh</strong>
      </div>

      <RecCard v-if="rec.primary_rec" :rec="rec.primary_rec" label="Primary" color="primary" />
      <RecCard v-if="rec.secondary_rec" :rec="rec.secondary_rec" label="Secondary" color="secondary" />
      <RecCard v-if="rec.tertiary_rec" :rec="rec.tertiary_rec" label="Tertiary" color="info" />
    </div>
    <div v-else-if="isoStore.recommendations.length > 0" class="mt-4">
      <v-divider class="mb-3" />
      <p class="text-body-2 text-medium-emphasis">No recommendations for this zone</p>
    </div>
  </div>
  <div v-else class="text-center text-medium-emphasis pa-4">
    Click a zone on the map to see details
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, defineComponent, h } from 'vue'
import { useIsoStore } from '@/stores/isoStore'
import { useMapStore } from '@/stores/mapStore'
import { fetchZoneLoadshape, type LoadshapeHour } from '@/api/isos'

const isoStore = useIsoStore()
const mapStore = useMapStore()

const zone = computed(() => {
  if (!mapStore.selectedZoneCode) return null
  return isoStore.classifications.find(c => c.zone_code === mapStore.selectedZoneCode) ?? null
})

const derCount = computed(() => {
  if (!mapStore.selectedZoneCode) return 0
  return isoStore.derLocations.filter(d => d.zone_code === mapStore.selectedZoneCode).length
})

const rec = computed(() => {
  if (!mapStore.selectedZoneCode) return null
  return isoStore.recommendationsForZone(mapStore.selectedZoneCode)
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

// Load loadshape data when profile is expanded or month changes
watch(
  [() => mapStore.selectedZoneCode, showCongestionProfile, selectedMonth],
  async ([zoneCode, show, month]) => {
    if (!zoneCode || !show || !isoStore.selectedISO) {
      loadshapeData.value = []
      return
    }
    loadshapeLoading.value = true
    try {
      loadshapeData.value = await fetchZoneLoadshape(
        isoStore.selectedISO,
        zoneCode,
        month ?? undefined,
      )
    } catch {
      loadshapeData.value = []
    } finally {
      loadshapeLoading.value = false
    }
  },
  { immediate: true },
)

// Bar chart dimensions
const chartWidth = 320
const chartHeight = 80
const chartPadTop = 4
const chartPadBottom = 14 // room for x-axis labels
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
    // Intensity color: low = muted, high = bright red
    const r = Math.round(140 + ratio * 91)  // 140 -> 231
    const g = Math.round(100 - ratio * 24)  // 100 -> 76
    const b = Math.round(100 - ratio * 40)  // 100 -> 60
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

function classificationColor(cls: string): string {
  switch (cls) {
    case 'transmission': return '#e74c3c'
    case 'generation': return '#3498db'
    case 'both': return '#9b59b6'
    case 'unconstrained': return '#2ecc71'
    default: return 'grey'
  }
}

// Inline recommendation card component
const RecCard = defineComponent({
  props: {
    rec: { type: Object, required: true },
    label: { type: String, required: true },
    color: { type: String, default: 'primary' },
  },
  setup(props) {
    return () => h('div', {
      class: 'mb-2 pa-2 rounded',
      style: 'border: 1px solid #ddd; background: rgba(0,0,0,0.02);',
    }, [
      h('div', { class: 'd-flex align-center ga-2 mb-1' }, [
        h('span', {
          class: `v-chip v-chip--size-x-small bg-${props.color} text-caption`,
          style: 'padding: 0 6px; border-radius: 4px; font-size: 11px;',
        }, props.label),
        h('span', { class: 'text-body-2 font-weight-medium' },
          props.rec.der_type ?? props.rec.type ?? 'DER'),
      ]),
      props.rec.rationale
        ? h('p', { class: 'text-caption text-medium-emphasis mb-0', style: 'line-height: 1.3;' },
            props.rec.rationale)
        : null,
      props.rec.value
        ? h('p', { class: 'text-caption mb-0' }, `Value: $${Number(props.rec.value).toFixed(2)}/kW-yr`)
        : null,
    ])
  },
})
</script>
