<template>
  <div v-if="wcStore.isLoading" class="text-center pa-4">
    <v-progress-circular indeterminate color="primary" size="32" />
  </div>

  <div v-else-if="asset">
    <h3 class="text-h6 mb-2">WattCarbon Asset</h3>
    <p class="text-body-2 text-medium-emphasis mb-3">
      {{ asset.wattcarbon_asset_id ?? `#${asset.id}` }}
    </p>

    <!-- Asset Info -->
    <v-table density="compact" class="mb-4">
      <tbody>
        <tr>
          <td class="text-medium-emphasis">DER Type</td>
          <td class="text-right">{{ asset.der_type }}</td>
        </tr>
        <tr>
          <td class="text-medium-emphasis">Capacity</td>
          <td class="text-right">{{ asset.capacity_mw }} MW</td>
        </tr>
        <tr v-if="asset.eac_category">
          <td class="text-medium-emphasis">EAC Category</td>
          <td class="text-right">{{ asset.eac_category }}</td>
        </tr>
        <tr v-if="asset.iso_code">
          <td class="text-medium-emphasis">ISO</td>
          <td class="text-right">{{ asset.iso_code.toUpperCase() }}</td>
        </tr>
        <tr v-if="asset.zone_code">
          <td class="text-medium-emphasis">Zone</td>
          <td class="text-right">{{ asset.zone_code }}</td>
        </tr>
        <tr v-if="asset.substation_name">
          <td class="text-medium-emphasis">Substation</td>
          <td class="text-right">{{ asset.substation_name }}</td>
        </tr>
        <tr v-if="asset.nearest_pnode_name">
          <td class="text-medium-emphasis">Nearest Pnode</td>
          <td class="text-right">
            {{ asset.nearest_pnode_name }}
            <span v-if="asset.pnode_distance_km" class="text-caption text-medium-emphasis">
              ({{ asset.pnode_distance_km.toFixed(1) }} km)
            </span>
          </td>
        </tr>
      </tbody>
    </v-table>

    <!-- Prospective Valuation -->
    <div v-if="asset.latest_valuation" class="mb-4">
      <v-divider class="mb-3" />
      <h4 class="text-subtitle-2 mb-2">Prospective Valuation</h4>

      <div class="d-flex align-center ga-2 mb-2">
        <span class="text-h5 font-weight-bold">
          ${{ asset.latest_valuation.total_constraint_relief_value.toFixed(0) }}
        </span>
        <v-chip
          :color="tierColor(asset.latest_valuation.value_tier)"
          size="small"
          variant="flat"
        >
          {{ asset.latest_valuation.value_tier }}
        </v-chip>
      </div>

      <div class="text-body-2 text-medium-emphasis mb-2">
        Coincidence factor: {{ (asset.latest_valuation.coincidence_factor * 100).toFixed(0) }}%
      </div>

      <!-- Value breakdown bar -->
      <div v-if="breakdownItems.length > 0" class="mb-2">
        <div class="text-caption text-medium-emphasis mb-1">Value Breakdown</div>
        <div class="d-flex" style="height: 14px; border-radius: 3px; overflow: hidden;">
          <div
            v-for="item in breakdownItems"
            :key="item.label"
            :style="{
              width: item.pct + '%',
              background: item.color,
              minWidth: item.pct > 0 ? '3px' : '0',
            }"
            :title="`${item.label}: $${item.value.toFixed(0)}`"
          />
        </div>
        <div class="d-flex flex-wrap ga-2 mt-1">
          <span v-for="item in breakdownItems" :key="item.label" class="text-caption">
            <span :style="{ color: item.color }">&#9679;</span>
            {{ item.label }} (${{ item.value.toFixed(0) }})
          </span>
        </div>
      </div>
    </div>

    <!-- Retrospective Performance -->
    <div v-if="asset.latest_retrospective" class="mb-4">
      <v-divider class="mb-3" />
      <h4 class="text-subtitle-2 mb-2">Retrospective Performance</h4>

      <v-table density="compact" class="mb-3">
        <tbody>
          <tr v-if="asset.latest_retrospective.retrospective_start">
            <td class="text-medium-emphasis">Period</td>
            <td class="text-right">
              {{ formatDate(asset.latest_retrospective.retrospective_start) }}
              - {{ formatDate(asset.latest_retrospective.retrospective_end) }}
            </td>
          </tr>
          <tr>
            <td class="text-medium-emphasis">Actual Savings</td>
            <td class="text-right">{{ asset.latest_retrospective.actual_savings_mwh.toFixed(1) }} MWh</td>
          </tr>
          <tr>
            <td class="text-medium-emphasis">Actual Value</td>
            <td class="text-right font-weight-bold">
              ${{ asset.latest_retrospective.actual_constraint_relief_value.toFixed(0) }}
            </td>
          </tr>
        </tbody>
      </v-table>

      <!-- Actual vs Projected comparison -->
      <div v-if="asset.latest_valuation" class="mb-2">
        <div class="text-caption text-medium-emphasis mb-1">Actual vs. Projected</div>
        <div class="d-flex align-center ga-2 mb-1">
          <span class="text-caption" style="width: 60px;">Projected</span>
          <div style="flex: 1; height: 12px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
            <div
              :style="{
                width: projectedBarPct + '%',
                height: '100%',
                background: '#3498db',
                borderRadius: '3px',
              }"
            />
          </div>
          <span class="text-caption" style="width: 50px; text-align: right;">
            ${{ asset.latest_valuation.total_constraint_relief_value.toFixed(0) }}
          </span>
        </div>
        <div class="d-flex align-center ga-2">
          <span class="text-caption" style="width: 60px;">Actual</span>
          <div style="flex: 1; height: 12px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
            <div
              :style="{
                width: actualBarPct + '%',
                height: '100%',
                background: actualVsProjectedColor,
                borderRadius: '3px',
              }"
            />
          </div>
          <span class="text-caption" style="width: 50px; text-align: right;">
            ${{ asset.latest_retrospective.actual_constraint_relief_value.toFixed(0) }}
          </span>
        </div>
      </div>
    </div>

    <!-- Run Retrospective -->
    <div class="mb-4">
      <v-divider class="mb-3" />
      <h4 class="text-subtitle-2 mb-2">Run Retrospective</h4>

      <v-text-field
        v-model="retroStart"
        label="Start Date"
        type="date"
        density="compact"
        variant="outlined"
        class="mb-2"
      />
      <v-text-field
        v-model="retroEnd"
        label="End Date"
        type="date"
        density="compact"
        variant="outlined"
        class="mb-2"
      />
      <v-btn
        color="primary"
        variant="flat"
        size="small"
        :disabled="!retroStart || !retroEnd || wcStore.isLoading"
        :loading="wcStore.isLoading"
        @click="onRunRetro"
      >
        Compute Retrospective
      </v-btn>

      <v-alert
        v-if="retroError"
        type="error"
        density="compact"
        class="mt-2"
        closable
      >
        {{ retroError }}
      </v-alert>
    </div>
  </div>

  <div v-else class="text-center text-medium-emphasis pa-4">
    Click a WattCarbon asset on the map to see details
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useWattCarbonStore } from '@/stores/wattcarbonStore'

const wcStore = useWattCarbonStore()

const retroStart = ref('')
const retroEnd = ref('')
const retroError = ref('')

const asset = computed(() => wcStore.selectedAsset)

const breakdownItems = computed(() => {
  const bd = asset.value?.latest_valuation?.value_breakdown
  if (!bd) return []
  const colors: Record<string, string> = {
    zone_congestion: '#e74c3c',
    pnode: '#e67e22',
    substation_loading: '#f1c40f',
    feeder_capacity: '#2ecc71',
  }
  const total = Object.values(bd).reduce((s, v) => s + Math.abs(v as number), 0) || 1
  return Object.entries(bd).map(([key, value]) => ({
    label: key.replace(/_/g, ' '),
    value: value as number,
    pct: (Math.abs(value as number) / total) * 100,
    color: colors[key] ?? '#95a5a6',
  }))
})

const projectedBarPct = computed(() => {
  if (!asset.value?.latest_valuation || !asset.value?.latest_retrospective) return 0
  const max = Math.max(
    asset.value.latest_valuation.total_constraint_relief_value,
    asset.value.latest_retrospective.actual_constraint_relief_value,
  )
  return max > 0 ? (asset.value.latest_valuation.total_constraint_relief_value / max) * 100 : 0
})

const actualBarPct = computed(() => {
  if (!asset.value?.latest_valuation || !asset.value?.latest_retrospective) return 0
  const max = Math.max(
    asset.value.latest_valuation.total_constraint_relief_value,
    asset.value.latest_retrospective.actual_constraint_relief_value,
  )
  return max > 0 ? (asset.value.latest_retrospective.actual_constraint_relief_value / max) * 100 : 0
})

const actualVsProjectedColor = computed(() => {
  if (!asset.value?.latest_valuation || !asset.value?.latest_retrospective) return '#2ecc71'
  const ratio = asset.value.latest_retrospective.actual_constraint_relief_value /
    (asset.value.latest_valuation.total_constraint_relief_value || 1)
  if (ratio >= 0.9) return '#2ecc71'
  if (ratio >= 0.7) return '#f1c40f'
  return '#e74c3c'
})

function tierColor(tier: string): string {
  const colors: Record<string, string> = {
    premium: '#c0392b',
    high: '#e67e22',
    moderate: '#f1c40f',
    low: '#27ae60',
  }
  // Handle both "Tier 1" and "premium" formats
  const normalized = tier.toLowerCase()
  if (normalized.includes('1') || normalized === 'premium') return colors.premium
  if (normalized.includes('2') || normalized === 'high') return colors.high
  if (normalized.includes('3') || normalized === 'moderate') return colors.moderate
  return colors.low
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

async function onRunRetro() {
  if (!asset.value?.wattcarbon_asset_id || !retroStart.value || !retroEnd.value) return
  retroError.value = ''
  try {
    await wcStore.runRetrospective(asset.value.wattcarbon_asset_id, retroStart.value, retroEnd.value)
  } catch (e: any) {
    retroError.value = e?.response?.data?.detail ?? e?.message ?? 'Retrospective computation failed'
  }
}
</script>
