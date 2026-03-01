import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ReviewItem, ReviewDetail, ReviewStats } from '@/api/review'
import {
  fetchReviewQueue,
  fetchReviewStats,
  fetchReviewItem,
  approveItem,
  rejectItem,
  editAndApprove,
} from '@/api/review'

export const useReviewStore = defineStore('review', () => {
  const items = ref<ReviewItem[]>([])
  const stats = ref<ReviewStats | null>(null)
  const selectedItem = ref<ReviewDetail | null>(null)
  const isLoading = ref(false)
  const statusFilter = ref('pending')
  const typeFilter = ref<string | null>(null)

  const pendingCount = computed(() => stats.value?.pending ?? 0)

  async function loadQueue() {
    isLoading.value = true
    try {
      const params: Record<string, string | number> = {}
      if (statusFilter.value) params.status = statusFilter.value
      if (typeFilter.value) params.extraction_type = typeFilter.value
      items.value = await fetchReviewQueue(params)
    } finally {
      isLoading.value = false
    }
  }

  async function loadStats() {
    stats.value = await fetchReviewStats()
  }

  async function selectItem(id: number) {
    isLoading.value = true
    try {
      selectedItem.value = await fetchReviewItem(id)
    } finally {
      isLoading.value = false
    }
  }

  async function approve(id: number, notes?: string) {
    const result = await approveItem(id, notes)
    selectedItem.value = result
    await loadQueue()
    await loadStats()
  }

  async function reject(id: number, notes?: string) {
    const result = await rejectItem(id, notes)
    selectedItem.value = result
    await loadQueue()
    await loadStats()
  }

  async function editApprove(id: number, data: Record<string, any>, notes?: string) {
    const result = await editAndApprove(id, data, notes)
    selectedItem.value = result
    await loadQueue()
    await loadStats()
  }

  function clearSelection() {
    selectedItem.value = null
  }

  return {
    items,
    stats,
    selectedItem,
    isLoading,
    statusFilter,
    typeFilter,
    pendingCount,
    loadQueue,
    loadStats,
    selectItem,
    approve,
    reject,
    editApprove,
    clearSelection,
  }
})
