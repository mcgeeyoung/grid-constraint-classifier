<template>
  <div v-if="annotations.length > 0" class="mb-3">
    <v-divider class="mb-2" />
    <h4 class="text-subtitle-2 mb-2">Annotations ({{ annotations.length }})</h4>

    <!-- Deferrals first -->
    <template v-for="group in groupedAnnotations" :key="group.type">
      <div v-if="group.items.length > 0">
        <AnnotationCard
          v-for="a in group.items"
          :key="a.id"
          :annotation="a"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Annotation } from '@/types/constraints'
import AnnotationCard from '@/components/panels/AnnotationCard.vue'

const props = defineProps<{
  annotations: Annotation[]
}>()

const typeOrder = ['deferral_opportunity', 'irp_citation', 'grid_plan', 'resource_need', 'constraint_context']

const groupedAnnotations = computed(() => {
  return typeOrder.map(type => ({
    type,
    items: props.annotations.filter(a => a.annotation_type === type),
  })).concat([{
    type: 'other',
    items: props.annotations.filter(a => !typeOrder.includes(a.annotation_type)),
  }])
})
</script>
