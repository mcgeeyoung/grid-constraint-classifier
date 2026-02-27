import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchSubstations,
  fetchSubstationDetail,
  fetchFeeders,
  fetchHierarchyScores,
  type Substation,
  type SubstationDetail,
  type Feeder,
  type HierarchyScore,
} from '@/api/hierarchy'

export const useHierarchyStore = defineStore('hierarchy', () => {
  const substations = ref<Substation[]>([])
  const selectedSubstation = ref<SubstationDetail | null>(null)
  const feeders = ref<Feeder[]>([])
  const scores = ref<HierarchyScore[]>([])
  const isLoading = ref(false)

  async function loadSubstations(isoCode: string, zoneCode?: string) {
    isLoading.value = true
    try {
      substations.value = await fetchSubstations(isoCode, zoneCode)
    } finally {
      isLoading.value = false
    }
  }

  async function selectSubstation(substationId: number) {
    isLoading.value = true
    try {
      selectedSubstation.value = await fetchSubstationDetail(substationId)
      if (selectedSubstation.value) {
        // fetchFeeders uses /substations/{id}/feeders, no isoCode needed
        feeders.value = await fetchFeeders(substationId)
      }
    } finally {
      isLoading.value = false
    }
  }

  async function loadScores(level?: string, entityId?: number) {
    scores.value = await fetchHierarchyScores(level, entityId)
  }

  return {
    substations,
    selectedSubstation,
    feeders,
    scores,
    isLoading,
    loadSubstations,
    selectSubstation,
    loadScores,
  }
})
