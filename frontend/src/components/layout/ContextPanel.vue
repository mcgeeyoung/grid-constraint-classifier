<template>
  <div class="glass-panel" style="position: absolute; top: 16px; right: 16px; width: 380px; max-height: calc(100vh - 72px); z-index: 500; display: flex; flex-direction: column;">
    <PanelBreadcrumb />
    <v-divider style="border-color: var(--border-subtle);" />
    <div style="flex: 1; overflow-y: auto; padding: 12px 14px;">
      <!-- Placeholder for summary/iso modes (browsing now in left drawer) -->
      <div v-if="mode === 'summary' || mode === 'iso'" class="text-center pa-6" style="color: var(--text-secondary);">
        <v-icon size="48" class="mb-3" color="grey">mdi-arrow-left-bold</v-icon>
        <div class="text-body-2">Select a zone, BA, or utility from the left panel to view details here.</div>
      </div>

      <ZonePanel v-else-if="mode === 'zone'" />
      <LocationPanel v-else-if="mode === 'location'" />
      <ValuationPanel v-else-if="mode === 'valuation'" />
      <ComparePanel v-else-if="mode === 'compare'" />
      <BAPanel v-else-if="mode === 'ba'" />
      <UtilityPanel v-else-if="mode === 'utility'" />
      <SubstationPanel v-else-if="mode === 'substation'" />
      <DERViewerPanel v-else-if="mode === 'der-viewer'" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useSelectionStore } from '@/stores/selectionStore'
import PanelBreadcrumb from './PanelBreadcrumb.vue'

const ZonePanel = defineAsyncComponent(() => import('@/components/panels/zone/ZonePanel.vue'))
const LocationPanel = defineAsyncComponent(() => import('@/components/panels/location/LocationPanel.vue'))
const ValuationPanel = defineAsyncComponent(() => import('@/components/panels/valuation/ValuationPanel.vue'))
const ComparePanel = defineAsyncComponent(() => import('@/components/panels/compare/ComparePanel.vue'))
const BAPanel = defineAsyncComponent(() => import('@/components/panels/ba/BAPanel.vue'))
const UtilityPanel = defineAsyncComponent(() => import('@/components/panels/utility/UtilityPanel.vue'))
const SubstationPanel = defineAsyncComponent(() => import('@/components/panels/substation/SubstationPanel.vue'))
const DERViewerPanel = defineAsyncComponent(() => import('@/components/panels/der-viewer/DERViewerPanel.vue'))

const selectionStore = useSelectionStore()
const mode = computed(() => selectionStore.panelMode)
</script>
