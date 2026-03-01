<template>
  <v-app-bar density="compact" color="surface">
    <v-app-bar-title>
      <router-link to="/" class="text-decoration-none text-white">
        Grid Constraint Classifier
      </router-link>
    </v-app-bar-title>

    <!-- Search -->
    <v-autocomplete
      v-model="selectedResult"
      :items="searchResults"
      :search="searchQuery"
      @update:search="searchQuery = $event ?? ''"
      item-title="label"
      item-value="id"
      placeholder="Search zones, substations..."
      density="compact"
      variant="outlined"
      hide-details
      clearable
      return-object
      no-filter
      style="max-width: 300px;"
      class="mx-4"
      @update:model-value="onSelect"
    >
      <template v-slot:item="{ item, props }">
        <v-list-item v-bind="props">
          <template v-slot:prepend>
            <v-icon size="16" :color="item.raw.iconColor">{{ item.raw.icon }}</v-icon>
          </template>
        </v-list-item>
      </template>
    </v-autocomplete>

    <template v-slot:append>
      <ISOSelector />
      <v-btn icon to="/review" title="Review Queue">
        <v-icon>mdi-clipboard-check-outline</v-icon>
      </v-btn>
      <v-btn icon to="/congestion" title="Import Congestion">
        <v-icon>mdi-transmission-tower-import</v-icon>
      </v-btn>
      <v-btn icon to="/overview" title="Overview">
        <v-icon>mdi-view-dashboard</v-icon>
      </v-btn>
    </template>
  </v-app-bar>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import ISOSelector from '@/components/panels/ISOSelector.vue'
import { useIsoStore } from '@/stores/isoStore'
import { useHierarchyStore } from '@/stores/hierarchyStore'
import { useMapStore } from '@/stores/mapStore'

const router = useRouter()
const isoStore = useIsoStore()
const hierarchyStore = useHierarchyStore()
const mapStore = useMapStore()

const searchQuery = ref('')
const selectedResult = ref<SearchItem | null>(null)

interface SearchItem {
  id: string
  label: string
  icon: string
  iconColor: string
  type: 'zone' | 'substation'
  code?: string
  lat?: number
  lon?: number
  substationId?: number
}

const searchResults = computed<SearchItem[]>(() => {
  const q = searchQuery.value.toLowerCase().trim()
  if (q.length < 2) return []

  const results: SearchItem[] = []

  // Search zones
  for (const cls of isoStore.classifications) {
    const match = cls.zone_code.toLowerCase().includes(q) ||
      (cls.zone_name?.toLowerCase().includes(q) ?? false)
    if (match) {
      const zone = isoStore.zones.find((z: any) => z.zone_code === cls.zone_code)
      results.push({
        id: `zone-${cls.zone_code}`,
        label: `${cls.zone_code}${cls.zone_name ? ' - ' + cls.zone_name : ''}`,
        icon: 'mdi-map-marker-radius',
        iconColor: classificationColor(cls.classification),
        type: 'zone',
        code: cls.zone_code,
        lat: zone?.centroid_lat ?? undefined,
        lon: zone?.centroid_lon ?? undefined,
      })
    }
    if (results.length >= 20) break
  }

  // Search substations
  for (const sub of hierarchyStore.substations) {
    const match = (sub.substation_name?.toLowerCase().includes(q) ?? false) ||
      (sub.zone_code?.toLowerCase().includes(q) ?? false)
    if (match) {
      results.push({
        id: `sub-${sub.id}`,
        label: sub.substation_name ?? `Substation #${sub.id}`,
        icon: 'mdi-flash',
        iconColor: '#f39c12',
        type: 'substation',
        substationId: sub.id,
        lat: sub.lat ?? undefined,
        lon: sub.lon ?? undefined,
      })
    }
    if (results.length >= 30) break
  }

  return results
})

function classificationColor(cls: string): string {
  switch (cls) {
    case 'transmission': return '#e74c3c'
    case 'generation': return '#3498db'
    case 'both': return '#9b59b6'
    case 'unconstrained': return '#2ecc71'
    default: return 'grey'
  }
}

function onSelect(item: SearchItem | null) {
  if (!item) return

  // Navigate to dashboard if not there
  if (router.currentRoute.value.path !== '/') {
    router.push('/')
  }

  if (item.type === 'zone' && item.code) {
    mapStore.selectedZoneCode = item.code
    if (item.lat != null && item.lon != null) {
      mapStore.panTo(item.lat, item.lon, 7)
    }
  } else if (item.type === 'substation' && item.substationId) {
    mapStore.selectedSubstationId = item.substationId
    hierarchyStore.selectSubstation(item.substationId)
    if (item.lat != null && item.lon != null) {
      mapStore.panTo(item.lat, item.lon, 10)
    }
  }

  // Clear search
  selectedResult.value = null
  searchQuery.value = ''
}
</script>
