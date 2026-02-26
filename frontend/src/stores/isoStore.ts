import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchISOs,
  fetchZones,
  fetchClassifications,
  type ISO,
  type Zone,
  type ZoneClassification,
} from '@/api/isos'
import { fetchDERLocations, type DERLocation } from '@/api/valuations'

export const useIsoStore = defineStore('iso', () => {
  const isos = ref<ISO[]>([])
  const selectedISO = ref<string | null>(null)
  const zones = ref<Zone[]>([])
  const classifications = ref<ZoneClassification[]>([])
  const derLocations = ref<DERLocation[]>([])
  const isLoading = ref(false)

  async function loadISOs() {
    isos.value = await fetchISOs()
  }

  async function selectISO(isoCode: string) {
    selectedISO.value = isoCode
    isLoading.value = true
    try {
      const [z, c, d] = await Promise.all([
        fetchZones(isoCode),
        fetchClassifications(isoCode),
        fetchDERLocations(isoCode),
      ])
      zones.value = z
      classifications.value = c
      derLocations.value = d
    } finally {
      isLoading.value = false
    }
  }

  return {
    isos,
    selectedISO,
    zones,
    classifications,
    derLocations,
    isLoading,
    loadISOs,
    selectISO,
  }
})
