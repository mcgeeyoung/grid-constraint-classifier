import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type PanelMode = 'summary' | 'iso' | 'zone' | 'location' | 'valuation' | 'compare' | 'ba' | 'utility' | 'substation' | 'der-viewer'

export interface BreadcrumbItem {
  label: string
  action?: () => void
}

export const useSelectionStore = defineStore('selection', () => {
  // Core selection state
  const selectedISOs = ref<string[]>([])
  const selectedZoneCode = ref<string | null>(null)
  const selectedSubstationId = ref<number | null>(null)
  const selectedBACode = ref<string | null>(null)
  const selectedUtilityCode = ref<string | null>(null)
  const clickedPoint = ref<{ lat: number; lng: number } | null>(null)
  const panelMode = ref<PanelMode>('summary')
  const selectedISOTab = ref<number>(0)

  // Computed
  const selectedISO = computed(() => selectedISOs.value[0] ?? null)

  const breadcrumb = computed<BreadcrumbItem[]>(() => {
    const items: BreadcrumbItem[] = []
    if (selectedISO.value) {
      items.push({ label: selectedISO.value.toUpperCase(), action: () => goBackTo('iso') })
    }
    if (selectedZoneCode.value) {
      items.push({ label: selectedZoneCode.value, action: () => goBackTo('zone') })
    }
    if (selectedBACode.value) {
      items.push({ label: selectedBACode.value })
    }
    if (selectedUtilityCode.value) {
      items.push({ label: selectedUtilityCode.value })
    }
    if (selectedSubstationId.value) {
      items.push({ label: `Substation #${selectedSubstationId.value}` })
    }
    if (clickedPoint.value) {
      items.push({ label: `${clickedPoint.value.lat.toFixed(2)}, ${clickedPoint.value.lng.toFixed(2)}` })
    }
    return items
  })

  const hasSelection = computed(() =>
    selectedISOs.value.length > 0 || selectedZoneCode.value !== null || clickedPoint.value !== null
  )

  // Actions
  function selectISO(code: string) {
    selectedISOs.value = [code]
    selectedZoneCode.value = null
    selectedSubstationId.value = null
    selectedBACode.value = null
    selectedUtilityCode.value = null
    clickedPoint.value = null
    panelMode.value = 'iso'
  }

  function toggleISO(code: string) {
    const idx = selectedISOs.value.indexOf(code)
    if (idx >= 0) {
      selectedISOs.value.splice(idx, 1)
    } else {
      selectedISOs.value.push(code)
    }
    panelMode.value = selectedISOs.value.length > 0 ? 'iso' : 'summary'
  }

  function selectZone(zoneCode: string) {
    selectedZoneCode.value = zoneCode
    selectedBACode.value = null
    clickedPoint.value = null
    panelMode.value = 'zone'
  }

  function selectBA(baCode: string) {
    selectedBACode.value = baCode
    selectedZoneCode.value = null
    selectedUtilityCode.value = null
    clickedPoint.value = null
    panelMode.value = 'ba'
  }

  function selectUtility(code: string) {
    selectedUtilityCode.value = code
    selectedZoneCode.value = null
    selectedBACode.value = null
    clickedPoint.value = null
    panelMode.value = 'utility'
  }

  function selectSubstation(id: number) {
    selectedSubstationId.value = id
    selectedBACode.value = null
    selectedUtilityCode.value = null
    clickedPoint.value = null
    panelMode.value = 'substation'
  }

  function clickMap(lat: number, lng: number) {
    clickedPoint.value = { lat, lng }
    selectedBACode.value = null
    panelMode.value = 'location'
  }

  function showValuation() {
    panelMode.value = 'valuation'
  }

  function showCompare() {
    panelMode.value = 'compare'
  }

  function goBackTo(mode: PanelMode) {
    if (mode === 'iso') {
      selectedZoneCode.value = null
      selectedBACode.value = null
      selectedUtilityCode.value = null
      clickedPoint.value = null
      panelMode.value = 'iso'
    } else if (mode === 'zone') {
      selectedBACode.value = null
      clickedPoint.value = null
      panelMode.value = 'zone'
    } else if (mode === 'summary') {
      selectedISOs.value = []
      selectedZoneCode.value = null
      selectedBACode.value = null
      selectedUtilityCode.value = null
      clickedPoint.value = null
      panelMode.value = 'summary'
    }
  }

  function showDERViewer() {
    panelMode.value = 'der-viewer'
  }

  function goBack() {
    if (panelMode.value === 'der-viewer') {
      if (selectedSubstationId.value) {
        panelMode.value = 'substation'
      } else if (selectedBACode.value) {
        panelMode.value = 'ba'
      } else if (selectedZoneCode.value) {
        panelMode.value = 'zone'
      } else {
        panelMode.value = 'iso'
      }
      return
    }
    if (panelMode.value === 'valuation' || panelMode.value === 'compare') {
      panelMode.value = clickedPoint.value ? 'location' : (selectedZoneCode.value ? 'zone' : 'iso')
    } else if (panelMode.value === 'location') {
      clickedPoint.value = null
      panelMode.value = selectedZoneCode.value ? 'zone' : 'iso'
    } else if (panelMode.value === 'substation') {
      selectedSubstationId.value = null
      panelMode.value = selectedZoneCode.value ? 'zone' : 'iso'
    } else if (panelMode.value === 'utility') {
      selectedUtilityCode.value = null
      panelMode.value = 'iso'
    } else if (panelMode.value === 'ba') {
      selectedBACode.value = null
      panelMode.value = 'iso'
    } else if (panelMode.value === 'zone') {
      selectedZoneCode.value = null
      panelMode.value = 'iso'
    } else if (panelMode.value === 'iso') {
      selectedISOs.value = []
      panelMode.value = 'summary'
    }
  }

  function clearAll() {
    selectedISOs.value = []
    selectedZoneCode.value = null
    selectedSubstationId.value = null
    selectedBACode.value = null
    selectedUtilityCode.value = null
    clickedPoint.value = null
    panelMode.value = 'summary'
    selectedISOTab.value = 0
  }

  return {
    selectedISOs, selectedISO, selectedZoneCode, selectedSubstationId,
    selectedBACode, selectedUtilityCode, clickedPoint, panelMode,
    selectedISOTab,
    breadcrumb, hasSelection,
    selectISO, toggleISO, selectZone, selectBA, selectUtility, selectSubstation,
    clickMap, showValuation, showCompare, showDERViewer,
    goBack, goBackTo, clearAll,
  }
})
