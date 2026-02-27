<template>
  <l-circle-marker
    v-for="asset in visibleAssets"
    :key="asset.id"
    :lat-lng="[asset.lat!, asset.lon!]"
    :radius="7"
    :color="'#fff'"
    :fill-color="tierColor(asset)"
    :fill-opacity="0.9"
    :weight="2"
    @click="onAssetClick(asset)"
  >
    <l-popup>
      <div style="font-size: 12px; min-width: 180px;">
        <strong>WattCarbon Asset</strong><br />
        ID: {{ asset.wattcarbon_asset_id ?? asset.id }}<br />
        Type: {{ asset.der_type }}<br />
        Capacity: {{ asset.capacity_mw }} MW<br />
        <span v-if="asset.zone_code">Zone: {{ asset.zone_code }}<br /></span>
        <span v-if="asset.eac_category">EAC: {{ asset.eac_category }}</span>
      </div>
    </l-popup>
  </l-circle-marker>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { LCircleMarker, LPopup } from '@vue-leaflet/vue-leaflet'
import { useWattCarbonStore } from '@/stores/wattcarbonStore'
import { useIsoStore } from '@/stores/isoStore'
import { useMapStore } from '@/stores/mapStore'
import type { WattCarbonAsset } from '@/api/wattcarbon'

const wcStore = useWattCarbonStore()
const isoStore = useIsoStore()
const mapStore = useMapStore()

const visibleAssets = computed(() => {
  return wcStore.assets.filter(a => a.lat != null && a.lon != null)
})

watch(() => isoStore.selectedISO, async (iso) => {
  if (iso) {
    try {
      await wcStore.loadAssets(iso)
    } catch {
      // WattCarbon assets may not be available
    }
  } else {
    wcStore.clear()
  }
}, { immediate: true })

function tierColor(asset: WattCarbonAsset): string {
  // Use the value tier from latest valuation if available from the detail
  // For list view, color by DER type as a visual distinguisher
  const typeColors: Record<string, string> = {
    solar: '#f39c12',
    storage: '#8e44ad',
    demand_response: '#2980b9',
    wind: '#1abc9c',
    ev_charger: '#e74c3c',
  }
  return typeColors[asset.der_type] ?? '#3498db'
}

function onAssetClick(asset: WattCarbonAsset) {
  if (asset.wattcarbon_asset_id) {
    mapStore.selectedAssetId = asset.wattcarbon_asset_id
    wcStore.selectAsset(asset.wattcarbon_asset_id)
  }
}
</script>
