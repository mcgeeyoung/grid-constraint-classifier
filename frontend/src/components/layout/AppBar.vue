<template>
  <v-app-bar density="compact" color="surface">
    <v-app-bar-title>
      <router-link to="/" class="text-decoration-none text-white">
        Grid Constraint Classifier
      </router-link>
    </v-app-bar-title>

    <template v-slot:append>
      <ISOSelector />
      <v-btn icon to="/overview" title="Overview">
        <v-icon>mdi-view-dashboard</v-icon>
      </v-btn>
    </template>
  </v-app-bar>
</template>

<script setup lang="ts">
import ISOSelector from '@/components/panels/ISOSelector.vue'
</script>
