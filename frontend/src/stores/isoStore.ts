import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchISOs,
  fetchZones,
  fetchClassifications,
  fetchRecommendations,
  type ISO,
  type Zone,
  type ZoneClassification,
  type DERRecommendation,
} from '@/api/isos'
import { fetchDERLocations, type DERLocation } from '@/api/valuations'
import { useMapStore } from './mapStore'

const ISO_VIEW: Record<string, { lat: number; lng: number; zoom: number }> = {
  caiso: { lat: 37.0, lng: -119.5, zoom: 6 },
  miso:  { lat: 42.0, lng: -90.0, zoom: 5 },
  nyiso: { lat: 43.0, lng: -75.5, zoom: 7 },
  pjm:   { lat: 39.5, lng: -78.0, zoom: 6 },
  spp:   { lat: 37.5, lng: -97.0, zoom: 5 },
}

export const useIsoStore = defineStore('iso', () => {
  const isos = ref<ISO[]>([])
  const selectedISO = ref<string | null>(null)
  const zones = ref<Zone[]>([])
  const classifications = ref<ZoneClassification[]>([])
  const derLocations = ref<DERLocation[]>([])
  const recommendations = ref<DERRecommendation[]>([])
  const isLoading = ref(false)

  async function loadISOs() {
    isos.value = await fetchISOs()
  }

  async function selectISO(isoCode: string) {
    selectedISO.value = isoCode
    isLoading.value = true

    const view = ISO_VIEW[isoCode]
    if (view) {
      const mapStore = useMapStore()
      mapStore.panTo(view.lat, view.lng, view.zoom)
    }

    try {
      const [z, c, d, r] = await Promise.all([
        fetchZones(isoCode),
        fetchClassifications(isoCode),
        fetchDERLocations(isoCode),
        fetchRecommendations(isoCode),
      ])
      zones.value = z
      classifications.value = c
      derLocations.value = d
      recommendations.value = r
    } finally {
      isLoading.value = false
    }
  }

  function recommendationsForZone(zoneCode: string): DERRecommendation | null {
    return recommendations.value.find(r => r.zone_code === zoneCode) ?? null
  }

  return {
    isos,
    selectedISO,
    zones,
    classifications,
    derLocations,
    recommendations,
    isLoading,
    loadISOs,
    selectISO,
    recommendationsForZone,
  }
})
