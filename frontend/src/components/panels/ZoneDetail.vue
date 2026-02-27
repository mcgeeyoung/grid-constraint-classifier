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
import { computed, defineComponent, h } from 'vue'
import { useIsoStore } from '@/stores/isoStore'
import { useMapStore } from '@/stores/mapStore'

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
