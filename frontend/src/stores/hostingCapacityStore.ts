import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchUtilities,
  fetchHostingCapacity,
  fetchHCSummary,
  type HCUtility,
  type HCFeeder,
  type HCSummary,
} from '@/api/hostingCapacity'

export const useHostingCapacityStore = defineStore('hostingCapacity', () => {
  const utilities = ref<HCUtility[]>([])
  const feeders = ref<HCFeeder[]>([])
  const selectedUtility = ref<string | null>(null)
  const selectedFeeder = ref<HCFeeder | null>(null)
  const summary = ref<HCSummary | null>(null)
  const isLoading = ref(false)

  async function loadUtilities() {
    isLoading.value = true
    try {
      utilities.value = await fetchUtilities()
    } finally {
      isLoading.value = false
    }
  }

  async function loadFeeders(utilityCode: string, bbox?: string) {
    isLoading.value = true
    selectedUtility.value = utilityCode
    try {
      feeders.value = await fetchHostingCapacity(utilityCode, {
        bbox,
        limit: 5000,
      })
      summary.value = await fetchHCSummary(utilityCode)
    } finally {
      isLoading.value = false
    }
  }

  function selectFeeder(feeder: HCFeeder | null) {
    selectedFeeder.value = feeder
  }

  function clear() {
    feeders.value = []
    selectedUtility.value = null
    selectedFeeder.value = null
    summary.value = null
  }

  return {
    utilities,
    feeders,
    selectedUtility,
    selectedFeeder,
    summary,
    isLoading,
    loadUtilities,
    loadFeeders,
    selectFeeder,
    clear,
  }
})
