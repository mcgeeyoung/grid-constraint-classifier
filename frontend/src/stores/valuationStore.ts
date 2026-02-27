import { defineStore } from 'pinia'
import { ref } from 'vue'
import { prospectiveValuation, createDERLocation, type ValuationResult } from '@/api/valuations'

export const useValuationStore = defineStore('valuation', () => {
  const sitingResult = ref<ValuationResult | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Preserve the inputs that produced the current result
  const lastDerType = ref<string>('solar')
  const lastCapacityMw = ref<number>(1.0)

  async function runSitingValuation(
    lat: number,
    lon: number,
    derType: string,
    capacityMw: number,
  ) {
    isLoading.value = true
    error.value = null
    sitingResult.value = null
    lastDerType.value = derType
    lastCapacityMw.value = capacityMw
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
    lastDerType,
    lastCapacityMw,
    runSitingValuation,
    saveDERLocation,
    clear,
  }
})
