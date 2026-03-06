<template>
  <div class="d-flex align-center ga-1 pa-2 pb-1" style="min-height: 32px;">
    <v-btn
      v-if="selectionStore.panelMode !== 'summary'"
      icon
      size="x-small"
      variant="text"
      @click="selectionStore.goBack()"
    >
      <v-icon size="16">mdi-arrow-left</v-icon>
    </v-btn>
    <template v-for="(item, i) in selectionStore.breadcrumb" :key="i">
      <span v-if="i > 0" class="text-medium-emphasis">/</span>
      <v-chip
        v-if="item.action"
        size="x-small"
        variant="text"
        @click="item.action"
        style="cursor: pointer;"
      >
        {{ item.label }}
      </v-chip>
      <span v-else class="text-caption text-medium-emphasis">{{ item.label }}</span>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useSelectionStore } from '@/stores/selectionStore'
const selectionStore = useSelectionStore()
</script>
