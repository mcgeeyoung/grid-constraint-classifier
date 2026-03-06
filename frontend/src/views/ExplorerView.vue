<template>
  <div style="height: calc(100vh - 40px); position: relative;">
    <NavDrawer />
    <GridMapGL />
    <ContextPanel />
    <v-progress-linear
      v-if="gridStore.isLoading"
      indeterminate
      color="primary"
      style="position: absolute; top: 0; left: 0; right: 0; z-index: 1000;"
    />
  </div>
</template>

<script setup lang="ts">
import GridMapGL from '@/components/map/GridMapGL.vue'
import NavDrawer from '@/components/layout/NavDrawer.vue'
import ContextPanel from '@/components/layout/ContextPanel.vue'
import { useGridDataStore } from '@/stores/gridDataStore'

const gridStore = useGridDataStore()
</script>
