<template>
  <v-container fluid class="pa-6">
    <h1 class="text-h5 mb-4">Cross-ISO Overview</h1>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <v-table v-else density="comfortable">
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
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchOverview, type Overview } from '@/api/isos'
import { useIsoStore } from '@/stores/isoStore'

const router = useRouter()
const isoStore = useIsoStore()

const overviewData = ref<Overview[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    overviewData.value = await fetchOverview()
  } finally {
    loading.value = false
  }
})

function goToISO(isoCode: string) {
  isoStore.selectISO(isoCode)
  router.push('/')
}
</script>
