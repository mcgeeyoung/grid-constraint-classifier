import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  listISOs,
  listZones,
  zoneGeometries,
  zoneConstraints,
  resolveLocation as apiResolveLocation,
  fetchDERLocations,
} from '@/api/constraints'
import {
  fetchBAs,
  fetchScores,
  fetchBAScores,
  fetchBAProfile,
  fetchDurationCurve,
  type BA,
  type BAProfile,
  type CongestionScore,
  type DurationCurve,
} from '@/api/congestion'
import {
  fetchSubstations,
  fetchSubstationDetail,
  fetchFeeders,
  fetchSubstationProfile,
  findNearestSubstation,
  type Substation,
  type SubstationDetail,
  type SubstationProfile12x24,
  type Feeder,
} from '@/api/hierarchy'
import type {
  ISO,
  ZoneConstraintSummary,
  ConstraintProfile,
  Annotation,
  PnodeScore,
  GeoResolution,
} from '@/types/constraints'
import { useMapStore } from './mapStore'
import { useSelectionStore } from './selectionStore'

export const ISO_VIEW: Record<string, { lat: number; lng: number; zoom: number }> = {
  caiso: { lat: 37.0, lng: -119.5, zoom: 6 },
  ercot: { lat: 31.0, lng: -97.5, zoom: 6 },
  isone: { lat: 42.5, lng: -72.0, zoom: 7 },
  miso:  { lat: 42.0, lng: -90.0, zoom: 5 },
  nyiso: { lat: 43.0, lng: -75.5, zoom: 7 },
  pjm:   { lat: 39.5, lng: -78.0, zoom: 6 },
  spp:   { lat: 37.5, lng: -97.0, zoom: 5 },
}

export const useGridDataStore = defineStore('gridData', () => {
  // ---- Constraint state (from constraintStore) ----
  const isos = ref<ISO[]>([])
  const isLoading = ref(false)
  const isDetailLoading = ref(false)

  // Per-ISO zone data
  const zonesMap = ref<Record<string, ZoneConstraintSummary[]>>({})
  const zoneGeometriesMap = ref<Record<string, any[]>>({})
  const derLocationsMap = ref<Record<string, any[]>>({})

  // Selected zone detail
  const zoneProfiles = ref<ConstraintProfile[]>([])
  const zoneAnnotations = ref<Annotation[]>([])
  const pnodeHotspots = ref<PnodeScore[]>([])

  // Geo resolution
  const resolvedLocation = ref<GeoResolution | null>(null)

  // ---- Congestion state (from congestionStore) ----
  const bas = ref<BA[]>([])
  const annualCongestionScores = ref<CongestionScore[]>([])
  const selectedBAMonthly = ref<CongestionScore[]>([])
  const selectedBADuration = ref<DurationCurve | null>(null)
  const selectedBAProfile = ref<BAProfile | null>(null)
  const congestionYear = ref(2024)
  const isCongestionLoading = ref(false)

  // ---- Hierarchy state (from hierarchyStore) ----
  const substations = ref<Substation[]>([])
  const selectedSubstationDetail = ref<SubstationDetail | null>(null)
  const substationFeeders = ref<Feeder[]>([])
  const substationProfile = ref<SubstationProfile12x24 | null>(null)
  const isSubstationProfileLoading = ref(false)

  // ---- Computed: constraints ----
  const selectionStore = useSelectionStore()

  const zones = computed(() =>
    selectionStore.selectedISOs.flatMap(iso => zonesMap.value[iso] ?? []),
  )
  const zoneGeometryList = computed(() =>
    selectionStore.selectedISOs.flatMap(iso => zoneGeometriesMap.value[iso] ?? []),
  )
  const derLocations = computed(() =>
    selectionStore.selectedISOs.flatMap(iso => derLocationsMap.value[iso] ?? []),
  )
  const constrainedZones = computed(() =>
    zones.value.filter(z => z.severity_tier && z.severity_tier !== 'low'),
  )

  // ---- Computed: congestion ----
  const mappableBAs = computed(() =>
    bas.value.filter(b => !b.is_rto && b.latitude != null && b.longitude != null),
  )

  const basForSelectedISO = computed(() => {
    const isos = selectionStore.selectedISOs
    if (!isos.length) return []
    return bas.value.filter(b =>
      !b.is_rto &&
      isos.some(iso => b.rto_neighbor?.toLowerCase() === iso)
    )
  })

  const scoresByBA = computed(() => {
    const map = new Map<string, CongestionScore>()
    for (const s of annualCongestionScores.value) {
      map.set(s.ba_code, s)
    }
    return map
  })

  const selectedBA = computed(() => {
    if (!selectionStore.selectedBACode) return null
    return bas.value.find(b => b.ba_code === selectionStore.selectedBACode) ?? null
  })

  const selectedBAScore = computed(() => {
    if (!selectionStore.selectedBACode) return null
    return scoresByBA.value.get(selectionStore.selectedBACode) ?? null
  })

  // ---- Actions: constraints ----
  async function loadISOs() {
    isos.value = await listISOs()
  }

  async function loadISOData(isoCode: string) {
    isLoading.value = true
    try {
      const [z, d] = await Promise.all([
        listZones(isoCode),
        fetchDERLocations(isoCode),
      ])
      zonesMap.value[isoCode] = z
      derLocationsMap.value[isoCode] = d

      zoneGeometries(isoCode).then(g => {
        zoneGeometriesMap.value[isoCode] = g
      }).catch(() => {
        zoneGeometriesMap.value[isoCode] = []
      })
    } finally {
      isLoading.value = false
    }
  }

  async function selectISO(isoCode: string) {
    zonesMap.value = {}
    zoneGeometriesMap.value = {}
    derLocationsMap.value = {}
    selectedSubstationDetail.value = null
    substationFeeders.value = []
    substationProfile.value = null

    selectionStore.selectISO(isoCode)
    await loadISOData(isoCode)

    const view = ISO_VIEW[isoCode]
    if (view) {
      const mapStore = useMapStore()
      mapStore.panTo(view.lat, view.lng, view.zoom)
    }
  }

  async function toggleISO(isoCode: string) {
    const idx = selectionStore.selectedISOs.indexOf(isoCode)
    if (idx >= 0) {
      selectionStore.toggleISO(isoCode)
      delete zonesMap.value[isoCode]
      delete zoneGeometriesMap.value[isoCode]
      delete derLocationsMap.value[isoCode]
      return
    }
    selectionStore.toggleISO(isoCode)
    await loadISOData(isoCode)

    const view = ISO_VIEW[isoCode]
    if (view) {
      const mapStore = useMapStore()
      mapStore.panTo(view.lat, view.lng, view.zoom)
    }
  }

  async function loadZoneConstraints(isoCode: string, zoneCode: string) {
    isDetailLoading.value = true
    try {
      const result = await zoneConstraints(isoCode, zoneCode)
      zoneProfiles.value = result.profiles
      pnodeHotspots.value = result.pnode_hotspots
    } catch {
      zoneProfiles.value = []
      zoneAnnotations.value = []
      pnodeHotspots.value = []
    } finally {
      isDetailLoading.value = false
    }
  }

  async function resolveLocation(lat: number, lon: number) {
    isLoading.value = true
    try {
      resolvedLocation.value = await apiResolveLocation(lat, lon)
    } catch {
      resolvedLocation.value = null
    } finally {
      isLoading.value = false
    }
  }

  function zoneByCode(zoneCode: string): ZoneConstraintSummary | null {
    return zones.value.find(z => z.zone_code === zoneCode) ?? null
  }

  // ---- Actions: congestion ----
  async function loadCongestionData() {
    isCongestionLoading.value = true
    try {
      const [baData, scoreData] = await Promise.all([
        fetchBAs(),
        fetchScores('year', congestionYear.value),
      ])
      bas.value = baData
      annualCongestionScores.value = scoreData
    } finally {
      isCongestionLoading.value = false
    }
  }

  async function selectBA(baCode: string) {
    selectionStore.selectBA(baCode)
    isDetailLoading.value = true
    try {
      const [monthly, duration, profile] = await Promise.all([
        fetchBAScores(baCode, 'month', congestionYear.value),
        fetchDurationCurve(baCode, congestionYear.value).catch(() => null),
        fetchBAProfile(baCode, congestionYear.value).catch(() => null),
      ])
      selectedBAMonthly.value = monthly
      selectedBADuration.value = duration
      selectedBAProfile.value = profile
    } finally {
      isDetailLoading.value = false
    }
  }

  function clearBASelection() {
    selectedBAMonthly.value = []
    selectedBADuration.value = null
    selectedBAProfile.value = null
  }

  // ---- Actions: hierarchy ----
  async function loadSubstations(isoCode: string, zoneCode?: string) {
    isLoading.value = true
    try {
      substations.value = await fetchSubstations(isoCode, zoneCode)
    } finally {
      isLoading.value = false
    }
  }

  async function selectSubstationByLocation(lat: number, lon: number) {
    const match = await findNearestSubstation(lat, lon)
    if (match) {
      await selectSubstation(match.id)
    }
    return match
  }

  async function selectSubstation(substationId: number) {
    selectionStore.selectSubstation(substationId)
    isLoading.value = true
    substationProfile.value = null
    try {
      const [detail, feeders] = await Promise.all([
        fetchSubstationDetail(substationId),
        fetchFeeders(substationId),
      ])
      selectedSubstationDetail.value = detail
      substationFeeders.value = feeders
    } finally {
      isLoading.value = false
    }
    // Load profile in background (non-blocking)
    isSubstationProfileLoading.value = true
    fetchSubstationProfile(substationId)
      .then(p => { substationProfile.value = p })
      .catch(() => { substationProfile.value = null })
      .finally(() => { isSubstationProfileLoading.value = false })
  }

  return {
    // Constraint state
    isos, isLoading, isDetailLoading,
    zonesMap, zoneGeometriesMap, derLocationsMap,
    zoneProfiles, zoneAnnotations, pnodeHotspots,
    resolvedLocation,
    // Constraint computed
    zones, zoneGeometryList, derLocations, constrainedZones,
    // Constraint actions
    loadISOs, loadISOData, selectISO, toggleISO,
    loadZoneConstraints, resolveLocation, zoneByCode,
    // Congestion state
    bas, annualCongestionScores, selectedBAMonthly, selectedBADuration, selectedBAProfile,
    congestionYear, isCongestionLoading,
    // Congestion computed
    mappableBAs, basForSelectedISO, scoresByBA, selectedBA, selectedBAScore,
    // Congestion actions
    loadCongestionData, selectBA, clearBASelection,
    // Hierarchy state
    substations, selectedSubstationDetail, substationFeeders,
    substationProfile, isSubstationProfileLoading,
    // Hierarchy actions
    loadSubstations, selectSubstation, selectSubstationByLocation,
  }
})
