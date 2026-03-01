import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchISOs,
  fetchZones,
  fetchZoneGeometries,
  fetchClassifications,
  fetchMultiISOClassifications,
  fetchRecommendations,
  fetchMultiISORecommendations,
  type ISO,
  type Zone,
  type ZoneGeometry,
  type ZoneClassification,
  type DERRecommendation,
} from '@/api/isos'
import { fetchDERLocations, type DERLocation } from '@/api/valuations'
import { useMapStore } from './mapStore'

export const ISO_VIEW: Record<string, { lat: number; lng: number; zoom: number }> = {
  caiso: { lat: 37.0, lng: -119.5, zoom: 6 },
  ercot: { lat: 31.0, lng: -97.5, zoom: 6 },
  isone: { lat: 42.5, lng: -72.0, zoom: 7 },
  miso:  { lat: 42.0, lng: -90.0, zoom: 5 },
  nyiso: { lat: 43.0, lng: -75.5, zoom: 7 },
  pjm:   { lat: 39.5, lng: -78.0, zoom: 6 },
  spp:   { lat: 37.5, lng: -97.0, zoom: 5 },
}

export const useIsoStore = defineStore('iso', () => {
  const isos = ref<ISO[]>([])
  const selectedISOs = ref<string[]>([])
  const isLoading = ref(false)

  // Per-ISO data keyed by iso_code
  const zonesMap = ref<Record<string, Zone[]>>({})
  const zoneGeometriesMap = ref<Record<string, ZoneGeometry[]>>({})
  const classificationsMap = ref<Record<string, ZoneClassification[]>>({})
  const derLocationsMap = ref<Record<string, DERLocation[]>>({})
  const recommendationsMap = ref<Record<string, DERRecommendation[]>>({})

  // Merged views across all selected ISOs
  const zones = computed(() => selectedISOs.value.flatMap(iso => zonesMap.value[iso] ?? []))
  const zoneGeometries = computed(() => selectedISOs.value.flatMap(iso => zoneGeometriesMap.value[iso] ?? []))
  const classifications = computed(() => selectedISOs.value.flatMap(iso => classificationsMap.value[iso] ?? []))
  const derLocations = computed(() => selectedISOs.value.flatMap(iso => derLocationsMap.value[iso] ?? []))
  const recommendations = computed(() => selectedISOs.value.flatMap(iso => recommendationsMap.value[iso] ?? []))

  // Convenience: first selected ISO (for backward compat with single-ISO code paths)
  const selectedISO = computed(() => selectedISOs.value[0] ?? null)

  async function loadISOs() {
    isos.value = await fetchISOs()
  }

  async function toggleISO(isoCode: string) {
    const idx = selectedISOs.value.indexOf(isoCode)
    if (idx >= 0) {
      // Deselect
      selectedISOs.value.splice(idx, 1)
      delete zonesMap.value[isoCode]
      delete zoneGeometriesMap.value[isoCode]
      delete classificationsMap.value[isoCode]
      delete derLocationsMap.value[isoCode]
      delete recommendationsMap.value[isoCode]
      return
    }

    // Select: add and load data
    selectedISOs.value.push(isoCode)
    await loadISOData(isoCode)

    // Pan to ISO region
    const view = ISO_VIEW[isoCode]
    if (view) {
      const mapStore = useMapStore()
      mapStore.panTo(view.lat, view.lng, view.zoom)
    }
  }

  async function selectISO(isoCode: string) {
    // Single-select mode: clear all and select one
    selectedISOs.value = [isoCode]
    zonesMap.value = {}
    zoneGeometriesMap.value = {}
    classificationsMap.value = {}
    derLocationsMap.value = {}
    recommendationsMap.value = {}

    await loadISOData(isoCode)

    const view = ISO_VIEW[isoCode]
    if (view) {
      const mapStore = useMapStore()
      mapStore.panTo(view.lat, view.lng, view.zoom)
    }
  }

  async function loadISOData(isoCode: string) {
    isLoading.value = true
    try {
      const [z, c, d, r] = await Promise.all([
        fetchZones(isoCode),
        fetchClassifications(isoCode),
        fetchDERLocations(isoCode),
        fetchRecommendations(isoCode),
      ])
      zonesMap.value[isoCode] = z
      classificationsMap.value[isoCode] = c
      derLocationsMap.value[isoCode] = d
      recommendationsMap.value[isoCode] = r

      // Load zone geometries in background
      fetchZoneGeometries(isoCode).then(g => {
        zoneGeometriesMap.value[isoCode] = g
      }).catch(() => {
        zoneGeometriesMap.value[isoCode] = []
      })
    } finally {
      isLoading.value = false
    }
  }

  function recommendationsForZone(zoneCode: string): DERRecommendation | null {
    return recommendations.value.find(r => r.zone_code === zoneCode) ?? null
  }

  return {
    isos,
    selectedISOs,
    selectedISO,
    zones,
    zoneGeometries,
    classifications,
    derLocations,
    recommendations,
    isLoading,
    loadISOs,
    selectISO,
    toggleISO,
    recommendationsForZone,
  }
})
