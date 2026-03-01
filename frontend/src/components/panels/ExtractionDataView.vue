<template>
  <div>
    <!-- Grid Constraints -->
    <template v-if="extractionType === 'grid_constraint'">
      <div class="text-caption text-medium-emphasis mb-2">
        {{ data.utility || 'Unknown utility' }}
        <span v-if="data.document_context"> &middot; {{ data.document_context }}</span>
      </div>
      <v-table density="compact" class="text-caption">
        <thead>
          <tr>
            <th>Location</th>
            <th>Type</th>
            <th class="text-right">Capacity MW</th>
            <th class="text-right">Load MW</th>
            <th class="text-right">Headroom MW</th>
            <th>Year</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(c, i) in (data.constraints || [])" :key="i">
            <td>{{ c.location_name || '-' }}</td>
            <td>{{ c.constraint_type || '-' }}</td>
            <td class="text-right">{{ fmt(c.current_capacity_mw) }}</td>
            <td class="text-right">{{ fmt(c.forecasted_load_mw) }}</td>
            <td class="text-right">{{ fmt(c.headroom_mw) }}</td>
            <td>{{ c.constraint_year || '-' }}</td>
          </tr>
        </tbody>
      </v-table>
    </template>

    <!-- Load Forecasts -->
    <template v-else-if="extractionType === 'load_forecast'">
      <div class="text-caption text-medium-emphasis mb-2">
        {{ data.utility || 'Unknown utility' }}
        <span v-if="data.area_name"> &middot; {{ data.area_name }} ({{ data.area_type || '?' }})</span>
      </div>
      <div v-for="(scenario, si) in (data.scenarios || [])" :key="si" class="mb-3">
        <div class="text-caption font-weight-medium mb-1">{{ scenario.name || `Scenario ${si + 1}` }}</div>
        <v-table density="compact" class="text-caption">
          <thead>
            <tr>
              <th>Year</th>
              <th class="text-right">Peak MW</th>
              <th class="text-right">Energy GWh</th>
              <th class="text-right">Growth %</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(dp, di) in (scenario.data || [])" :key="di">
              <td>{{ dp.year || '-' }}</td>
              <td class="text-right">{{ fmt(dp.peak_demand_mw) }}</td>
              <td class="text-right">{{ fmt(dp.energy_gwh) }}</td>
              <td class="text-right">{{ fmt(dp.growth_rate_pct) }}</td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </template>

    <!-- Resource Needs -->
    <template v-else-if="extractionType === 'resource_need'">
      <div class="text-caption text-medium-emphasis mb-2">
        {{ data.utility || 'Unknown utility' }}
        <span v-if="data.planning_horizon"> &middot; Horizon: {{ data.planning_horizon }}</span>
      </div>
      <v-table density="compact" class="text-caption">
        <thead>
          <tr>
            <th>Need Type</th>
            <th class="text-right">MW</th>
            <th>Year</th>
            <th>Location</th>
            <th>Eligible Resources</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(n, i) in (data.needs || [])" :key="i">
            <td>{{ n.need_type || '-' }}</td>
            <td class="text-right">{{ fmt(n.need_mw) }}</td>
            <td>{{ n.need_year || '-' }}</td>
            <td>{{ n.location_name || '-' }}</td>
            <td>{{ (n.eligible_resource_types || []).join(', ') || '-' }}</td>
          </tr>
        </tbody>
      </v-table>
    </template>

    <!-- Hosting Capacity -->
    <template v-else-if="extractionType === 'hosting_capacity'">
      <div class="text-caption text-medium-emphasis mb-2">
        {{ data.utility || 'Unknown utility' }}
        <span v-if="data.data_date"> &middot; {{ data.data_date }}</span>
      </div>
      <v-table density="compact" class="text-caption">
        <thead>
          <tr>
            <th>Feeder</th>
            <th>Substation</th>
            <th class="text-right">HC MW</th>
            <th class="text-right">DG MW</th>
            <th class="text-right">Remaining MW</th>
            <th>Constraint</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in (data.records || [])" :key="i">
            <td>{{ r.feeder_id || '-' }}</td>
            <td>{{ r.substation_name || '-' }}</td>
            <td class="text-right">{{ fmt(r.hosting_capacity_mw) }}</td>
            <td class="text-right">{{ fmt(r.installed_dg_mw) }}</td>
            <td class="text-right">{{ fmt(r.remaining_capacity_mw) }}</td>
            <td>{{ r.constraining_factor || '-' }}</td>
          </tr>
        </tbody>
      </v-table>
    </template>

    <!-- General Summary -->
    <template v-else-if="extractionType === 'general_summary'">
      <div class="text-caption text-medium-emphasis mb-2">
        {{ data.utility || 'Unknown utility' }}
        <span v-if="data.document_type"> &middot; {{ data.document_type }}</span>
        <span v-if="data.filing_date"> &middot; {{ data.filing_date }}</span>
      </div>
      <div v-if="data.key_findings" class="mb-2">
        <div class="text-caption font-weight-medium mb-1">Key Findings</div>
        <ul class="text-caption pl-4">
          <li v-for="(f, i) in data.key_findings" :key="i">{{ f }}</li>
        </ul>
      </div>
      <div v-if="data.der_relevance" class="text-caption mb-1">
        <strong>DER Relevance:</strong> {{ data.der_relevance }}
      </div>
      <div v-if="data.recommended_extraction_types?.length" class="text-caption">
        <strong>Recommended extractions:</strong>
        {{ data.recommended_extraction_types.join(', ') }}
      </div>
    </template>

    <!-- Fallback: raw JSON -->
    <template v-else>
      <pre class="text-caption pa-2 rounded" style="background: #f5f5f5; overflow-x: auto;">{{ JSON.stringify(data, null, 2) }}</pre>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  extractionType: string
  data: Record<string, any>
}>()

function fmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString(undefined, { maximumFractionDigits: 2 })
}
</script>
