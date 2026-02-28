<template>
  <div ref="mapContainer" style="height: 100%; width: 100%;" />
  <MapLegend />
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import maplibregl, { type ExpressionSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useMapStore } from '@/stores/mapStore'
import { useIsoStore } from '@/stores/isoStore'
import MapLegend from './MapLegend.vue'

const mapStore = useMapStore()
const isoStore = useIsoStore()

const mapContainer = ref<HTMLElement | null>(null)
let map: maplibregl.Map | null = null
let skipCenterSync = false

const TILE_BASE = '/api/v1/tiles'

const ISO_VIEW: Record<string, { lat: number; lng: number; zoom: number }> = {
  caiso: { lat: 37.0, lng: -119.5, zoom: 6 },
  miso:  { lat: 42.0, lng: -90.0, zoom: 5 },
  nyiso: { lat: 43.0, lng: -75.5, zoom: 7 },
  pjm:   { lat: 39.5, lng: -78.0, zoom: 6 },
  spp:   { lat: 37.5, lng: -97.0, zoom: 5 },
}

// Data-driven style expressions (cast to avoid MapLibre TS strictness with spread)
const classificationColor = [
  'match', ['get', 'classification'],
  'transmission', '#e53935',
  'generation', '#1e88e5',
  'both', '#8e24aa',
  'unconstrained', '#43a047',
  '#9e9e9e',
] as unknown as ExpressionSpecification

const tierColor = [
  'match', ['coalesce', ['get', 'tier'], 'low'],
  'critical', '#b71c1c',
  'severe', '#e53935',
  'elevated', '#ff9800',
  'moderate', '#fdd835',
  'low', '#66bb6a',
  '#66bb6a',
] as unknown as ExpressionSpecification

const dcStatusColor = [
  'match', ['coalesce', ['get', 'status'], 'operational'],
  'operational', '#1e88e5',
  'planned', '#ff9800',
  'under construction', '#fdd835',
  'proposed', '#8e24aa',
  '#757575',
] as unknown as ExpressionSpecification

const loadingColor = [
  'interpolate', ['linear'],
  ['coalesce', ['get', 'peak_loading_pct'], 0],
  0, '#43a047',
  60, '#fdd835',
  80, '#ff9800',
  100, '#e53935',
] as unknown as ExpressionSpecification

const voltageColor = [
  'interpolate', ['linear'],
  ['coalesce', ['get', 'voltage_kv'], 0],
  69, '#90caf9',
  115, '#42a5f5',
  230, '#1565c0',
  345, '#e53935',
  500, '#b71c1c',
  765, '#4a148c',
] as unknown as ExpressionSpecification

const voltageWidth = [
  'interpolate', ['linear'],
  ['coalesce', ['get', 'voltage_kv'], 0],
  69, 0.5,
  230, 1.5,
  500, 3,
  765, 4,
] as unknown as ExpressionSpecification

// Cluster-aware radius: scales by point_count when clustered, uses base sizing for individuals
function clusterAwareRadius(minR: number, midR: number, maxR: number): ExpressionSpecification {
  return [
    'case',
    ['>', ['coalesce', ['get', 'point_count'], 1], 1],
    // Clustered: size by point count
    ['interpolate', ['linear'],
      ['get', 'point_count'],
      2, midR + 2,
      10, maxR + 4,
      50, maxR + 8,
      200, maxR + 12,
    ],
    // Individual: base size
    midR,
  ] as unknown as ExpressionSpecification
}

function initMap() {
  if (!mapContainer.value) return

  map = new maplibregl.Map({
    container: mapContainer.value,
    style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
    center: [mapStore.center.lng, mapStore.center.lat],
    zoom: mapStore.zoom,
  })

  map.addControl(new maplibregl.NavigationControl(), 'top-right')

  map.on('load', () => {
    addTileSources()
    addLayers()
    setupInteractivity()
  })

  map.on('moveend', () => {
    if (skipCenterSync || !map) return
    const center = map.getCenter()
    mapStore.center = { lat: center.lat, lng: center.lng }
    mapStore.zoom = Math.round(map.getZoom())
  })
}

function addTileSources() {
  if (!map) return

  const layers = [
    'zones', 'transmission_lines', 'substations',
    'pnodes', 'data_centers', 'der_locations', 'feeders',
  ]

  for (const layer of layers) {
    map.addSource(`${layer}-source`, {
      type: 'vector',
      tiles: [`${window.location.origin}${TILE_BASE}/${layer}/{z}/{x}/{y}.mvt`],
      minzoom: 0,
      maxzoom: 14,
    })
  }
}

function addLayers() {
  if (!map) return

  // --- Zone boundaries (fill + outline) ---
  map.addLayer({
    id: 'zones-fill',
    type: 'fill',
    source: 'zones-source',
    'source-layer': 'zones',
    paint: {
      'fill-color': classificationColor,
      'fill-opacity': 0.15,
    },
    layout: {
      visibility: mapStore.showZones ? 'visible' : 'none',
    },
  })

  map.addLayer({
    id: 'zones-outline',
    type: 'line',
    source: 'zones-source',
    'source-layer': 'zones',
    paint: {
      'line-color': classificationColor,
      'line-width': 1.5,
      'line-opacity': 0.6,
    },
    layout: {
      visibility: mapStore.showZones ? 'visible' : 'none',
    },
  })

  // --- Transmission lines ---
  map.addLayer({
    id: 'transmission-lines',
    type: 'line',
    source: 'transmission_lines-source',
    'source-layer': 'transmission_lines',
    paint: {
      'line-color': voltageColor,
      'line-width': voltageWidth,
      'line-opacity': 0.7,
    },
    layout: {
      visibility: 'visible',
    },
  })

  // --- Substations (cluster-aware) ---
  map.addLayer({
    id: 'substations',
    type: 'circle',
    source: 'substations-source',
    'source-layer': 'substations',
    paint: {
      'circle-radius': clusterAwareRadius(3, 6, 10),
      'circle-color': loadingColor,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1,
      'circle-opacity': 0.8,
    },
    layout: {
      visibility: mapStore.showSubstations ? 'visible' : 'none',
    },
  })

  // Cluster count labels for substations
  map.addLayer({
    id: 'substations-count',
    type: 'symbol',
    source: 'substations-source',
    'source-layer': 'substations',
    filter: ['>', ['coalesce', ['get', 'point_count'], 1], 1],
    layout: {
      'text-field': ['to-string', ['get', 'point_count']],
      'text-size': 11,
      'text-font': ['Open Sans Bold'],
      'text-allow-overlap': true,
      visibility: mapStore.showSubstations ? 'visible' : 'none',
    },
    paint: {
      'text-color': '#ffffff',
    },
  })

  // --- Pnodes (cluster-aware) ---
  map.addLayer({
    id: 'pnodes',
    type: 'circle',
    source: 'pnodes-source',
    'source-layer': 'pnodes',
    paint: {
      'circle-radius': clusterAwareRadius(3, 6, 10),
      'circle-color': tierColor,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 0.5,
      'circle-opacity': 0.7,
    },
    layout: {
      visibility: 'visible',
    },
  })

  // Cluster count labels for pnodes
  map.addLayer({
    id: 'pnodes-count',
    type: 'symbol',
    source: 'pnodes-source',
    'source-layer': 'pnodes',
    filter: ['>', ['coalesce', ['get', 'point_count'], 1], 1],
    layout: {
      'text-field': ['to-string', ['get', 'point_count']],
      'text-size': 10,
      'text-font': ['Open Sans Bold'],
      'text-allow-overlap': true,
      visibility: 'visible',
    },
    paint: {
      'text-color': '#ffffff',
    },
  })

  // --- Data centers (cluster-aware) ---
  map.addLayer({
    id: 'data-centers',
    type: 'circle',
    source: 'data_centers-source',
    'source-layer': 'data_centers',
    paint: {
      'circle-radius': clusterAwareRadius(4, 8, 14),
      'circle-color': dcStatusColor,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1,
      'circle-opacity': 0.8,
    },
    layout: {
      visibility: mapStore.showDataCenters ? 'visible' : 'none',
    },
  })

  // Cluster count labels for data centers
  map.addLayer({
    id: 'data-centers-count',
    type: 'symbol',
    source: 'data_centers-source',
    'source-layer': 'data_centers',
    filter: ['>', ['coalesce', ['get', 'point_count'], 1], 1],
    layout: {
      'text-field': ['to-string', ['get', 'point_count']],
      'text-size': 11,
      'text-font': ['Open Sans Bold'],
      'text-allow-overlap': true,
      visibility: mapStore.showDataCenters ? 'visible' : 'none',
    },
    paint: {
      'text-color': '#ffffff',
    },
  })

  // --- DER locations (cluster-aware) ---
  map.addLayer({
    id: 'der-locations',
    type: 'circle',
    source: 'der_locations-source',
    'source-layer': 'der_locations',
    paint: {
      'circle-radius': clusterAwareRadius(3, 5, 9),
      'circle-color': '#ff7043',
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 0.5,
      'circle-opacity': 0.7,
    },
    layout: {
      visibility: mapStore.showDERs ? 'visible' : 'none',
    },
  })

  // Cluster count labels for DER locations
  map.addLayer({
    id: 'der-locations-count',
    type: 'symbol',
    source: 'der_locations-source',
    'source-layer': 'der_locations',
    filter: ['>', ['coalesce', ['get', 'point_count'], 1], 1],
    layout: {
      'text-field': ['to-string', ['get', 'point_count']],
      'text-size': 10,
      'text-font': ['Open Sans Bold'],
      'text-allow-overlap': true,
      visibility: mapStore.showDERs ? 'visible' : 'none',
    },
    paint: {
      'text-color': '#ffffff',
    },
  })

  // --- Feeders ---
  map.addLayer({
    id: 'feeders',
    type: 'line',
    source: 'feeders-source',
    'source-layer': 'feeders',
    paint: {
      'line-color': '#78909c',
      'line-width': 1,
      'line-opacity': 0.5,
    },
    minzoom: 10,
    layout: {
      visibility: 'visible',
    },
  })
}

function setupInteractivity() {
  if (!map) return

  // Cursor changes on hover for interactive layers
  const interactiveLayers = [
    'zones-fill', 'substations', 'pnodes', 'data-centers', 'der-locations',
  ]

  for (const layerId of interactiveLayers) {
    map.on('mouseenter', layerId, () => {
      if (map) map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', layerId, () => {
      if (map) map.getCanvas().style.cursor = ''
    })
  }

  // Click on zone
  map.on('click', 'zones-fill', (e) => {
    if (e.features && e.features.length > 0) {
      const props = e.features[0].properties
      mapStore.selectedZoneCode = props.zone_code
    }
  })

  // Click on substation
  map.on('click', 'substations', (e) => {
    if (e.features && e.features.length > 0) {
      const props = e.features[0].properties
      mapStore.selectedSubstationId = props.id ?? null
    }
  })

  // Click on pnode — show popup
  map.on('click', 'pnodes', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    const props = e.features[0].properties
    const coords = (e.features[0].geometry as any).coordinates.slice()
    new maplibregl.Popup({ closeButton: true, maxWidth: '260px' })
      .setLngLat(coords)
      .setHTML(`
        <strong>${props.node_name || props.node_id_external}</strong><br/>
        Severity: ${props.severity_score?.toFixed(1) ?? 'N/A'}<br/>
        Tier: ${props.tier || 'N/A'}
      `)
      .addTo(map)
  })

  // Click on data center — show popup
  map.on('click', 'data-centers', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    const props = e.features[0].properties
    const coords = (e.features[0].geometry as any).coordinates.slice()
    new maplibregl.Popup({ closeButton: true, maxWidth: '280px' })
      .setLngLat(coords)
      .setHTML(`
        <strong>${props.facility_name || 'Data Center'}</strong><br/>
        Status: ${props.status || 'unknown'}<br/>
        Capacity: ${props.capacity_mw ? props.capacity_mw + ' MW' : 'N/A'}<br/>
        Operator: ${props.operator || 'N/A'}
      `)
      .addTo(map)
  })

  // Click on map background (for siting)
  map.on('click', (e) => {
    // Only trigger if no feature was clicked
    const features = map!.queryRenderedFeatures(e.point, {
      layers: interactiveLayers.filter(l => map!.getLayer(l)),
    })
    if (features.length === 0) {
      mapStore.setClickedPoint({ lat: e.lngLat.lat, lng: e.lngLat.lng })
    }
  })
}

// Toggle layer visibility when store toggles change
function setLayerVisibility(layerId: string, visible: boolean) {
  if (map && map.getLayer(layerId)) {
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
  }
}

watch(() => mapStore.showZones, (v) => {
  setLayerVisibility('zones-fill', v)
  setLayerVisibility('zones-outline', v)
})
watch(() => mapStore.showSubstations, (v) => {
  setLayerVisibility('substations', v)
  setLayerVisibility('substations-count', v)
})
watch(() => mapStore.showDataCenters, (v) => {
  setLayerVisibility('data-centers', v)
  setLayerVisibility('data-centers-count', v)
})
watch(() => mapStore.showDERs, (v) => {
  setLayerVisibility('der-locations', v)
  setLayerVisibility('der-locations-count', v)
})
watch(() => mapStore.showAssets, (v) => {
  // Assets not yet a vector tile layer; will be handled when HC integration lands
})

// Pan to ISO region when selected
watch(() => isoStore.selectedISO, (iso) => {
  if (!iso || !map) return
  const view = ISO_VIEW[iso]
  if (!view) return
  skipCenterSync = true
  map.flyTo({ center: [view.lng, view.lat], zoom: view.zoom, duration: 1200 })
  setTimeout(() => { skipCenterSync = false }, 1500)
})

onMounted(() => {
  initMap()
})

onBeforeUnmount(() => {
  if (map) {
    map.remove()
    map = null
  }
})
</script>

<style scoped>
/* MapLibre popups need global styles; scoped won't reach them.
   The maplibre-gl.css import handles base popup styling. */
</style>
