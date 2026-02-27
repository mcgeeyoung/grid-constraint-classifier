<template>
  <v-container fluid class="pa-6">
    <h1 class="text-h5 mb-4">Cross-ISO Overview</h1>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <template v-else>
      <!-- Summary cards row -->
      <v-row class="mb-4">
        <v-col cols="12" sm="6" md="3">
          <v-card class="pa-4 text-center" color="surface" variant="outlined">
            <div class="text-h4 font-weight-bold text-primary">{{ totalISOs }}</div>
            <div class="text-caption text-medium-emphasis">ISOs Analyzed</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card class="pa-4 text-center" color="surface" variant="outlined">
            <div class="text-h4 font-weight-bold" style="color: #e74c3c;">{{ totalConstrained }}</div>
            <div class="text-caption text-medium-emphasis">Constrained Zones</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card class="pa-4 text-center" color="surface" variant="outlined">
            <div class="text-h4 font-weight-bold" style="color: #2ecc71;">{{ formatCurrency(totalPortfolioValue) }}</div>
            <div class="text-caption text-medium-emphasis">Total Portfolio Value</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card class="pa-4 text-center" color="surface" variant="outlined">
            <div class="text-h4 font-weight-bold" style="color: #f1c40f;">{{ totalDERs }}</div>
            <div class="text-caption text-medium-emphasis">DER Locations</div>
          </v-card>
        </v-col>
      </v-row>

      <!-- Per-ISO cards -->
      <v-row>
        <v-col v-for="vs in valueSummaries" :key="vs.iso_code" cols="12" md="6" lg="4">
          <v-card variant="outlined" class="pa-4">
            <!-- Header -->
            <div class="d-flex align-center justify-space-between mb-3">
              <div>
                <v-chip
                  size="small"
                  color="primary"
                  variant="flat"
                  @click="goToISO(vs.iso_code)"
                  style="cursor: pointer;"
                >
                  {{ vs.iso_code.toUpperCase() }}
                </v-chip>
                <span class="text-body-2 ml-2">{{ vs.iso_name }}</span>
              </div>
              <v-chip
                v-if="vs.avg_value_per_kw_year > 0"
                size="small"
                :color="tierColor(avgTier(vs.avg_value_per_kw_year))"
                variant="flat"
              >
                ${{ vs.avg_value_per_kw_year.toFixed(0) }}/kW-yr
              </v-chip>
            </div>

            <!-- Stats grid -->
            <v-row dense class="mb-3">
              <v-col cols="6">
                <div class="text-caption text-medium-emphasis">Zones</div>
                <div class="text-body-1">
                  {{ vs.total_zones }}
                  <span v-if="vs.constrained_zones" class="text-caption" style="color: #e74c3c;">
                    ({{ vs.constrained_zones }} constrained)
                  </span>
                </div>
              </v-col>
              <v-col cols="6">
                <div class="text-caption text-medium-emphasis">Substations</div>
                <div class="text-body-1">
                  {{ vs.total_substations }}
                  <span v-if="vs.overloaded_substations" class="text-caption" style="color: #e67e22;">
                    ({{ vs.overloaded_substations }} overloaded)
                  </span>
                </div>
              </v-col>
              <v-col cols="6">
                <div class="text-caption text-medium-emphasis">DER Locations</div>
                <div class="text-body-1">{{ vs.total_der_locations }}</div>
              </v-col>
              <v-col cols="6">
                <div class="text-caption text-medium-emphasis">Portfolio Value</div>
                <div class="text-body-1">${{ formatNumber(vs.total_portfolio_value) }}</div>
              </v-col>
            </v-row>

            <!-- Tier distribution bar -->
            <div v-if="totalTierCount(vs) > 0" class="mb-3">
              <div class="text-caption text-medium-emphasis mb-1">Value Tier Distribution</div>
              <div class="d-flex" style="height: 16px; border-radius: 4px; overflow: hidden;">
                <div
                  v-for="tier in tierOrder"
                  :key="tier"
                  v-show="vs.tier_distribution[tier]"
                  :style="{
                    width: ((vs.tier_distribution[tier] || 0) / totalTierCount(vs) * 100) + '%',
                    background: tierColor(tier),
                    minWidth: vs.tier_distribution[tier] ? '4px' : '0',
                  }"
                  :title="`${tier}: ${vs.tier_distribution[tier] || 0}`"
                />
              </div>
              <div class="d-flex ga-3 mt-1">
                <span v-for="tier in tierOrder" :key="tier" v-show="vs.tier_distribution[tier]" class="text-caption">
                  <span :style="{ color: tierColor(tier) }">&#9679;</span>
                  {{ tier }} ({{ vs.tier_distribution[tier] || 0 }})
                </span>
              </div>
            </div>

            <!-- Top zones -->
            <div v-if="vs.top_zones.length > 0">
              <div class="text-caption text-medium-emphasis mb-1">Top Zones by Value</div>
              <v-table density="compact">
                <tbody>
                  <tr v-for="tz in vs.top_zones" :key="tz.zone_code">
                    <td class="text-body-2 pa-1">{{ tz.zone_code }}</td>
                    <td class="text-body-2 text-medium-emphasis pa-1">{{ tz.zone_name || '' }}</td>
                    <td class="text-body-2 text-right pa-1">${{ formatNumber(tz.avg_constraint_value) }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>

            <!-- Empty state -->
            <div v-if="vs.total_der_locations === 0 && vs.total_zones === 0" class="text-center text-medium-emphasis py-2">
              No data available
            </div>
          </v-card>
        </v-col>
      </v-row>

      <!-- Classification overview table (preserved from original) -->
      <h2 class="text-h6 mt-6 mb-3">Classification Breakdown</h2>
      <v-table density="comfortable">
        <thead>
          <tr>
            <th>ISO</th>
            <th>Name</th>
            <th class="text-right">Zones</th>
            <th class="text-right">Transmission</th>
            <th class="text-right">Generation</th>
            <th class="text-right">Both</th>
            <th class="text-right">Unconstrained</th>
            <th class="text-right">Latest Run</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in overviewData" :key="row.iso_code">
            <td>
              <v-chip
                size="small"
                color="primary"
                variant="outlined"
                @click="goToISO(row.iso_code)"
                style="cursor: pointer;"
              >
                {{ row.iso_code.toUpperCase() }}
              </v-chip>
            </td>
            <td>{{ row.iso_name }}</td>
            <td class="text-right">{{ row.zones_count }}</td>
            <td class="text-right">
              <v-chip v-if="row.transmission_constrained" size="x-small" color="#e74c3c" variant="flat">
                {{ row.transmission_constrained }}
              </v-chip>
              <span v-else class="text-medium-emphasis">0</span>
            </td>
            <td class="text-right">
              <v-chip v-if="row.generation_constrained" size="x-small" color="#3498db" variant="flat">
                {{ row.generation_constrained }}
              </v-chip>
              <span v-else class="text-medium-emphasis">0</span>
            </td>
            <td class="text-right">
              <v-chip v-if="row.both_constrained" size="x-small" color="#9b59b6" variant="flat">
                {{ row.both_constrained }}
              </v-chip>
              <span v-else class="text-medium-emphasis">0</span>
            </td>
            <td class="text-right">
              <v-chip v-if="row.unconstrained" size="x-small" color="#2ecc71" variant="flat">
                {{ row.unconstrained }}
              </v-chip>
              <span v-else class="text-medium-emphasis">0</span>
            </td>
            <td class="text-right">{{ row.latest_run_year ?? '-' }}</td>
            <td>
              <v-chip
                v-if="row.latest_run_status"
                size="x-small"
                :color="row.latest_run_status === 'completed' ? 'success' : 'warning'"
                variant="flat"
              >
                {{ row.latest_run_status }}
              </v-chip>
              <span v-else class="text-medium-emphasis">-</span>
            </td>
          </tr>
        </tbody>
      </v-table>
    </template>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchOverview, fetchOverviewValues, type Overview, type ValueSummary } from '@/api/isos'
import { useIsoStore } from '@/stores/isoStore'

const router = useRouter()
const isoStore = useIsoStore()

const overviewData = ref<Overview[]>([])
const valueSummaries = ref<ValueSummary[]>([])
const loading = ref(true)

const tierOrder = ['premium', 'high', 'moderate', 'low']

onMounted(async () => {
  try {
    const [overview, values] = await Promise.all([
      fetchOverview(),
      fetchOverviewValues(),
    ])
    overviewData.value = overview
    valueSummaries.value = values
  } finally {
    loading.value = false
  }
})

const totalISOs = computed(() => valueSummaries.value.length)
const totalConstrained = computed(() => valueSummaries.value.reduce((s, v) => s + v.constrained_zones, 0))
const totalPortfolioValue = computed(() => valueSummaries.value.reduce((s, v) => s + v.total_portfolio_value, 0))
const totalDERs = computed(() => valueSummaries.value.reduce((s, v) => s + v.total_der_locations, 0))

function totalTierCount(vs: ValueSummary): number {
  return Object.values(vs.tier_distribution).reduce((s, n) => s + n, 0)
}

function avgTier(value: number): string {
  if (value >= 150) return 'premium'
  if (value >= 80) return 'high'
  if (value >= 30) return 'moderate'
  return 'low'
}

function tierColor(tier: string): string {
  switch (tier) {
    case 'premium': return '#c0392b'
    case 'high': return '#e67e22'
    case 'moderate': return '#f1c40f'
    case 'low': return '#27ae60'
    default: return '#666'
  }
}

function formatCurrency(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`
  return `$${value.toFixed(0)}`
}

function formatNumber(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return value.toFixed(0)
}

async function goToISO(isoCode: string) {
  await isoStore.selectISO(isoCode)
  router.push('/')
}
</script>
