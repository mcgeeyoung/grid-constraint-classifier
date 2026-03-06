<template>
  <v-card variant="outlined" class="pa-3 mb-3">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon :icon="levelIcon" size="18" :color="levelColor" />
      <span class="text-subtitle-2 font-weight-medium text-truncate">
        {{ props.level.name || levelLabel }}
      </span>
      <v-spacer />
      <TierChip v-if="props.level.tier" :tier="props.level.tier" />
      <span
        v-if="props.level.grid_score != null"
        class="text-caption"
        style="font-variant-numeric: tabular-nums; color: var(--text-secondary);"
      >
        {{ Math.round(props.level.grid_score * 100) }}
      </span>
    </div>

    <div class="text-caption text-medium-emphasis mb-2">
      {{ props.level.score_label }}
    </div>

    <template v-if="props.level.constraint_loadshape">
      <ProfileHeatmap
        :constraint-profile="props.level.constraint_loadshape"
        :der-profile="derProfile"
        :overlap-profile="props.level.overlap_12x24"
        size="standard"
        :show-labels="true"
        :show-legend="true"
        :score="props.level.grid_score != null ? props.level.grid_score * 100 : undefined"
      />
      <div
        v-if="props.level.coincidence_factor != null"
        class="d-flex align-center ga-2 mt-2"
      >
        <span class="text-caption" style="color: var(--text-secondary);">Coincidence Factor</span>
        <v-chip size="x-small" variant="outlined" color="info">
          {{ Math.round(props.level.coincidence_factor * 100) }}%
        </v-chip>
      </div>
    </template>

    <div v-else class="text-caption pa-2" style="color: var(--text-tertiary);">
      No data at this level
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { GridLevelScore } from '@/types/constraints'
import TierChip from '@/components/shared/TierChip.vue'
import ProfileHeatmap from '@/components/shared/ProfileHeatmap.vue'

const props = defineProps<{
  level: GridLevelScore
  derProfile?: Record<string, number[]> | null
}>()

const LEVEL_ICONS: Record<string, string> = {
  substation: 'mdi-transmission-tower',
  pnode: 'mdi-map-marker-circle',
  zone: 'mdi-vector-polygon',
  utility: 'mdi-office-building',
  ba: 'mdi-earth',
}

const LEVEL_LABELS: Record<string, string> = {
  substation: 'Substation',
  pnode: 'P-node',
  zone: 'Zone',
  utility: 'Utility',
  ba: 'Balancing Authority',
}

const LEVEL_COLORS: Record<string, string> = {
  substation: 'amber',
  pnode: 'cyan',
  zone: 'primary',
  utility: 'green',
  ba: 'deep-purple',
}

const levelIcon = computed(() => LEVEL_ICONS[props.level.level] ?? 'mdi-help-circle')
const levelLabel = computed(() => LEVEL_LABELS[props.level.level] ?? props.level.level)
const levelColor = computed(() => LEVEL_COLORS[props.level.level] ?? 'grey')
</script>
