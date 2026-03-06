import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  prospectiveValuation,
  compareDERTypes,
  valueRankings,
  createDERLocation,
} from '@/api/valuations'
import {
  getConstraintProfile,
  getDERProfile,
  listDERProfiles,
  getIntersection,
  zoneLoadshape,
} from '@/api/profiles'
import type {
  ValueStack,
  DERComparisonItem,
  LocationRanking,
  ConstraintProfile,
  DERProfile,
  Intersection,
  LoadshapeHour,
} from '@/types/constraints'

export interface ComparisonEntry {
  lat: number
  lon: number
  derType: string
  result: ValueStack
}

export const useValuationStore = defineStore('valuations', () => {
  const valueStack = ref<ValueStack | null>(null)
  const derComparison = ref<DERComparisonItem[]>([])
  const rankings = ref<LocationRanking[]>([])
  const isComputing = ref(false)
  const error = ref<string | null>(null)

  // Current inputs
  const selectedDERType = ref<string>('solar')
  const lastCapacityMw = ref<number>(1.0)

  // Site comparison
  const comparisonList = ref<ComparisonEntry[]>([])
  const selectedComparisonIndex = ref<number | null>(null)

  async function computeProspective(
    lat: number,
    lon: number,
    derType: string,
    capacityMw = 1.0,
  ) {
    isComputing.value = true
    error.value = null
    valueStack.value = null
    selectedDERType.value = derType
    lastCapacityMw.value = capacityMw
    try {
      valueStack.value = await prospectiveValuation(lat, lon, derType, capacityMw)
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Valuation failed'
    } finally {
      isComputing.value = false
    }
  }

  async function loadDERComparison(lat: number, lon: number) {
    isComputing.value = true
    try {
      const result = await compareDERTypes(lat, lon)
      derComparison.value = result.comparisons
    } catch {
      derComparison.value = []
    } finally {
      isComputing.value = false
    }
  }

  async function loadRankings(isoCode: string, derType: string) {
    isComputing.value = true
    try {
      rankings.value = await valueRankings(isoCode, derType)
    } catch {
      rankings.value = []
    } finally {
      isComputing.value = false
    }
  }

  function addToComparison() {
    if (!valueStack.value?.geo_resolution) return
    if (comparisonList.value.length >= 10) return
    const geo = valueStack.value.geo_resolution
    const exists = comparisonList.value.some(
      e => Math.abs(e.lat - geo.lat) < 0.0001 && Math.abs(e.lon - geo.lon) < 0.0001,
    )
    if (exists) return
    comparisonList.value.push({
      lat: geo.lat,
      lon: geo.lon,
      derType: selectedDERType.value,
      result: { ...valueStack.value },
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
    valueStack.value = comparisonList.value[index].result
  }

  function isInComparison(): boolean {
    if (!valueStack.value?.geo_resolution) return false
    const geo = valueStack.value.geo_resolution
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
    valueStack.value = null
    error.value = null
    derComparison.value = []
  }

  // ---- Profile state (from profileStore) ----
  const constraintProfile = ref<ConstraintProfile | null>(null)
  const derProfile = ref<DERProfile | null>(null)
  const derProfiles = ref<DERProfile[]>([])
  const intersection = ref<Intersection | null>(null)
  const loadshape = ref<LoadshapeHour[]>([])
  const isProfileLoading = ref(false)

  async function loadConstraintProfile(profileId: number) {
    isProfileLoading.value = true
    try {
      constraintProfile.value = await getConstraintProfile(profileId)
    } catch {
      constraintProfile.value = null
    } finally {
      isProfileLoading.value = false
    }
  }

  async function loadDERProfile(derType: string) {
    isProfileLoading.value = true
    try {
      derProfile.value = await getDERProfile(derType)
    } catch {
      derProfile.value = null
    } finally {
      isProfileLoading.value = false
    }
  }

  async function loadAllDERProfiles() {
    try {
      derProfiles.value = await listDERProfiles()
    } catch {
      derProfiles.value = []
    }
  }

  async function loadIntersection(constraintProfileId: number, derType: string) {
    isProfileLoading.value = true
    try {
      intersection.value = await getIntersection(constraintProfileId, derType)
    } catch {
      intersection.value = null
    } finally {
      isProfileLoading.value = false
    }
  }

  async function loadLoadshape(isoCode: string, zoneCode: string, month?: number) {
    isProfileLoading.value = true
    try {
      loadshape.value = await zoneLoadshape(isoCode, zoneCode, month)
    } catch {
      loadshape.value = []
    } finally {
      isProfileLoading.value = false
    }
  }

  function clearProfiles() {
    constraintProfile.value = null
    derProfile.value = null
    intersection.value = null
    loadshape.value = []
  }

  return {
    valueStack,
    derComparison,
    rankings,
    isComputing,
    error,
    selectedDERType,
    lastCapacityMw,
    comparisonList,
    selectedComparisonIndex,
    computeProspective,
    loadDERComparison,
    loadRankings,
    addToComparison,
    removeFromComparison,
    clearComparison,
    selectComparison,
    isInComparison,
    saveDERLocation,
    clear,
    // Profile state & actions
    constraintProfile,
    derProfile,
    derProfiles,
    intersection,
    loadshape,
    isProfileLoading,
    loadConstraintProfile,
    loadDERProfile,
    loadAllDERProfiles,
    loadIntersection,
    loadLoadshape,
    clearProfiles,
  }
})
