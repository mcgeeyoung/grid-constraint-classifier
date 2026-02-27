<template>
  <div>
    <h3 class="text-subtitle-1 mb-2">Grid Hierarchy</h3>

    <div v-if="!isoStore.selectedISO" class="text-body-2 text-medium-emphasis">
      Select an ISO to browse the grid hierarchy
    </div>

    <v-treeview
      v-else
      :items="treeItems"
      item-value="id"
      item-title="title"
      :load-children="(loadChildren as any)"
      activatable
      open-on-click
      density="compact"
      @update:activated="(onActivate as any)"
    >
      <template v-slot:prepend="{ item }">
        <v-chip
          v-if="item.tier"
          :color="tierColor(item.tier)"
          size="x-small"
          variant="flat"
          class="mr-1"
        >
          {{ item.tier }}
        </v-chip>
        <v-icon v-else size="small" :color="item.iconColor ?? 'grey'">
          {{ item.icon ?? 'mdi-circle-small' }}
        </v-icon>
      </template>
      <template v-slot:append="{ item }">
        <span v-if="item.subtitle" class="text-caption text-medium-emphasis ml-1">
          {{ item.subtitle }}
        </span>
      </template>
    </v-treeview>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useIsoStore } from '@/stores/isoStore'
import { useHierarchyStore } from '@/stores/hierarchyStore'
import { useMapStore } from '@/stores/mapStore'
import { fetchSubstations, fetchFeeders } from '@/api/hierarchy'

const isoStore = useIsoStore()
const hierarchyStore = useHierarchyStore()
const mapStore = useMapStore()

interface TreeNode {
  id: string
  title: string
  subtitle?: string
  children?: TreeNode[]
  tier?: string
  icon?: string
  iconColor?: string
  lat?: number
  lon?: number
  entityType?: string
  entityId?: number
}

const treeItems = computed<TreeNode[]>(() => {
  return isoStore.classifications.map(cls => {
    const parts: string[] = []
    if (cls.avg_abs_congestion != null) {
      parts.push(`$${cls.avg_abs_congestion.toFixed(1)}/MWh`)
    }
    if (cls.congested_hours_pct != null) {
      parts.push(`${(cls.congested_hours_pct * 100).toFixed(0)}% hrs`)
    }
    return {
      id: `zone-${cls.zone_code}`,
      title: `${cls.zone_code}${cls.zone_name ? ' - ' + cls.zone_name : ''}`,
      subtitle: parts.length > 0 ? parts.join(' | ') : undefined,
      tier: cls.classification,
      entityType: 'zone',
      children: [], // lazy-loaded
    }
  })
})

async function loadChildren(item: TreeNode): Promise<void> {
  if (!isoStore.selectedISO) return

  try {
    if (item.id.startsWith('zone-')) {
      const zoneCode = item.id.replace('zone-', '')
      const subs = await fetchSubstations(isoStore.selectedISO, zoneCode)
      item.children = subs.map(s => {
        const parts: string[] = []
        if (s.peak_loading_pct != null) {
          parts.push(`${s.peak_loading_pct.toFixed(0)}%`)
        }
        if (s.facility_loading_mw != null && s.facility_rating_mw != null) {
          parts.push(`${s.facility_loading_mw.toFixed(0)}/${s.facility_rating_mw.toFixed(0)} MW`)
        }
        return {
          id: `sub-${s.id}`,
          title: s.substation_name ?? `Substation #${s.id}`,
          subtitle: parts.length > 0 ? parts.join(' | ') : undefined,
          icon: 'mdi-flash',
          iconColor: substationColor(s.peak_loading_pct),
          lat: s.lat ?? undefined,
          lon: s.lon ?? undefined,
          entityType: 'substation',
          entityId: s.id,
          children: [], // lazy-loaded
        }
      })
    } else if (item.id.startsWith('sub-')) {
      const subId = Number(item.id.replace('sub-', ''))
      const fds = await fetchFeeders(subId)
      item.children = fds.map(f => {
        const parts: string[] = []
        if (f.peak_loading_pct != null) {
          parts.push(`${f.peak_loading_pct.toFixed(0)}%`)
        }
        if (f.peak_loading_mw != null && f.capacity_mw != null) {
          parts.push(`${f.peak_loading_mw.toFixed(1)}/${f.capacity_mw.toFixed(1)} MW`)
        }
        if (f.voltage_kv != null) {
          parts.push(`${f.voltage_kv} kV`)
        }
        return {
          id: `feeder-${f.id}`,
          title: f.feeder_id_external ?? `Feeder #${f.id}`,
          subtitle: parts.length > 0 ? parts.join(' | ') : undefined,
          icon: 'mdi-transmission-tower',
          iconColor: substationColor(f.peak_loading_pct),
          entityType: 'feeder',
          entityId: f.id,
        }
      })
    }
  } catch (e) {
    console.error(`Failed to load children for ${item.id}:`, e)
    item.children = []
  }
}

function onActivate(ids: string[]) {
  const id = ids[0]
  if (!id) return

  if (id.startsWith('zone-')) {
    mapStore.selectedZoneCode = id.replace('zone-', '')
  } else if (id.startsWith('sub-')) {
    const subId = Number(id.replace('sub-', ''))
    mapStore.selectedSubstationId = subId
    hierarchyStore.selectSubstation(subId)
  }
}

function substationColor(pct: number | null): string {
  if (pct == null) return 'grey'
  if (pct > 100) return '#e74c3c'
  if (pct >= 80) return '#e67e22'
  if (pct >= 60) return '#f1c40f'
  return '#2ecc71'
}

function tierColor(cls: string): string {
  switch (cls) {
    case 'transmission': return '#e74c3c'
    case 'generation': return '#3498db'
    case 'both': return '#9b59b6'
    case 'unconstrained': return '#2ecc71'
    default: return 'grey'
  }
}
</script>
