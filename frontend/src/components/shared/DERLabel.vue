<template>
  <span class="d-inline-flex align-center ga-1">
    <v-icon v-if="showIcon" :icon="derIcon" size="16" />
    <span>{{ label }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { derLabel } from '@/utils/derLabels'

const props = withDefaults(defineProps<{
  derType: string
  showIcon?: boolean
}>(), {
  showIcon: false,
})

const DER_ICONS: Record<string, string> = {
  solar: 'mdi-white-balance-sunny',
  wind: 'mdi-wind-turbine',
  storage: 'mdi-battery-high',
  demand_response: 'mdi-lightning-bolt',
  energy_efficiency: 'mdi-lightbulb-on-outline',
  weatherization: 'mdi-home-thermometer',
  combined_heat_power: 'mdi-factory',
  fuel_cell: 'mdi-fuel-cell',
}

const label = computed(() => derLabel(props.derType))
const derIcon = computed(() => DER_ICONS[props.derType] ?? 'mdi-flash')
</script>
