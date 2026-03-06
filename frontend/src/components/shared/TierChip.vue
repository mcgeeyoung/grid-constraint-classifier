<template>
  <v-chip
    :color="chipColor"
    :size="size"
    :variant="variant"
    label
  >
    {{ tier }}
  </v-chip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { severityTierColor, valueTierColor, constraintTypeColor } from '@/utils/tierColors'

const props = withDefaults(defineProps<{
  tier: string
  type?: 'severity' | 'value' | 'constraint'
  size?: 'x-small' | 'small'
  variant?: 'flat' | 'outlined'
}>(), {
  type: 'severity',
  size: 'x-small',
  variant: 'flat',
})

const chipColor = computed(() => {
  switch (props.type) {
    case 'value': return valueTierColor(props.tier)
    case 'constraint': return constraintTypeColor(props.tier)
    default: return severityTierColor(props.tier)
  }
})
</script>
