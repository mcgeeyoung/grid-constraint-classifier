import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useSelectionStore } from './selectionStore'
import {
  fetchUtilities,
  fetchHostingCapacity,
  fetchHostingCapacityGeoJSON,
  fetchHCSummary,
  fetchHCProfile,
  type HCUtility,
  type HCFeeder as HCFeederFull,
  type HCSummary,
  type HCProfile,
} from '@/api/hostingCapacity'
import {
  fetchWattCarbonAssets,
  fetchWattCarbonAssetDetail,
  runRetrospectiveValuation,
  type WattCarbonAsset,
  type WattCarbonAssetDetail,
  type RetrospectiveValuation,
} from '@/api/wattcarbon'
import {
  nearbyHostingCapacity,
  nearbyInterconnection,
  utilityFilings,
} from '@/api/enrichment'
import { getDERGridScores } from '@/api/profiles'
import type { DERGridScores } from '@/types/constraints'
import type {
  HCFeeder,
  InterconnectionProject,
  UtilityFiling,
} from '@/types/constraints'

export const useEnrichmentStore = defineStore('enrichment', () => {
  // ---- Hosting Capacity state (from hostingCapacityStore) ----
  const hcUtilities = ref<HCUtility[]>([])
  const hcFeeders = ref<HCFeederFull[]>([])
  const selectedUtility = ref<string | null>(null)
  const selectedFeeder = ref<HCFeederFull | null>(null)
  const hcSummary = ref<HCSummary | null>(null)
  const isLoading = ref(false)
  const filterConstraint = ref<string | null>(null)
  const filterMinCapacity = ref<number | null>(null)

  const constraintTypes = computed(() => {
    const types = new Set(hcFeeders.value.map(f => f.constraining_metric).filter(Boolean) as string[])
    return Array.from(types).sort()
  })

  const selectionStore = useSelectionStore()

  const utilitiesForSelectedISO = computed(() => {
    const isos = selectionStore.selectedISOs
    if (!isos.length) return hcUtilities.value
    return hcUtilities.value.filter(u =>
      u.iso_code && isos.some(iso => u.iso_code === iso)
    )
  })

  const filteredFeeders = computed(() => {
    let result = hcFeeders.value
    if (filterConstraint.value) {
      result = result.filter(f => f.constraining_metric === filterConstraint.value)
    }
    if (filterMinCapacity.value != null) {
      result = result.filter(f => (f.remaining_capacity_mw ?? 0) >= filterMinCapacity.value!)
    }
    return result
  })

  // ---- WattCarbon state (from wattcarbonStore) ----
  const assets = ref<WattCarbonAsset[]>([])
  const selectedAsset = ref<WattCarbonAssetDetail | null>(null)
  const retroResult = ref<RetrospectiveValuation | null>(null)

  // ---- Nearby enrichment (NEW) ----
  const nearbyFeeders = ref<HCFeeder[]>([])
  const nearbyQueueProjects = ref<InterconnectionProject[]>([])
  const utilityFilingsList = ref<UtilityFiling[]>([])
  const isNearbyLoading = ref(false)

  // ---- DER Viewer state ----
  const derGridScores = ref<DERGridScores | null>(null)
  const selectedViewerDERType = ref('solar')
  const isDERViewerLoading = ref(false)
  const derViewerError = ref<string | null>(null)

  // ---- HC 12x24 Profile ----
  const selectedHCProfile = ref<HCProfile | null>(null)
  const isHCProfileLoading = ref(false)

  // ---- HC Actions ----
  async function loadUtilities() {
    isLoading.value = true
    try {
      hcUtilities.value = await fetchUtilities()
    } finally {
      isLoading.value = false
    }
  }

  async function loadFeeders(utilityCode: string, bbox?: string) {
    isLoading.value = true
    selectedUtility.value = utilityCode
    try {
      hcFeeders.value = await fetchHostingCapacity(utilityCode, { bbox, limit: 5000 })
      hcSummary.value = await fetchHCSummary(utilityCode)
    } finally {
      isLoading.value = false
    }
  }

  function selectFeederItem(feeder: HCFeederFull | null) {
    selectedFeeder.value = feeder
  }

  async function exportGeoJSON() {
    if (!selectedUtility.value) return
    const data = await fetchHostingCapacityGeoJSON(selectedUtility.value)
    const blob = new Blob([JSON.stringify(data)], { type: 'application/geo+json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `hosting-capacity-${selectedUtility.value}.geojson`
    a.click()
    URL.revokeObjectURL(url)
  }

  function clearHC() {
    hcFeeders.value = []
    selectedUtility.value = null
    selectedFeeder.value = null
    hcSummary.value = null
    filterConstraint.value = null
    filterMinCapacity.value = null
  }

  // ---- WattCarbon Actions ----
  async function loadAssets(isoCode: string) {
    isLoading.value = true
    try {
      assets.value = await fetchWattCarbonAssets(isoCode)
    } finally {
      isLoading.value = false
    }
  }

  async function selectAsset(assetId: string) {
    isLoading.value = true
    retroResult.value = null
    try {
      selectedAsset.value = await fetchWattCarbonAssetDetail(assetId)
    } finally {
      isLoading.value = false
    }
  }

  async function runRetrospective(assetId: string, start: string, end: string) {
    isLoading.value = true
    try {
      retroResult.value = await runRetrospectiveValuation(assetId, start, end)
      selectedAsset.value = await fetchWattCarbonAssetDetail(assetId)
    } finally {
      isLoading.value = false
    }
  }

  // ---- Nearby Enrichment Actions (NEW) ----
  async function loadNearbyHC(lat: number, lon: number, radiusKm = 10) {
    isNearbyLoading.value = true
    try {
      nearbyFeeders.value = await nearbyHostingCapacity(lat, lon, radiusKm)
    } catch {
      nearbyFeeders.value = []
    } finally {
      isNearbyLoading.value = false
    }
  }

  async function loadNearbyQueue(lat: number, lon: number, radiusKm = 50) {
    isNearbyLoading.value = true
    try {
      nearbyQueueProjects.value = await nearbyInterconnection(lat, lon, radiusKm)
    } catch {
      nearbyQueueProjects.value = []
    } finally {
      isNearbyLoading.value = false
    }
  }

  async function loadFilings(utilityCode: string) {
    isLoading.value = true
    try {
      utilityFilingsList.value = await utilityFilings(utilityCode)
    } catch {
      utilityFilingsList.value = []
    } finally {
      isLoading.value = false
    }
  }

  // ---- HC Profile Actions ----
  async function loadHCProfile(utilityCode: string, year?: number) {
    isHCProfileLoading.value = true
    try {
      selectedHCProfile.value = await fetchHCProfile(utilityCode, year)
    } catch {
      selectedHCProfile.value = null
    } finally {
      isHCProfileLoading.value = false
    }
  }

  // ---- DER Viewer Actions ----
  async function loadDERGridScores(lat: number, lon: number, derType: string, isoCode?: string) {
    isDERViewerLoading.value = true
    derViewerError.value = null
    selectedViewerDERType.value = derType
    try {
      const iso = isoCode ?? selectionStore.selectedISO ?? undefined
      derGridScores.value = await getDERGridScores(lat, lon, derType, iso)
    } catch (err: any) {
      derGridScores.value = null
      const status = err?.response?.status
      const detail = err?.response?.data?.detail
      derViewerError.value = detail
        ? `${status}: ${detail}`
        : err?.message || 'Failed to load DER grid scores'
      console.error('[DER Viewer] loadDERGridScores failed:', { lat, lon, derType, status, detail, err })
    } finally {
      isDERViewerLoading.value = false
    }
  }

  function clearDERViewer() {
    derGridScores.value = null
    derViewerError.value = null
    selectedViewerDERType.value = 'solar'
  }

  function clearNearby() {
    nearbyFeeders.value = []
    nearbyQueueProjects.value = []
    utilityFilingsList.value = []
    selectedHCProfile.value = null
  }

  return {
    // HC state
    hcUtilities, hcFeeders, selectedUtility, selectedFeeder, hcSummary,
    isLoading, filterConstraint, filterMinCapacity,
    constraintTypes, filteredFeeders, utilitiesForSelectedISO,
    // HC actions
    loadUtilities, loadFeeders, selectFeederItem, exportGeoJSON, clearHC,
    // WattCarbon state
    assets, selectedAsset, retroResult,
    // WattCarbon actions
    loadAssets, selectAsset, runRetrospective,
    // Nearby state
    nearbyFeeders, nearbyQueueProjects, utilityFilingsList, isNearbyLoading,
    // Nearby actions
    loadNearbyHC, loadNearbyQueue, loadFilings, clearNearby,
    // HC Profile state
    selectedHCProfile, isHCProfileLoading,
    // HC Profile actions
    loadHCProfile,
    // DER Viewer state
    derGridScores, selectedViewerDERType, isDERViewerLoading, derViewerError,
    // DER Viewer actions
    loadDERGridScores, clearDERViewer,
  }
})
