import { defineStore } from 'pinia'
import { ref } from 'vue'
import { prospectiveValuation, createDERLocation, type ValuationResult } from '@/api/valuations'

export interface ComparisonEntry {
  lat: number
  lon: number
  derType: string
  capacityMw: number
  result: ValuationResult
}

export const useValuationStore = defineStore('valuation', () => {
  const sitingResult = ref<ValuationResult | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Preserve the inputs that produced the current result
  const lastDerType = ref<string>('solar')
  const lastCapacityMw = ref<number>(1.0)

  // Site comparison list (max 10)
  const comparisonList = ref<ComparisonEntry[]>([])
  const selectedComparisonIndex = ref<number | null>(null)

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

  function addToComparison() {
    if (!sitingResult.value?.geo_resolution) return
    if (comparisonList.value.length >= 10) return
    const geo = sitingResult.value.geo_resolution
    // Check for duplicate (same lat/lon)
    const exists = comparisonList.value.some(
      e => Math.abs(e.lat - geo.lat) < 0.0001 && Math.abs(e.lon - geo.lon) < 0.0001,
    )
    if (exists) return
    comparisonList.value.push({
      lat: geo.lat,
      lon: geo.lon,
      derType: lastDerType.value,
      capacityMw: lastCapacityMw.value,
      result: { ...sitingResult.value },
    })
  }

  function removeFromComparison(index: number) {
    comparisonList.value.splice(index, 1)
    if (selectedComparisonIndex.value === index) {
      selectedComparisonIndex.value = null
    } else if (selectedComparisonIndex.value !== null && selectedComparisonIndex.value > index) {
      selectedComparisonIndex.value--
    }
  }

  function clearComparison() {
    comparisonList.value = []
    selectedComparisonIndex.value = null
  }

  function selectComparison(index: number) {
    selectedComparisonIndex.value = index
    sitingResult.value = comparisonList.value[index].result
  }

  function isInComparison(): boolean {
    if (!sitingResult.value?.geo_resolution) return false
    const geo = sitingResult.value.geo_resolution
    return comparisonList.value.some(
      e => Math.abs(e.lat - geo.lat) < 0.0001 && Math.abs(e.lon - geo.lon) < 0.0001,
    )
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
    comparisonList,
    selectedComparisonIndex,
    runSitingValuation,
    addToComparison,
    removeFromComparison,
    clearComparison,
    selectComparison,
    isInComparison,
    saveDERLocation,
    clear,
  }
})
