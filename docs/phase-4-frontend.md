# Phase 4: Frontend

## Goal

Update the Vue 3 frontend to use the new API structure and build a UI centered on constraint profiles and DER-constraint intersection. The frontend should clearly answer the three core questions: where are constraints, what DERs match, and what's the temporal overlap.

## Prerequisites

- Phase 3 complete (new API endpoints deployed, old routes removed)
- All constraint profiles, intersections, and value stacks populated

---

## Step 4.1: Update API Client

### `frontend/src/api/client.ts`

Change baseURL from `/api/v1` to `/api`:

```typescript
const client = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})
```

### Replace API modules

**Delete old modules** (7 files):
- `isos.ts`, `valuations.ts`, `hierarchy.ts`, `congestion.ts`, `hostingCapacity.ts`, `infrastructure.ts`, `wattcarbon.ts`

**Create new modules** (4 files):

#### `frontend/src/api/constraints.ts`
```typescript
export async function resolveLocation(lat: number, lon: number)
export async function listISOs()
export async function listZones(isoCode: string)
export async function zoneGeometries(isoCode: string)
export async function zoneConstraints(isoCode: string, zoneCode: string)
export async function zoneLMPs(isoCode: string, zoneCode: string, params)
export async function locationProfile(level: string, locationId: number)
```

#### `frontend/src/api/valuations.ts` (rewrite)
```typescript
export async function prospectiveValuation(lat, lon, derType, capacityMw)
export async function compareDERTypes(lat: number, lon: number)
export async function valueRankings(isoCode: string, derType: string, params)
export async function batchValuation(items: BatchItem[], apiKey: string)
```

#### `frontend/src/api/profiles.ts` (NEW)
```typescript
export async function getConstraintProfile(profileId: number)
export async function getDERProfile(derType: string)
export async function getIntersection(constraintProfileId: number, derType: string)
export async function zoneLoadshape(isoCode: string, zoneCode: string, month?: number)
```

#### `frontend/src/api/enrichment.ts` (NEW)
```typescript
export async function nearbyHostingCapacity(lat: number, lon: number, radiusKm?: number)
export async function nearbyInterconnection(lat: number, lon: number, radiusKm?: number)
export async function utilityFilings(utilityCode: string, filingType?: string)
export async function listUtilities(state?: string, isoCode?: string)
```

---

## Step 4.2: Consolidate Pinia Stores

**Delete old stores** (6 files):
- `isoStore.ts` -> split into constraintStore + keep ISO selection
- `valuationStore.ts` -> rewrite
- `hierarchyStore.ts` -> remove (hierarchy is now part of constraint profiles)
- `congestionStore.ts` -> remove (folded into constraint profiles)
- `hostingCapacityStore.ts` -> remove (folded into enrichment)
- `wattcarbonStore.ts` -> remove (plugin, not core)

**Create new stores** (4 files):

#### `frontend/src/stores/constraintStore.ts`
```typescript
export const useConstraintStore = defineStore('constraints', () => {
  // State
  const isos = ref<ISO[]>([])
  const selectedISOs = ref<string[]>([])
  const zonesMap = ref<Record<string, ZoneConstraintSummary[]>>({})
  const selectedZone = ref<ZoneConstraintSummary | null>(null)
  const zoneConstraints = ref<ConstraintProfile[]>([])
  const zoneAnnotations = ref<Annotation[]>([])
  const resolvedLocation = ref<GeoResolution | null>(null)
  const isLoading = ref(false)

  // Computed
  const zones = computed(() => /* merge across selected ISOs */)
  const constrainedZones = computed(() =>
    zones.value.filter(z => z.severity_tier !== 'low'))

  // Actions
  async function loadISOs()
  async function selectISO(isoCode: string)
  async function loadZoneConstraints(isoCode: string, zoneCode: string)
  async function resolveLocation(lat: number, lon: number)
})
```

#### `frontend/src/stores/valuationStore.ts` (rewrite)
```typescript
export const useValuationStore = defineStore('valuations', () => {
  // State
  const valueStack = ref<ValueStack | null>(null)
  const derComparison = ref<DERComparisonItem[]>([])
  const rankings = ref<LocationRanking[]>([])
  const selectedDERType = ref<string>('solar')
  const isComputing = ref(false)

  // Actions
  async function computeProspective(lat, lon, derType, capacityMw)
  async function compareDERTypes(lat: number, lon: number)
  async function loadRankings(isoCode: string, derType: string)
})
```

#### `frontend/src/stores/profileStore.ts` (NEW)
```typescript
export const useProfileStore = defineStore('profiles', () => {
  // State
  const constraintProfile = ref<ConstraintProfile | null>(null)
  const derProfile = ref<DERProfile | null>(null)
  const intersection = ref<Intersection | null>(null)
  const loadshape = ref<LoadshapeHour[]>([])

  // Actions
  async function loadConstraintProfile(profileId: number)
  async function loadDERProfile(derType: string)
  async function loadIntersection(constraintProfileId: number, derType: string)
  async function loadLoadshape(isoCode: string, zoneCode: string, month?: number)
})
```

#### `frontend/src/stores/mapStore.ts` (KEEP, minimal changes)
```typescript
// Keep existing map state management
// Update layer list to match new tile attributes
// Update popup data to show severity_score instead of classification
```

---

## Step 4.3: Update/Create Components

### Panel Components

#### `frontend/src/components/panels/ZoneDetail.vue` (REWRITE)

Currently shows classification (transmission/generation/both/unconstrained). Rewrite to show:

1. **Constraint Summary Card**: severity tier badge, peak month/hour, constrained hours %
2. **Constraint Profiles List**: expandable cards for each constraint type (congestion, loading, etc.) with mini 24-hour sparkline
3. **Annotations Panel**: regulatory context cards (IRP citations, grid plans, deferral opportunities) with confidence indicators
4. **Best DER Recommendation**: top DER type with value and coincidence factor
5. **Pnode Hotspots**: top 5 pnodes by severity with mini severity bars

#### `frontend/src/components/panels/ProfileOverlayChart.vue` (NEW)

The signature visualization. Shows two 12x24 heatmaps overlaid:
- Constraint intensity (red/orange gradient)
- DER output (blue/green gradient)
- Overlap region highlighted (purple where both are high)

Uses a 24-column x 12-row grid (hours x months). User can toggle between:
- Heatmap view (color intensity)
- Line chart view (24-hour profile for a selected month)
- Stacked area view (constraint + DER output overlaid)

#### `frontend/src/components/panels/DERComparison.vue` (NEW)

Side-by-side comparison of all DER types at a location:
- Bar chart: $/kW-yr by DER type (sorted descending)
- Coincidence factor gauge for each type
- Mini 24-hour overlap chart for the selected DER type
- Dispatchable vs. non-dispatchable grouping

#### `frontend/src/components/panels/ValueStack.vue` (NEW)

Stacked bar chart showing the value breakdown:
- Congestion value (blue)
- Loading value (orange)
- Capacity value (green)
- Import stress value (purple)
- Total $/kW-yr label on top

With tier badge (premium/high/moderate/low) and annotations panel below.

#### `frontend/src/components/panels/AnnotationCard.vue` (NEW)

Compact card for a single annotation:
- Type badge (IRP citation, grid plan, deferral opportunity, etc.)
- Title and summary
- Planned solution (if available)
- Deferral value estimate (if available)
- Confidence indicator (dot: green/yellow/red)
- Source link

#### `frontend/src/components/panels/SidePanel.vue` (REWRITE)

Currently has tabs for different views. Simplify to three primary tabs:
1. **Constraints** - zone list with severity sorting, click to expand zone detail
2. **Valuations** - prospective valuation tool (click map or enter lat/lon)
3. **Profiles** - DER profile browser and intersection viewer

### Map Components

#### `frontend/src/components/map/GridMapGL.vue` (MODIFY)

Update data-driven styling to use new tile attributes:

```typescript
// Zone fill color: severity_score gradient (was classification-based)
'fill-color': [
  'interpolate', ['linear'], ['get', 'severity_score'],
  0.0, '#e8f5e9',    // low - green
  0.25, '#fff9c4',   // moderate - yellow
  0.50, '#ffcc80',   // elevated - orange
  0.75, '#ef5350',   // critical - red
]

// Pnode circle color: severity_score gradient (same)
'circle-color': [
  'interpolate', ['linear'], ['get', 'severity_score'],
  0.0, '#66bb6a',
  0.75, '#d32f2f',
]
```

#### `frontend/src/components/map/SitingPopup.vue` (MODIFY)

Update the click-to-site popup to show:
- Resolved hierarchy (zone, substation, feeder)
- Value stack breakdown (from `/api/valuations/prospective`)
- Best DER type recommendation
- "Compare all DER types" button -> opens DERComparison panel
- Nearby hosting capacity summary (from enrichment)

#### `frontend/src/components/map/MapLegend.vue` (MODIFY)

Update legend to show:
- Severity gradient (low/moderate/elevated/critical) instead of classification categories
- DER value tier legend (premium/high/moderate/low)
- Layer toggles: Constraints, Pnodes, Substations, Feeders, Transmission

---

## Step 4.4: Update Views

### `frontend/src/views/Dashboard.vue` (MODIFY)

The main view. Currently shows a map with a side panel. Update:

1. **Map**: zones colored by severity_score, pnodes by severity, substations by loading
2. **Side Panel**: three tabs (Constraints, Valuations, Profiles)
3. **Top Bar**: ISO selector (multi-select), DER type selector dropdown
4. **Click interaction**: clicking a zone opens ZoneDetail in the side panel; clicking the map (not on a zone) triggers location resolve and shows prospective valuation
5. **Rankings view**: accessible from Valuations tab, shows top locations for selected DER type

### Remove old views
- Any separate Overview/Summary views that duplicate information now in the consolidated dashboard

---

## Step 4.5: TypeScript Interfaces

### `frontend/src/types/constraints.ts` (NEW)

```typescript
interface ConstraintProfile {
  id: number
  location_level: string
  location_id: number
  location_name?: string
  constraint_type: string
  period_year: number
  profile_12x24: Record<string, number[]>
  peak_intensity: number
  peak_month: number
  peak_hour: number
  mean_intensity: number
  total_constrained_hours: number
  constrained_hours_pct: number
  severity_score: number
  severity_tier: string
  avg_marginal_cost?: number
  annual_cost?: number
  annotations: Annotation[]
}

interface Annotation {
  id: number
  annotation_type: string
  title: string
  summary?: string
  planned_solution?: string
  deferral_value_estimate?: number
  source_url?: string
  confidence: number
}

interface ZoneConstraintSummary {
  iso_code: string
  zone_code: string
  zone_name: string
  centroid_lat?: number
  centroid_lon?: number
  primary_constraint_type?: string
  severity_score?: number
  severity_tier?: string
  peak_month?: number
  peak_hour?: number
  constrained_hours_pct?: number
  best_der_type?: string
  best_der_value_per_kw_year?: number
  annotation_count: number
}

interface ValueStack {
  congestion_value_per_kw_year: number
  loading_value_per_kw_year: number
  capacity_value_per_kw_year: number
  import_stress_value_per_kw_year: number
  total_value_per_kw_year: number
  composite_coincidence_factor: number
  value_tier: string
  constraint_layers: ConstraintLayer[]
  annotations: Annotation[]
}

interface DERProfile {
  id: number
  der_type: string
  eac_category: string
  profile_12x24?: Record<string, number[]>
  is_dispatchable: boolean
  max_dispatch_hours?: number
  dispatch_power_mw?: number
  capacity_factor?: number
}

interface Intersection {
  coincidence_factor: number
  overlap_hours: number
  overlap_12x24?: Record<string, number[]>
  value_per_kw_year: number
  value_tier: string
}

interface DERComparisonItem {
  der_type: string
  eac_category: string
  total_value_per_kw_year: number
  coincidence_factor: number
  value_tier: string
  is_dispatchable: boolean
}

interface LocationRanking {
  location_level: string
  location_id: number
  location_name?: string
  lat?: number
  lon?: number
  total_value_per_kw_year: number
  value_tier: string
  coincidence_factor: number
}
```

---

## Verification

After Phase 4:
- [ ] Map loads with zones colored by severity gradient
- [ ] Clicking a zone opens ZoneDetail with constraint profiles, 12x24 charts, and annotations
- [ ] Clicking empty map triggers geo-resolve and shows prospective valuation
- [ ] DER comparison chart shows all 8 DER types ranked by value
- [ ] Profile overlay chart correctly renders constraint and DER 12x24s with overlap highlighting
- [ ] Value stack chart shows per-layer breakdown
- [ ] Annotation cards display regulatory context with confidence indicators
- [ ] Rankings view shows top locations for selected DER type
- [ ] ISO multi-select works correctly
- [ ] Vector tiles render with new severity-based styling
- [ ] No console errors, no broken API calls

## Files Created/Modified/Deleted

| File | Action |
|---|---|
| `frontend/src/api/client.ts` | MODIFY (baseURL) |
| `frontend/src/api/constraints.ts` | CREATE |
| `frontend/src/api/valuations.ts` | REWRITE |
| `frontend/src/api/profiles.ts` | CREATE |
| `frontend/src/api/enrichment.ts` | CREATE |
| `frontend/src/api/isos.ts` | DELETE |
| `frontend/src/api/hierarchy.ts` | DELETE |
| `frontend/src/api/congestion.ts` | DELETE |
| `frontend/src/api/hostingCapacity.ts` | DELETE |
| `frontend/src/api/infrastructure.ts` | DELETE |
| `frontend/src/api/wattcarbon.ts` | DELETE |
| `frontend/src/stores/constraintStore.ts` | CREATE |
| `frontend/src/stores/valuationStore.ts` | REWRITE |
| `frontend/src/stores/profileStore.ts` | CREATE |
| `frontend/src/stores/mapStore.ts` | MODIFY |
| `frontend/src/stores/isoStore.ts` | DELETE |
| `frontend/src/stores/hierarchyStore.ts` | DELETE |
| `frontend/src/stores/congestionStore.ts` | DELETE |
| `frontend/src/stores/hostingCapacityStore.ts` | DELETE |
| `frontend/src/stores/wattcarbonStore.ts` | DELETE |
| `frontend/src/components/panels/ZoneDetail.vue` | REWRITE |
| `frontend/src/components/panels/ProfileOverlayChart.vue` | CREATE |
| `frontend/src/components/panels/DERComparison.vue` | CREATE |
| `frontend/src/components/panels/ValueStack.vue` | CREATE |
| `frontend/src/components/panels/AnnotationCard.vue` | CREATE |
| `frontend/src/components/panels/SidePanel.vue` | REWRITE |
| `frontend/src/components/map/GridMapGL.vue` | MODIFY |
| `frontend/src/components/map/SitingPopup.vue` | MODIFY |
| `frontend/src/components/map/MapLegend.vue` | MODIFY |
| `frontend/src/views/Dashboard.vue` | MODIFY |
| `frontend/src/types/constraints.ts` | CREATE |
