<template>
  <v-app-bar density="compact" color="transparent" flat style="background: var(--bg-base) !important; height: 40px;">
    <v-app-bar-title>
      <router-link to="/" class="text-decoration-none" style="color: var(--text-primary);">
        Grid Constraint Classifier
      </router-link>
    </v-app-bar-title>

    <!-- ISO Selector -->
    <v-select
      v-model="currentISO"
      :items="isoItems"
      item-title="label"
      item-value="code"
      placeholder="ISO"
      density="compact"
      variant="solo-filled"
      flat
      hide-details
      style="max-width: 130px;"
      class="mx-2"
      @update:model-value="onSelectISO"
    >
      <template v-slot:prepend-inner>
        <v-icon size="16">mdi-transmission-tower</v-icon>
      </template>
    </v-select>

    <v-spacer />

    <!-- Search -->
    <v-autocomplete
      v-model="selectedResult"
      :items="searchResults"
      :search="searchQuery"
      @update:search="searchQuery = $event ?? ''"
      item-title="label"
      item-value="id"
      placeholder="Search zones..."
      density="compact"
      variant="outlined"
      hide-details
      clearable
      return-object
      no-filter
      bg-color="transparent"
      base-color="rgba(255,255,255,0.6)"
      style="max-width: 300px;"
      class="mx-2"
      prepend-inner-icon="mdi-magnify"
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
      <v-btn icon to="/review" title="Review Queue">
        <v-icon>mdi-clipboard-check-outline</v-icon>
      </v-btn>
    </template>
  </v-app-bar>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useGridDataStore } from '@/stores/gridDataStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { useMapStore } from '@/stores/mapStore'
import { listISOs } from '@/api/constraints'
import { severityTierColor } from '@/utils/tierColors'
import type { ISO } from '@/types/constraints'

const router = useRouter()
const gridStore = useGridDataStore()
const selectionStore = useSelectionStore()
const mapStore = useMapStore()

// ISO selector
const allISOs = ref<ISO[]>([])
const currentISO = ref<string | null>(null)

const isoItems = computed(() =>
  allISOs.value
    .filter(iso => iso.is_rto && iso.iso_code === iso.iso_code.toLowerCase())
    .map(iso => ({ code: iso.iso_code, label: iso.iso_code.toUpperCase() }))
)

watch(() => selectionStore.selectedISO, (val) => {
  currentISO.value = val
})

onMounted(async () => {
  allISOs.value = await listISOs()
  if (selectionStore.selectedISO) {
    currentISO.value = selectionStore.selectedISO
  }
})

function onSelectISO(code: string | null) {
  if (!code) return
  gridStore.selectISO(code)
}

// Search
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

  for (const zone of gridStore.zones) {
    const match = zone.zone_code.toLowerCase().includes(q) ||
      (zone.zone_name?.toLowerCase().includes(q) ?? false)
    if (match) {
      results.push({
        id: `zone-${zone.zone_code}`,
        label: `${zone.zone_code}${zone.zone_name ? ' - ' + zone.zone_name : ''}`,
        icon: 'mdi-map-marker-radius',
        iconColor: severityTierColor(zone.severity_tier),
        type: 'zone',
        code: zone.zone_code,
        lat: zone.centroid_lat ?? undefined,
        lon: zone.centroid_lon ?? undefined,
      })
    }
    if (results.length >= 30) break
  }

  return results
})

function onSelect(item: SearchItem | null) {
  if (!item) return

  if (router.currentRoute.value.path !== '/') {
    router.push('/')
  }

  if (item.type === 'zone' && item.code) {
    selectionStore.selectZone(item.code)
    if (selectionStore.selectedISO) {
      gridStore.loadZoneConstraints(selectionStore.selectedISO, item.code)
    }
    if (item.lat != null && item.lon != null) {
      mapStore.panTo(item.lat, item.lon, 7)
    }
  }

  selectedResult.value = null
  searchQuery.value = ''
}
</script>
