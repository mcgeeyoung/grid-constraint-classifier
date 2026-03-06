import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface LatLng {
  lat: number
  lng: number
}

export type ZoneColorMode = 'classification' | 'value' | 'severity'

export const useMapStore = defineStore('map', () => {
  const center = ref<LatLng>({ lat: 39.8, lng: -98.5 })
  const zoom = ref(5)
  const clickedPoint = ref<LatLng | null>(null)
  const showSitingPopup = ref(false)

  // Active map layers
  const showZones = ref(true)
  const showDERs = ref(true)
  const showSubstations = ref(false)
  const showDataCenters = ref(false)
  const showTransmissionLines = ref(true)
  const showFeeders = ref(true)
  const showAssets = ref(false)
  const showHostingCapacity = ref(false)
  const showInterconnectionQueue = ref(false)
  const showBAMarkers = ref(false)

  // GeoPackage infrastructure layers (OSM data)
  const showInfraLines = ref(false)
  const showInfraSubstations = ref(false)
  const showInfraPowerPlants = ref(false)

  // Zone color mode
  const zoneColorMode = ref<ZoneColorMode>('severity')

  // Filters
  const filterClassifications = ref<string[]>([])
  const filterTiers = ref<string[]>([])
  const filterDerType = ref<string | null>(null)
  const filterMinLoading = ref<number>(0)

  // Selection state kept here for backward compat with GridMapGL
  // Will be fully migrated to selectionStore in Phase 2
  const selectedZoneCode = ref<string | null>(null)
  const selectedSubstationId = ref<number | null>(null)
  const selectedAssetId = ref<string | null>(null)

  function setClickedPoint(point: LatLng) {
    clickedPoint.value = point
    showSitingPopup.value = true
  }

  function clearClickedPoint() {
    clickedPoint.value = null
    showSitingPopup.value = false
  }

  function panTo(lat: number, lng: number, z?: number) {
    center.value = { lat, lng }
    if (z !== undefined) zoom.value = z
  }

  return {
    center,
    zoom,
    clickedPoint,
    showSitingPopup,
    showZones,
    showDERs,
    showSubstations,
    showDataCenters,
    showTransmissionLines,
    showFeeders,
    showAssets,
    showHostingCapacity,
    showInterconnectionQueue,
    showBAMarkers,
    showInfraLines,
    showInfraSubstations,
    showInfraPowerPlants,
    zoneColorMode,
    filterClassifications,
    filterTiers,
    filterDerType,
    filterMinLoading,
    selectedZoneCode,
    selectedSubstationId,
    selectedAssetId,
    setClickedPoint,
    clearClickedPoint,
    panTo,
  }
})
