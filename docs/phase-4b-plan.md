# Phase 4B: Dashboard Intelligence Layer

## Context

Phase 4A delivered the Vue 3 SPA scaffold: map, stores, API client, siting tool, hierarchy tree, and backend auth/batch/aggregation endpoints. The backend fully supports the original vision. The frontend is a navigation shell that doesn't yet surface the intelligence.

This plan closes the gap between "functional scaffold" and "intelligence layer for the grid that allows any DER to be valued for its contribution to grid capacity constraints."

## Guiding Principles

- Every view should answer a question a user would actually ask
- Show value ($/kW-yr) everywhere, not just categories
- The three audiences (utility engineers, DER developers, WattCarbon internal) each have a primary workflow
- Use data already available from the API. No new backend endpoints needed (except one small addition noted below).

---

## Part 1: Value-Driven Map (the "So What?" fix)

### Problem
Zone polygons show classification type (transmission/generation/both/unconstrained) as colored categories. A user can't glance at the map and see where the highest-value locations are. The intelligence is invisible.

### 1.1 Zone Value Gradient

**File: `ZoneLayer.vue`**

Add a toggle between "Classification" and "Value" color modes.

- **Classification mode** (current): red/blue/purple/green by type
- **Value mode** (new): continuous color gradient from cool (low $/kW-yr) to hot (high $/kW-yr) based on `avg_abs_congestion` from classifications data

Implementation:
- Add `colorMode` ref to `mapStore` (`'classification' | 'value'`)
- In value mode, normalize `avg_abs_congestion` across all zones to 0-1 range
- Use interpolated color scale: `#2ecc71` (green, low) -> `#f1c40f` (yellow, mid) -> `#e74c3c` (red, high)
- Show legend overlay in bottom-left corner indicating the scale

### 1.2 Data Center Layer

**File: `components/map/DataCenterMarkers.vue` (new)**

Diamond-shaped markers for data center locations. Color by status (operating=blue, planned=orange, under construction=yellow).

Data source: `GET /data-centers?iso_id={iso}` (already wired in `api/isos.ts` as `fetchDataCenters`, never called).

- Add `showDataCenters` toggle to `mapStore`
- Add checkbox to DashboardView layer controls
- Popup: facility name, operator, capacity MW, status
- Clicking opens a side panel card showing co-located constraint data (which zone, zone classification, nearby substations)

### 1.3 Pnode Severity Overlay

**File: `components/map/PnodeMarkers.vue` (new)**

Small circle markers at pnode locations, colored by severity tier. Only shown when zoomed into a specific zone.

Data source: `GET /isos/{iso_id}/zones/{zone_code}/pnodes` (exists, not wired in frontend).

- Add `fetchPnodeScores(isoCode, zoneCode)` to `api/isos.ts`
- Add `pnodes` ref to `isoStore`, loaded when a zone is selected
- Marker radius: 3px base, scales with severity_score
- Color: green (low) -> yellow -> orange -> red (critical)
- Popup: node name, severity score, avg/max congestion, congested hours %
- Only render when `mapStore.selectedZoneCode` is set and zoom >= 8

### 1.4 Map Legend

**File: `components/map/MapLegend.vue` (new)**

Floating card in bottom-left showing active layer legends:
- Zone color key (classification mode or value gradient)
- DER tier colors (premium/high/moderate/low)
- Substation loading colors
- Data center status colors
- Pnode severity scale

Only show entries for layers currently toggled on.

---

## Part 2: Recommendations Panel

### Problem
The backend computes DER recommendations per zone (which DER types to deploy, why, expected value), but the frontend never displays them. This is the most actionable data for DER developers.

### 2.1 Zone Detail Enhancement

**File: `components/panels/ZoneDetail.vue`**

Add a "Recommendations" section below the existing congestion stats:

- Fetch recommendations: `GET /isos/{iso_id}/recommendations` (already wired as `fetchRecommendations`, never called)
- Filter to the selected zone
- Display:
  - **Rationale** text (why this zone needs DERs)
  - **Primary recommendation**: DER type, expected congestion value, brief explanation
  - **Secondary/tertiary**: smaller cards below
- Each recommendation card shows: DER type icon, congestion_value formatted as $/kW-yr, one-line rationale

### 2.2 Recommendations Store

**Modify: `stores/isoStore.ts`**

- Add `recommendations` ref
- Load recommendations alongside zones/classifications in `selectISO()`
- Filter helper: `recommendationsForZone(zoneCode)` computed

---

## Part 3: WattCarbon Asset Integration

### Problem
The user chose "Both" (prospective + retrospective). The backend has full WattCarbon asset support. The frontend has zero visibility into enrolled assets or their actual performance.

### 3.1 Asset Layer on Map

**File: `components/map/AssetMarkers.vue` (new)**

Star-shaped markers for WattCarbon assets (distinct from hypothetical DER circles).

Data source: `GET /wattcarbon/assets?iso_code={iso}` (exists, not wired).

- Add `fetchWattCarbonAssets(isoCode)` to new `api/wattcarbon.ts`
- Add `showAssets` toggle to `mapStore`
- Star marker colored by value tier (same palette as DERs but different shape)
- Popup: asset ID, DER type, capacity, zone, latest valuation summary

### 3.2 Asset Detail Panel

**File: `components/panels/AssetDetail.vue` (new)**

Full detail view when a WattCarbon asset is clicked:

Data source: `GET /wattcarbon/assets/{id}` (returns latest_valuation + latest_retrospective).

Display sections:
1. **Asset Info**: DER type, capacity, EAC category, zone, substation, pnode
2. **Prospective Valuation**: total value, $/kW-yr, tier badge, value breakdown (same format as ValuationResult)
3. **Retrospective Performance** (if available):
   - Date range (start - end)
   - Actual savings (MWh)
   - Actual constraint relief value ($)
   - Actual vs. projected comparison bar (side-by-side)
   - Component breakdown: zone actual vs. projected, substation actual vs. projected, feeder actual vs. projected
4. **"Run Retrospective"** button: date range picker, triggers `POST /wattcarbon/assets/{id}/retrospective`

### 3.3 WattCarbon Store

**File: `stores/wattcarbonStore.ts` (new)**

- `assets` ref: loaded per ISO
- `selectedAsset` ref: full detail with valuations
- `loadAssets(isoCode)`: fetches asset list
- `selectAsset(assetId)`: fetches detail
- `runRetrospective(assetId, start, end)`: triggers computation, refreshes detail

### 3.4 API Client Module

**File: `api/wattcarbon.ts` (new)**

Typed functions wrapping:
- `GET /wattcarbon/assets` (list, filterable by iso_code, der_type)
- `GET /wattcarbon/assets/{id}` (detail with valuations)
- `GET /wattcarbon/assets/{id}/valuation` (compute prospective)
- `POST /wattcarbon/assets/{id}/retrospective` (compute retrospective)

---

## Part 4: Enhanced Overview (Executive Dashboard)

### Problem
The Overview page is a flat table with zone counts. The value-summary endpoint returns rich portfolio data (total value, tier distributions, top zones) but is never called. This page should answer "how much constraint-relief value exists in each ISO?"

### 4.1 Value Summary Cards

**File: `views/OverviewView.vue` (rewrite)**

Replace the single table with a dashboard layout:

**Top row**: Summary cards per ISO (one card each, horizontal scroll on mobile):
- ISO name + code
- Total portfolio value (formatted as $XXXk)
- Avg $/kW-yr
- Constrained zones / total zones
- Overloaded substations count

Data source: `GET /isos/{iso_id}/value-summary` for each ISO. Note: this endpoint requires API key, so either:
- Option A: Make this endpoint open (remove auth requirement for read-only summary)
- Option B: Add an internal `/overview/values` endpoint that aggregates across ISOs without auth

**Recommended: Option A** (remove auth from value-summary since it's read-only aggregate data, or add a parallel open endpoint).

### 4.2 Tier Distribution Chart

For each ISO, show a horizontal stacked bar of tier distribution (premium/high/moderate/low counts).

Use inline SVG or a simple CSS bar (no charting library needed):
- Each segment width proportional to count
- Colored by tier palette
- Hover shows count + percentage

### 4.3 Top Zones Table

Below the cards, a combined table of top zones across all ISOs:
- Columns: ISO, Zone, Classification, Avg Constraint Value ($/kW-yr), DER Count
- Sorted by avg constraint value descending
- Clickable rows navigate to Dashboard with that ISO/zone selected

Data source: `top_zones` from each ISO's value-summary response.

### 4.4 Backend Adjustment

**File: `app/api/v1/routes.py`**

Add `GET /api/v1/overview/values` endpoint (no auth required). Iterates all ISOs and returns the same data as value-summary but in a list. This avoids the auth issue and the N+1 problem of calling value-summary per ISO from the frontend.

Response: `list[ValueSummaryResponse]`

---

## Part 5: Site Comparison Workflow

### Problem
The siting tool evaluates one point at a time. Previous results vanish. A DER developer evaluating sites needs to compare candidates.

### 5.1 Comparison List

**Modify: `stores/valuationStore.ts`**

Add a `comparisonList` ref that accumulates siting results:
- `comparisonList: ref<Array<{ lat, lon, derType, capacityMw, result: ValuationResult }>>([])` (max 10 entries)
- `addToComparison()`: copies current siting result into the list
- `removeFromComparison(index)`: removes entry
- `clearComparison()`: empties list

### 5.2 Comparison Panel

**File: `components/panels/ComparisonPanel.vue` (new)**

New tab in the side panel ("Compare"):
- List of saved siting results
- Each row: lat/lon, zone, total value, $/kW-yr, tier badge
- Sorted by total value descending (best site on top)
- Highlight the best option
- "Remove" button per row
- Corresponding numbered markers on the map for each comparison point

### 5.3 Comparison Markers

**File: `components/map/ComparisonMarkers.vue` (new)**

Numbered circle markers (1, 2, 3...) at each comparison point. Colored by value tier. Clicking re-opens that result in the side panel.

### 5.4 "Add to Comparison" Button

**Modify: `components/panels/ValuationResult.vue`**

Add button below the existing "Save as DER Location" button:
- "Add to Comparison" (icon: mdi-compare)
- Disabled if already in comparison list (same lat/lon)
- Shows count badge: "Compare (3)"

---

## Part 6: Filtering and Search

### Problem
No way to filter the map or find specific entities. Utilities want to filter by state, value tier, or loading. DER developers want to search for substations or zones.

### 6.1 Filter Bar

**File: `components/panels/FilterBar.vue` (new)**

Collapsible filter section at top of side panel (or floating above map):
- **Value tier filter**: chip toggles for premium/high/moderate/low (applied to DER markers)
- **DER type filter**: dropdown (solar, storage, wind, etc.)
- **Loading threshold**: slider for substation min loading % (60-100%)
- **Classification filter**: chip toggles for transmission/generation/both/unconstrained (applied to zones)

Filters are reactive via `mapStore` refs. Each map layer component watches the relevant filter and excludes non-matching entities.

### 6.2 Search

**Modify: `components/layout/AppBar.vue`**

Add a search field (Vuetify `v-autocomplete`) in the app bar:
- Searches across zone codes, zone names, substation names
- Debounced, client-side (data already loaded in stores)
- Selecting a result pans the map to that entity and opens its detail panel
- Show entity type icon (zone/substation) in dropdown results

---

## Part 7: LMP Time Series

### Problem
Hourly congestion data exists in the backend but isn't visualized. Understanding when congestion occurs is critical for matching DER output profiles to constraint patterns.

### 7.1 LMP Chart in Zone Detail

**Modify: `components/panels/ZoneDetail.vue`**

Add an expandable "Congestion Profile" section:

Data source: `GET /isos/{iso_id}/zones/{zone_code}/lmps?limit=720` (last 30 days of hourly data).

Display:
- Simple inline SVG sparkline (no charting library) showing congestion component over time
- Below sparkline: summary stats (avg, max, % hours congested)
- Month selector to view different periods

### 7.2 API Client Addition

**Modify: `api/isos.ts`**

Add `fetchZoneLMPs(isoCode, zoneCode, limit?, month?)` function wrapping the existing endpoint.

---

## Part 8: Hierarchy Tree Value Display

### Problem
The tree shows structure (zone > substation > feeder) with constraint tier badges, but not the actual $/kW-yr values that are the core insight.

### 8.1 Value Annotations

**Modify: `components/panels/HierarchyTree.vue`**

For each tree node, show the value metric inline:
- **Zone nodes**: avg congestion value from classifications (avg_abs_congestion)
- **Substation nodes**: peak loading % + loading MW / rating MW
- **Feeder nodes**: peak loading % if available

Format: `zone_code (avg $X.XX/MWh congestion)` or `Substation Name (85% loaded, 45/53 MW)`

### 8.2 Hierarchy Scores Integration

Load hierarchy scores (`GET /hierarchy-scores?level=zone`) alongside the tree. Show `combined_score` as a small bar or numeric indicator next to each node.

---

## Implementation Order

Ordered by impact (what transforms the UX most for the least effort):

| Priority | Part | Effort | Impact | Why |
|----------|------|--------|--------|-----|
| 1 | Part 2: Recommendations Panel | Small | High | Actionable insight, data already fetched, just needs display |
| 2 | Part 4: Enhanced Overview | Medium | High | Executive-level value story, makes the tool legible |
| 3 | Part 1.1: Zone Value Gradient | Small | High | Map immediately communicates value, not just categories |
| 4 | Part 3: WattCarbon Assets | Large | High | Core use case (retrospective), unique differentiator |
| 5 | Part 1.2: Data Center Layer | Small | Medium | Context for demand-side marketplace story |
| 6 | Part 5: Site Comparison | Medium | High | Key DER developer workflow |
| 7 | Part 8: Hierarchy Tree Values | Small | Medium | Makes drill-down informative, not just navigational |
| 8 | Part 6: Filtering and Search | Medium | Medium | Usability for power users |
| 9 | Part 1.3: Pnode Severity Overlay | Medium | Medium | Deep technical layer for utility engineers |
| 10 | Part 7: LMP Time Series | Medium | Medium | Temporal dimension, useful but secondary |
| 11 | Part 1.4: Map Legend | Small | Low | Polish, but important for interpretability |

### Suggested Grouping

**Sprint 1** (Parts 1.1, 2, 4, 8): "Make the existing views show value"
- Zone value gradient, recommendations in zone detail, enhanced overview, tree values
- Mostly modifying existing components, small new additions
- Result: every view answers "how much value?" not just "what category?"

**Sprint 2** (Parts 1.2, 3, 1.4): "WattCarbon assets + context layers"
- Data center markers, WattCarbon asset integration (list + detail + retrospective), map legend
- New store, new API module, new components
- Result: retrospective valuation visible, demand-side context present

**Sprint 3** (Parts 5, 6, 1.3, 7): "Power user workflows"
- Site comparison, filtering/search, pnode overlay, LMP charts
- Polish and depth features
- Result: tool usable for real site evaluation workflows

---

## Files Summary

### New Files
| File | Part |
|------|------|
| `frontend/src/components/map/DataCenterMarkers.vue` | 1.2 |
| `frontend/src/components/map/PnodeMarkers.vue` | 1.3 |
| `frontend/src/components/map/MapLegend.vue` | 1.4 |
| `frontend/src/components/map/ComparisonMarkers.vue` | 5.3 |
| `frontend/src/components/panels/AssetDetail.vue` | 3.2 |
| `frontend/src/components/panels/ComparisonPanel.vue` | 5.2 |
| `frontend/src/components/panels/FilterBar.vue` | 6.1 |
| `frontend/src/api/wattcarbon.ts` | 3.4 |
| `frontend/src/stores/wattcarbonStore.ts` | 3.3 |

### Modified Files
| File | Parts |
|------|-------|
| `frontend/src/components/map/ZoneLayer.vue` | 1.1 |
| `frontend/src/components/map/GridMap.vue` | 1.2, 1.3, 1.4, 5.3 |
| `frontend/src/components/panels/ZoneDetail.vue` | 2.1, 7.1 |
| `frontend/src/components/panels/ValuationResult.vue` | 5.4 |
| `frontend/src/components/panels/HierarchyTree.vue` | 8.1, 8.2 |
| `frontend/src/components/layout/AppBar.vue` | 6.2 |
| `frontend/src/views/DashboardView.vue` | 1.2, 5.2, 6.1 (new tabs/layers) |
| `frontend/src/views/OverviewView.vue` | 4.1, 4.2, 4.3 (full rewrite) |
| `frontend/src/stores/isoStore.ts` | 2.2, 1.3 |
| `frontend/src/stores/mapStore.ts` | 1.1, 1.2, 6.1 |
| `frontend/src/stores/valuationStore.ts` | 5.1 |
| `frontend/src/api/isos.ts` | 1.3, 7.2 |
| `app/api/v1/routes.py` | 4.4 (new open overview/values endpoint) |

### Backend Change
One small addition: `GET /api/v1/overview/values` (open, no auth) that returns `list[ValueSummaryResponse]` for all ISOs. This avoids the frontend needing API keys for the overview page and eliminates N+1 API calls.

---

## Verification Criteria

After all parts are complete:

1. A user can open the map and immediately see where constraint-relief value is highest (zone gradient)
2. Clicking a zone shows classification, congestion stats, AND actionable DER recommendations
3. WattCarbon assets appear as distinct markers; clicking one shows prospective + retrospective valuations
4. The overview page shows portfolio value per ISO, tier distributions, and top zones
5. A DER developer can evaluate 5 sites and compare them side-by-side
6. Filtering by tier, DER type, and loading narrows the map to relevant entities
7. The hierarchy tree shows quantitative values ($/MWh, loading %) not just labels
8. Data centers appear on the map providing demand context
9. Every endpoint the backend exposes is represented somewhere in the frontend
