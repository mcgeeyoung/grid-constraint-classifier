<template>
  <v-navigation-drawer
    :model-value="visible"
    location="right"
    :width="400"
    temporary
    @update:model-value="$emit('update:visible', $event)"
  >
    <v-toolbar density="compact" color="surface">
      <v-toolbar-title class="text-body-1">{{ title }}</v-toolbar-title>
      <v-btn icon size="small" @click="$emit('update:visible', false)">
        <v-icon>mdi-close</v-icon>
      </v-btn>
    </v-toolbar>
    <v-divider />
    <div class="pa-4">
      <slot />
    </div>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  title: string
}>()
defineEmits<{
  'update:visible': [value: boolean]
}>()
</script>
