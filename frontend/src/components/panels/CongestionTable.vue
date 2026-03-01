<template>
  <div>
    <div v-if="store.isLoading" class="text-center pa-4">
      <v-progress-circular indeterminate color="primary" />
    </div>
    <div v-else-if="store.annualScores.length === 0" class="text-center text-medium-emphasis pa-4">
      No congestion scores available
    </div>
    <div v-else>
      <v-table density="compact" hover class="congestion-table">
        <thead>
          <tr>
            <th class="sortable" @click="toggleSort('ba_code')">
              BA {{ sortIcon('ba_code') }}
            </th>
            <th class="sortable text-right" @click="toggleSort('hours_above_80')">
              Hrs>80% {{ sortIcon('hours_above_80') }}
            </th>
            <th class="sortable text-right" @click="toggleSort('pct_hours_importing')">
              Import% {{ sortIcon('pct_hours_importing') }}
            </th>
            <th class="sortable text-right" @click="toggleSort('congestion_opportunity_score')">
              COS {{ sortIcon('congestion_opportunity_score') }}
            </th>
            <th class="text-center">Quality</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in sortedScores"
            :key="row.ba_code"
            :class="{ 'bg-blue-lighten-5': row.ba_code === store.selectedBACode }"
            style="cursor: pointer;"
            @click="store.selectBA(row.ba_code)"
          >
            <td>
              <div class="d-flex align-center ga-1">
                <span
                  :style="{ background: congestionDot(row), width: '8px', height: '8px', borderRadius: '50%', display: 'inline-block' }"
                />
                <span class="text-body-2 font-weight-medium">{{ row.ba_code }}</span>
              </div>
              <div class="text-caption text-medium-emphasis" style="max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ row.ba_name }}
              </div>
            </td>
            <td class="text-right font-weight-medium">{{ row.hours_above_80 ?? '-' }}</td>
            <td class="text-right">{{ pctFmt(row.pct_hours_importing) }}</td>
            <td class="text-right">
              <template v-if="row.congestion_opportunity_score != null">
                ${{ row.congestion_opportunity_score.toFixed(2) }}
              </template>
              <template v-else>-</template>
            </td>
            <td class="text-center">
              <v-chip :color="qualityColor(row.data_quality_flag)" size="x-small" variant="flat">
                {{ row.data_quality_flag ?? '?' }}
              </v-chip>
            </td>
          </tr>
        </tbody>
      </v-table>
      <div class="text-caption text-medium-emphasis pa-2">
        {{ store.annualScores.length }} balancing authorities
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useCongestionStore } from '@/stores/congestionStore'
import type { CongestionScore } from '@/api/congestion'

const store = useCongestionStore()

type SortKey = 'ba_code' | 'hours_above_80' | 'pct_hours_importing' | 'congestion_opportunity_score'
const sortKey = ref<SortKey>('hours_above_80')
const sortAsc = ref(false)

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = key === 'ba_code'
  }
}

function sortIcon(key: SortKey): string {
  if (sortKey.value !== key) return ''
  return sortAsc.value ? '\u25B2' : '\u25BC'
}

const sortedScores = computed(() => {
  const arr = [...store.annualScores]
  const k = sortKey.value
  const dir = sortAsc.value ? 1 : -1
  arr.sort((a, b) => {
    const va = (a as any)[k] ?? -Infinity
    const vb = (b as any)[k] ?? -Infinity
    if (va < vb) return -1 * dir
    if (va > vb) return 1 * dir
    return 0
  })
  return arr
})

function pctFmt(v: number | null): string {
  if (v == null) return '-'
  return (v * 100).toFixed(1) + '%'
}

function congestionDot(row: CongestionScore): string {
  const h80 = row.hours_above_80 ?? 0
  if (h80 >= 1000) return '#c0392b'
  if (h80 >= 500) return '#e74c3c'
  if (h80 >= 200) return '#e67e22'
  if (h80 >= 50) return '#f1c40f'
  return '#2ecc71'
}

function qualityColor(flag: string | null): string {
  switch (flag) {
    case 'good': return 'success'
    case 'partial': return 'warning'
    case 'sparse': return 'error'
    default: return 'grey'
  }
}
</script>

<style scoped>
.sortable {
  cursor: pointer;
  user-select: none;
}
.sortable:hover {
  background: rgba(0, 0, 0, 0.04);
}
.congestion-table td {
  padding-top: 4px !important;
  padding-bottom: 4px !important;
}
</style>
