<template>
  <div style="height: calc(100vh - 48px); display: flex;">
    <!-- Queue list (left) -->
    <div style="width: 420px; border-right: 1px solid #ddd; overflow-y: auto; background: #ffffff;">
      <div class="pa-3 pb-0">
        <div class="d-flex align-center justify-space-between">
          <h2 class="text-subtitle-1 font-weight-bold">Review Queue</h2>
          <v-chip v-if="store.stats" size="x-small" variant="flat" color="warning">
            {{ store.stats.pending }} pending
          </v-chip>
        </div>
        <div class="text-caption text-medium-emphasis mt-1">
          Human-in-the-loop verification for LLM-extracted data
        </div>
      </div>

      <!-- Filters -->
      <div class="px-3 pt-2 d-flex ga-2">
        <v-select
          v-model="store.statusFilter"
          :items="statusOptions"
          item-title="label"
          item-value="value"
          density="compact"
          variant="outlined"
          hide-details
          style="max-width: 140px;"
          @update:model-value="store.loadQueue()"
        />
        <v-select
          v-model="store.typeFilter"
          :items="typeOptions"
          item-title="label"
          item-value="value"
          density="compact"
          variant="outlined"
          hide-details
          clearable
          placeholder="All types"
          style="max-width: 160px;"
          @update:model-value="store.loadQueue()"
        />
      </div>

      <!-- Stats chips -->
      <div v-if="store.stats" class="px-3 pt-2 d-flex ga-1 flex-wrap">
        <v-chip
          v-for="(count, type) in store.stats.by_type"
          :key="type"
          size="x-small"
          variant="tonal"
          :color="typeColor(type)"
        >
          {{ type }}: {{ count }}
        </v-chip>
      </div>

      <!-- Loading -->
      <v-progress-linear v-if="store.isLoading" indeterminate color="primary" class="mt-2" />

      <!-- Queue items -->
      <v-list density="compact" class="mt-1">
        <v-list-item
          v-for="item in store.items"
          :key="item.id"
          :active="store.selectedItem?.id === item.id"
          @click="store.selectItem(item.id)"
          class="py-2"
        >
          <template v-slot:prepend>
            <v-icon :color="confidenceColor(item.confidence)" size="18">
              {{ confidenceIcon(item.confidence) }}
            </v-icon>
          </template>

          <v-list-item-title class="text-body-2">
            <v-chip size="x-small" variant="tonal" :color="typeColor(item.extraction_type)" class="mr-1">
              {{ item.extraction_type }}
            </v-chip>
            <span class="text-medium-emphasis">{{ item.record_count }} records</span>
          </v-list-item-title>

          <v-list-item-subtitle class="text-caption">
            {{ item.utility_name || 'Unknown utility' }}
            <span v-if="item.source_file" class="text-disabled">
              &middot; {{ fileName(item.source_file) }}
            </span>
          </v-list-item-subtitle>

          <template v-slot:append>
            <v-chip
              size="x-small"
              :color="statusColor(item.review_status)"
              variant="flat"
            >
              {{ item.review_status }}
            </v-chip>
          </template>
        </v-list-item>

        <v-list-item v-if="!store.isLoading && store.items.length === 0">
          <v-list-item-title class="text-body-2 text-medium-emphasis text-center">
            No items matching filters
          </v-list-item-title>
        </v-list-item>
      </v-list>
    </div>

    <!-- Detail panel (right) -->
    <div style="flex: 1; overflow-y: auto; background: #fafafa;">
      <div v-if="!store.selectedItem" class="d-flex align-center justify-center" style="height: 100%;">
        <div class="text-center text-medium-emphasis">
          <v-icon size="48" color="grey-lighten-1">mdi-clipboard-check-outline</v-icon>
          <div class="text-body-2 mt-2">Select an item to review</div>
        </div>
      </div>

      <div v-else class="pa-4">
        <!-- Header -->
        <div class="d-flex align-center justify-space-between mb-3">
          <div>
            <div class="d-flex align-center ga-2">
              <v-chip :color="typeColor(store.selectedItem.extraction_type)" variant="flat" size="small">
                {{ store.selectedItem.extraction_type }}
              </v-chip>
              <v-chip :color="confidenceColor(store.selectedItem.confidence)" variant="tonal" size="small">
                {{ store.selectedItem.confidence }}
              </v-chip>
              <v-chip :color="statusColor(store.selectedItem.review_status)" variant="flat" size="small">
                {{ store.selectedItem.review_status }}
              </v-chip>
            </div>
            <div class="text-caption text-medium-emphasis mt-1">
              {{ store.selectedItem.utility_name || 'Unknown utility' }}
              <span v-if="store.selectedItem.docket_number">
                &middot; {{ store.selectedItem.docket_number }}
              </span>
              <span v-if="store.selectedItem.llm_model">
                &middot; {{ store.selectedItem.llm_model }}
              </span>
            </div>
          </div>

          <!-- Action buttons -->
          <div v-if="store.selectedItem.review_status === 'pending'" class="d-flex ga-2">
            <v-btn
              color="success"
              variant="flat"
              size="small"
              prepend-icon="mdi-check"
              @click="handleApprove"
              :loading="actionLoading"
            >
              Approve
            </v-btn>
            <v-btn
              color="error"
              variant="outlined"
              size="small"
              prepend-icon="mdi-close"
              @click="handleReject"
              :loading="actionLoading"
            >
              Reject
            </v-btn>
          </div>
        </div>

        <!-- Source provenance -->
        <v-card v-if="store.selectedItem.source_file || store.selectedItem.raw_text_snippet" variant="outlined" class="mb-3">
          <v-card-title class="text-body-2 font-weight-medium py-2 px-3">Source</v-card-title>
          <v-card-text class="px-3 pb-3 pt-0">
            <div v-if="store.selectedItem.source_file" class="text-caption text-medium-emphasis mb-1">
              File: {{ store.selectedItem.source_file }}
              <span v-if="store.selectedItem.source_page"> (page {{ store.selectedItem.source_page }})</span>
            </div>
            <div
              v-if="store.selectedItem.raw_text_snippet"
              class="text-caption pa-2 rounded"
              style="background: #f5f5f5; font-family: monospace; white-space: pre-wrap; max-height: 200px; overflow-y: auto;"
            >
              {{ store.selectedItem.raw_text_snippet }}
            </div>
          </v-card-text>
        </v-card>

        <!-- Extracted data -->
        <v-card variant="outlined" class="mb-3">
          <v-card-title class="text-body-2 font-weight-medium py-2 px-3 d-flex align-center justify-space-between">
            Extracted Data
            <v-btn
              v-if="store.selectedItem.review_status === 'pending'"
              size="x-small"
              variant="text"
              :icon="editMode ? 'mdi-eye' : 'mdi-pencil'"
              @click="editMode = !editMode"
              title="Toggle edit mode"
            />
          </v-card-title>
          <v-card-text class="px-3 pb-3 pt-0">
            <!-- View mode: formatted display -->
            <div v-if="!editMode">
              <ExtractionDataView
                :extraction-type="store.selectedItem.extraction_type"
                :data="store.selectedItem.extracted_data"
              />
            </div>

            <!-- Edit mode: JSON editor -->
            <div v-else>
              <v-textarea
                v-model="editedJson"
                variant="outlined"
                density="compact"
                rows="15"
                style="font-family: monospace; font-size: 12px;"
                hide-details
              />
              <v-btn
                color="primary"
                variant="flat"
                size="small"
                class="mt-2"
                prepend-icon="mdi-check-all"
                @click="handleEditApprove"
                :loading="actionLoading"
                :disabled="!isValidJson"
              >
                Save &amp; Approve
              </v-btn>
              <span v-if="!isValidJson" class="text-caption text-error ml-2">Invalid JSON</span>
            </div>
          </v-card-text>
        </v-card>

        <!-- Notes -->
        <v-card v-if="store.selectedItem.extraction_notes || store.selectedItem.reviewer_notes" variant="outlined">
          <v-card-title class="text-body-2 font-weight-medium py-2 px-3">Notes</v-card-title>
          <v-card-text class="px-3 pb-3 pt-0">
            <div v-if="store.selectedItem.extraction_notes" class="text-caption mb-1">
              <strong>Extraction:</strong> {{ store.selectedItem.extraction_notes }}
            </div>
            <div v-if="store.selectedItem.reviewer_notes" class="text-caption">
              <strong>Reviewer:</strong> {{ store.selectedItem.reviewer_notes }}
            </div>
          </v-card-text>
        </v-card>

        <!-- Reviewer notes input (for pending items) -->
        <v-text-field
          v-if="store.selectedItem.review_status === 'pending'"
          v-model="reviewerNotes"
          label="Reviewer notes (optional)"
          variant="outlined"
          density="compact"
          hide-details
          class="mt-3"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useReviewStore } from '@/stores/reviewStore'
import ExtractionDataView from '@/components/panels/ExtractionDataView.vue'

const store = useReviewStore()

const actionLoading = ref(false)
const reviewerNotes = ref('')
const editMode = ref(false)
const editedJson = ref('')

const statusOptions = [
  { label: 'Pending', value: 'pending' },
  { label: 'Approved', value: 'approved' },
  { label: 'Rejected', value: 'rejected' },
  { label: 'Edited', value: 'edited' },
  { label: 'All', value: '' },
]

const typeOptions = [
  { label: 'Load Forecast', value: 'load_forecast' },
  { label: 'Grid Constraint', value: 'grid_constraint' },
  { label: 'Resource Need', value: 'resource_need' },
  { label: 'Hosting Capacity', value: 'hosting_capacity' },
  { label: 'General Summary', value: 'general_summary' },
]

const isValidJson = computed(() => {
  try {
    JSON.parse(editedJson.value)
    return true
  } catch {
    return false
  }
})

// When selecting a new item, reset edit state
watch(() => store.selectedItem, (item) => {
  editMode.value = false
  reviewerNotes.value = ''
  if (item) {
    editedJson.value = JSON.stringify(item.extracted_data, null, 2)
  }
})

onMounted(async () => {
  await Promise.all([store.loadQueue(), store.loadStats()])
})

async function handleApprove() {
  if (!store.selectedItem) return
  actionLoading.value = true
  try {
    await store.approve(store.selectedItem.id, reviewerNotes.value || undefined)
    reviewerNotes.value = ''
  } finally {
    actionLoading.value = false
  }
}

async function handleReject() {
  if (!store.selectedItem) return
  actionLoading.value = true
  try {
    await store.reject(store.selectedItem.id, reviewerNotes.value || undefined)
    reviewerNotes.value = ''
  } finally {
    actionLoading.value = false
  }
}

async function handleEditApprove() {
  if (!store.selectedItem || !isValidJson.value) return
  actionLoading.value = true
  try {
    const data = JSON.parse(editedJson.value)
    await store.editApprove(store.selectedItem.id, data, reviewerNotes.value || undefined)
    editMode.value = false
    reviewerNotes.value = ''
  } finally {
    actionLoading.value = false
  }
}

function typeColor(type: string): string {
  switch (type) {
    case 'grid_constraint': return 'error'
    case 'load_forecast': return 'info'
    case 'resource_need': return 'warning'
    case 'hosting_capacity': return 'success'
    case 'general_summary': return 'grey'
    default: return 'grey'
  }
}

function confidenceColor(conf: string): string {
  switch (conf) {
    case 'high': return 'success'
    case 'medium': return 'info'
    case 'low': return 'warning'
    case 'unverified': return 'error'
    default: return 'grey'
  }
}

function confidenceIcon(conf: string): string {
  switch (conf) {
    case 'high': return 'mdi-check-circle'
    case 'medium': return 'mdi-alert-circle'
    case 'low': return 'mdi-alert'
    case 'unverified': return 'mdi-help-circle'
    default: return 'mdi-circle'
  }
}

function statusColor(status: string): string {
  switch (status) {
    case 'pending': return 'warning'
    case 'approved': return 'success'
    case 'rejected': return 'error'
    case 'edited': return 'info'
    default: return 'grey'
  }
}

function fileName(path: string): string {
  return path.split('/').pop() || path
}
</script>
