<template>
  <div class="mb-2 pa-2 rounded" style="border: 1px solid var(--border-default); background: var(--bg-surface-2);">
    <div class="d-flex align-center ga-2 mb-1">
      <v-chip :color="typeColor" size="x-small" variant="flat">
        {{ annotation.annotation_type }}
      </v-chip>
      <span
        :style="{ width: '8px', height: '8px', borderRadius: '50%', background: confidenceColor, display: 'inline-block' }"
        :title="`Confidence: ${(annotation.confidence * 100).toFixed(0)}%`"
      />
    </div>

    <div class="text-body-2 font-weight-medium mb-1">{{ annotation.title }}</div>

    <p v-if="annotation.summary" class="text-caption text-medium-emphasis mb-1" style="line-height: 1.3;">
      {{ annotation.summary }}
    </p>

    <div v-if="annotation.planned_solution" class="text-caption mb-1">
      <span class="text-medium-emphasis">Solution:</span>
      {{ annotation.planned_solution }}
    </div>

    <div v-if="annotation.deferral_value_estimate" class="text-caption mb-1">
      <span class="text-medium-emphasis">Deferral value:</span>
      ${{ annotation.deferral_value_estimate.toLocaleString() }}
    </div>

    <a
      v-if="annotation.source_url"
      :href="annotation.source_url"
      target="_blank"
      class="text-caption text-primary"
      style="text-decoration: none;"
    >
      Source
    </a>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Annotation } from '@/types/constraints'

const props = defineProps<{
  annotation: Annotation
}>()

const typeColor = computed(() => {
  switch (props.annotation.annotation_type) {
    case 'irp_citation': return 'blue'
    case 'grid_plan': return 'purple'
    case 'deferral_opportunity': return 'green'
    case 'constraint_context': return 'orange'
    default: return 'grey'
  }
})

const confidenceColor = computed(() => {
  const c = props.annotation.confidence
  if (c >= 0.7) return '#22c55e'
  if (c >= 0.4) return '#f59e0b'
  return '#ef4444'
})
</script>
