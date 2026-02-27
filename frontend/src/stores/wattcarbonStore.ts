import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchWattCarbonAssets,
  fetchWattCarbonAssetDetail,
  runRetrospectiveValuation,
  type WattCarbonAsset,
  type WattCarbonAssetDetail,
  type RetrospectiveValuation,
} from '@/api/wattcarbon'

export const useWattCarbonStore = defineStore('wattcarbon', () => {
  const assets = ref<WattCarbonAsset[]>([])
  const selectedAsset = ref<WattCarbonAssetDetail | null>(null)
  const isLoading = ref(false)
  const retroResult = ref<RetrospectiveValuation | null>(null)

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
      // Refresh asset detail to get updated latest_retrospective
      selectedAsset.value = await fetchWattCarbonAssetDetail(assetId)
    } finally {
      isLoading.value = false
    }
  }

  function clear() {
    assets.value = []
    selectedAsset.value = null
    retroResult.value = null
  }

  return {
    assets,
    selectedAsset,
    isLoading,
    retroResult,
    loadAssets,
    selectAsset,
    runRetrospective,
    clear,
  }
})
