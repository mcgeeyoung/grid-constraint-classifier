import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchBAs,
  fetchScores,
  fetchBAScores,
  fetchDurationCurve,
  type BA,
  type CongestionScore,
  type DurationCurve,
} from '@/api/congestion'

export const useCongestionStore = defineStore('congestion', () => {
  const bas = ref<BA[]>([])
  const annualScores = ref<CongestionScore[]>([])
  const selectedBACode = ref<string | null>(null)
  const selectedBAMonthly = ref<CongestionScore[]>([])
  const selectedBADuration = ref<DurationCurve | null>(null)
  const isLoading = ref(false)
  const isDetailLoading = ref(false)
  const year = ref(2024)

  // Non-RTO BAs with lat/lon for map display
  const mappableBAs = computed(() => {
    return bas.value.filter(
      (b) => !b.is_rto && b.latitude != null && b.longitude != null,
    )
  })

  // Scores keyed by ba_code for fast lookup
  const scoresByBA = computed(() => {
    const map = new Map<string, CongestionScore>()
    for (const s of annualScores.value) {
      map.set(s.ba_code, s)
    }
    return map
  })

  // Selected BA detail object
  const selectedBA = computed(() => {
    if (!selectedBACode.value) return null
    return bas.value.find((b) => b.ba_code === selectedBACode.value) ?? null
  })

  const selectedBAScore = computed(() => {
    if (!selectedBACode.value) return null
    return scoresByBA.value.get(selectedBACode.value) ?? null
  })

  async function loadData() {
    isLoading.value = true
    try {
      const [baData, scoreData] = await Promise.all([
        fetchBAs(),
        fetchScores('year', year.value),
      ])
      bas.value = baData
      annualScores.value = scoreData
    } finally {
      isLoading.value = false
    }
  }

  async function selectBA(baCode: string) {
    selectedBACode.value = baCode
    isDetailLoading.value = true
    try {
      const [monthly, duration] = await Promise.all([
        fetchBAScores(baCode, 'month', year.value),
        fetchDurationCurve(baCode, year.value).catch(() => null),
      ])
      selectedBAMonthly.value = monthly
      selectedBADuration.value = duration
    } finally {
      isDetailLoading.value = false
    }
  }

  function clearSelection() {
    selectedBACode.value = null
    selectedBAMonthly.value = []
    selectedBADuration.value = null
  }

  return {
    bas,
    annualScores,
    selectedBACode,
    selectedBAMonthly,
    selectedBADuration,
    isLoading,
    isDetailLoading,
    year,
    mappableBAs,
    scoresByBA,
    selectedBA,
    selectedBAScore,
    loadData,
    selectBA,
    clearSelection,
  }
})
