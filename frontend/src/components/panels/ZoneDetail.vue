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

        <div v-if="lmpLoading" class="text-center pa-2">
          <v-progress-circular indeterminate size="20" color="primary" />
        </div>

        <div v-else-if="lmpData.length > 0">
          <!-- SVG Sparkline -->
          <svg
            :viewBox="`0 0 ${sparkWidth} ${sparkHeight}`"
            :width="sparkWidth"
            :height="sparkHeight"
            style="width: 100%; height: auto;"
          >
            <!-- Zero line -->
            <line
              :x1="0" :y1="zeroY" :x2="sparkWidth" :y2="zeroY"
              stroke="rgba(255,255,255,0.15)" stroke-width="0.5"
            />
            <!-- Congestion area -->
            <path
              :d="areaPath"
              fill="rgba(231, 76, 60, 0.2)"
            />
            <!-- Congestion line -->
            <path
              :d="linePath"
              fill="none"
              stroke="#e74c3c"
              stroke-width="1"
            />
          </svg>

          <!-- Summary stats -->
          <div class="d-flex justify-space-between mt-2 text-caption">
            <div>
              <span class="text-medium-emphasis">Avg:</span>
              ${{ lmpStats.avg.toFixed(2) }}
            </div>
            <div>
              <span class="text-medium-emphasis">Max:</span>
              ${{ lmpStats.max.toFixed(2) }}
            </div>
            <div>
              <span class="text-medium-emphasis">Congested:</span>
              {{ lmpStats.congestedPct.toFixed(0) }}%
            </div>
          </div>
          <div class="text-caption text-medium-emphasis mt-1">
            {{ lmpData.length }} hours of data
          </div>
        </div>

        <div v-else class="text-caption text-medium-emphasis">
          No LMP data available
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
import { fetchZoneLMPs, type ZoneLMP } from '@/api/isos'

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
const lmpData = ref<ZoneLMP[]>([])
const lmpLoading = ref(false)
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

// Load LMP data when profile is expanded or month changes
watch(
  [() => mapStore.selectedZoneCode, showCongestionProfile, selectedMonth],
  async ([zoneCode, show, month]) => {
    if (!zoneCode || !show || !isoStore.selectedISO) {
      lmpData.value = []
      return
    }
    lmpLoading.value = true
    try {
      lmpData.value = await fetchZoneLMPs(
        isoStore.selectedISO,
        zoneCode,
        720,
        month ?? undefined,
      )
    } catch {
      lmpData.value = []
    } finally {
      lmpLoading.value = false
    }
  },
  { immediate: true },
)

// Sparkline dimensions
const sparkWidth = 320
const sparkHeight = 60

const congestionValues = computed(() => {
  return lmpData.value
    .map(d => d.congestion ?? 0)
    .reverse() // chronological order (endpoint returns desc)
})

const lmpStats = computed(() => {
  const vals = congestionValues.value
  if (vals.length === 0) return { avg: 0, max: 0, congestedPct: 0 }
  const absVals = vals.map(v => Math.abs(v))
  const avg = absVals.reduce((s, v) => s + v, 0) / vals.length
  const max = Math.max(...absVals)
  const congested = vals.filter(v => Math.abs(v) > 1).length
  return { avg, max, congestedPct: (congested / vals.length) * 100 }
})

const zeroY = computed(() => {
  const vals = congestionValues.value
  if (vals.length === 0) return sparkHeight / 2
  const min = Math.min(...vals, 0)
  const max = Math.max(...vals, 0)
  const range = max - min || 1
  return ((max - 0) / range) * (sparkHeight - 4) + 2
})

const linePath = computed(() => {
  const vals = congestionValues.value
  if (vals.length < 2) return ''
  const min = Math.min(...vals, 0)
  const max = Math.max(...vals, 0)
  const range = max - min || 1
  const dx = sparkWidth / (vals.length - 1)

  return vals.map((v, i) => {
    const x = i * dx
    const y = ((max - v) / range) * (sparkHeight - 4) + 2
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

const areaPath = computed(() => {
  const vals = congestionValues.value
  if (vals.length < 2) return ''
  const min = Math.min(...vals, 0)
  const max = Math.max(...vals, 0)
  const range = max - min || 1
  const dx = sparkWidth / (vals.length - 1)
  const zy = zeroY.value

  const points = vals.map((v, i) => {
    const x = i * dx
    const y = ((max - v) / range) * (sparkHeight - 4) + 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  return `M0,${zy} L${points.join(' L')} L${sparkWidth},${zy} Z`
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
      style: 'border: 1px solid #444; background: rgba(255,255,255,0.03);',
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
