import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface LatLng {
  lat: number
  lng: number
}

export type ZoneColorMode = 'classification' | 'value'

export const useMapStore = defineStore('map', () => {
  const center = ref<LatLng>({ lat: 39.8, lng: -98.5 })
  const zoom = ref(5)
  const clickedPoint = ref<LatLng | null>(null)
  const showSitingPopup = ref(false)

  // Active map layers
  const showZones = ref(true)
  const showDERs = ref(true)
  const showSubstations = ref(false)

  // Zone color mode
  const zoneColorMode = ref<ZoneColorMode>('classification')

  // Selected entities for side panel
  const selectedZoneCode = ref<string | null>(null)
  const selectedSubstationId = ref<number | null>(null)

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
    zoneColorMode,
    selectedZoneCode,
    selectedSubstationId,
    setClickedPoint,
    clearClickedPoint,
    panTo,
  }
})
