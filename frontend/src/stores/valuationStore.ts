import { defineStore } from 'pinia'
import { ref } from 'vue'
import { prospectiveValuation, createDERLocation, type ValuationResult } from '@/api/valuations'

export const useValuationStore = defineStore('valuation', () => {
  const sitingResult = ref<ValuationResult | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function runSitingValuation(
    lat: number,
    lon: number,
    derType: string,
    capacityMw: number,
  ) {
    isLoading.value = true
    error.value = null
    sitingResult.value = null
    try {
      sitingResult.value = await prospectiveValuation(lat, lon, derType, capacityMw)
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Valuation failed'
    } finally {
      isLoading.value = false
    }
  }

  async function saveDERLocation(
    lat: number,
    lon: number,
    derType: string,
    capacityMw: number,
  ) {
    try {
      await createDERLocation(lat, lon, derType, capacityMw)
      return true
    } catch {
      return false
    }
  }

  function clear() {
    sitingResult.value = null
    error.value = null
  }

  return {
    sitingResult,
    isLoading,
    error,
    runSitingValuation,
    saveDERLocation,
    clear,
  }
})
