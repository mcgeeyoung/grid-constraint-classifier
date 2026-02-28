import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface LatLng {
  lat: number
  lng: number
}

export type ZoneColorMode = 'classification' | 'value'
export type MapEngine = 'leaflet' | 'maplibre'

export const useMapStore = defineStore('map', () => {
  const mapEngine = ref<MapEngine>('maplibre')
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

  // GeoPackage infrastructure layers (OSM data)
  const showInfraLines = ref(false)
  const showInfraSubstations = ref(false)
  const showInfraPowerPlants = ref(false)

  // Zone color mode
  const zoneColorMode = ref<ZoneColorMode>('classification')

  // Filters
  const filterClassifications = ref<string[]>([]) // empty = show all
  const filterTiers = ref<string[]>([]) // empty = show all
  const filterDerType = ref<string | null>(null)
  const filterMinLoading = ref<number>(0) // 0 = no filter

  // Selected entities for side panel
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
    mapEngine,
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
