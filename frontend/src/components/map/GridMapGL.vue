<template>
  <div ref="mapContainer" style="height: 100%; width: 100%;" />
  <MapLegend />
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import maplibregl, { type ExpressionSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useMapStore } from '@/stores/mapStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { useGridDataStore, ISO_VIEW } from '@/stores/gridDataStore'
import { useEnrichmentStore } from '@/stores/enrichmentStore'
import { allInterconnectionQueue } from '@/api/enrichment'
import MapLegend from './MapLegend.vue'

const mapStore = useMapStore()
const selectionStore = useSelectionStore()
const gridStore = useGridDataStore()
const enrichStore = useEnrichmentStore()

const mapContainer = ref<HTMLElement | null>(null)
let map: maplibregl.Map | null = null
let skipCenterSync = false
let bboxMarkers: maplibregl.Marker[] = []

const TILE_BASE = '/api/v1/tiles'

// Data-driven style expressions (cast to avoid MapLibre TS strictness with spread)
const classificationColor = [
  'match', ['get', 'classification'],
  'transmission', '#ef4444',
  'generation', '#38bdf8',
  'both', '#c084fc',
  'unconstrained', '#4ade80',
  '#6b7280',
] as unknown as ExpressionSpecification

const tierColor = [
  'match', ['coalesce', ['get', 'tier'], 'low'],
  'critical', '#ef4444',
  'severe', '#f59e0b',
  'elevated', '#eab308',
  'moderate', '#facc15',
  'low', '#22c55e',
  '#22c55e',
] as unknown as ExpressionSpecification

const severityColor = [
  'interpolate', ['linear'],
  ['coalesce', ['get', 'severity_score'], 0],
  0.0, '#1a2e1a',
  0.25, '#3d2a08',
  0.50, '#f59e0b',
  0.75, '#ef4444',
] as unknown as ExpressionSpecification

const dcStatusColor = [
  'match', ['coalesce', ['get', 'status'], 'operational'],
  'operational', '#38bdf8',
  'planned', '#fb923c',
  'under construction', '#facc15',
  'proposed', '#c084fc',
  '#6b7280',
] as unknown as ExpressionSpecification

const loadingColor = [
  'interpolate', ['linear'],
  ['coalesce', ['get', 'peak_loading_pct'], 0],
  0, '#22c55e',
  60, '#eab308',
  80, '#f59e0b',
  100, '#ef4444',
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

// Hosting capacity: remaining MW -> green/yellow/orange/red
const hcRemainingColor = [
  'interpolate', ['linear'],
  ['coalesce', ['get', 'remaining_capacity_mw'], 0],
  0, '#ef4444',
  0.5, '#fb923c',
  2, '#facc15',
  5, '#22c55e',
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
    style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
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

const TILE_LAYERS = [
  'zones', 'transmission_lines', 'substations',
  'pnodes', 'data_centers', 'der_locations', 'feeders',
]

// GeoPackage infrastructure layers (no ISO filter, national coverage)
const INFRA_TILE_LAYERS = [
  'gpkg_power_lines', 'gpkg_substations', 'gpkg_power_plants',
]

function tileUrl(layer: string): string {
  const base = `${window.location.origin}${TILE_BASE}/${layer}/{z}/{x}/{y}.mvt`
  if (selectionStore.selectedISOs.length > 0) {
    return `${base}?iso_id=${selectionStore.selectedISOs.join(',')}`
  }
  return base
}

function infraTileUrl(layer: string): string {
  return `${window.location.origin}${TILE_BASE}/${layer}/{z}/{x}/{y}.mvt`
}

function addTileSources() {
  if (!map) return

  for (const layer of TILE_LAYERS) {
    map.addSource(`${layer}-source`, {
      type: 'vector',
      tiles: [tileUrl(layer)],
      minzoom: 0,
      maxzoom: 14,
    })
  }

  // GeoPackage infrastructure sources (national, no ISO filter)
  for (const layer of INFRA_TILE_LAYERS) {
    map.addSource(`${layer}-source`, {
      type: 'vector',
      tiles: [infraTileUrl(layer)],
      minzoom: 0,
      maxzoom: 14,
    })
  }

  // Hosting capacity GeoJSON source (loaded on demand per utility)
  map.addSource('hosting-capacity-source', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })

}

function updateTileSourceUrls() {
  if (!map) return
  for (const layer of TILE_LAYERS) {
    const source = map.getSource(`${layer}-source`) as maplibregl.VectorTileSource | undefined
    if (source) {
      source.setTiles([tileUrl(layer)])
    }
  }
}

function addLayers() {
  if (!map) return

  // --- Zone boundaries (fill + outline) ---
  const initialZoneColor = mapStore.zoneColorMode === 'severity'
    ? severityColor
    : mapStore.zoneColorMode === 'value'
      ? classificationColor // value mode uses transmission_score; will be set by watcher
      : classificationColor

  map.addLayer({
    id: 'zones-fill',
    type: 'fill',
    source: 'zones-source',
    'source-layer': 'zones',
    paint: {
      'fill-color': initialZoneColor,
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
      'line-color': initialZoneColor,
      'line-width': 1.5,
      'line-opacity': 0.8,
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
      'line-width': [
        'case',
        ['boolean', ['feature-state', 'hover'], false],
        ['*', voltageWidth, 2.5],
        voltageWidth,
      ] as unknown as ExpressionSpecification,
      'line-opacity': [
        'case',
        ['boolean', ['feature-state', 'hover'], false],
        1,
        0.7,
      ] as unknown as ExpressionSpecification,
    },
    layout: {
      visibility: mapStore.showTransmissionLines ? 'visible' : 'none',
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
      'circle-stroke-color': 'rgba(0,0,0,0.3)',
      'circle-stroke-width': 1,
      'circle-opacity': 0.8,
    },
    layout: {
      visibility: mapStore.showInfraSubstations ? 'visible' : 'none',
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
      visibility: mapStore.showInfraSubstations ? 'visible' : 'none',
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
      'circle-stroke-color': 'rgba(0,0,0,0.3)',
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
      'circle-stroke-color': 'rgba(0,0,0,0.3)',
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
      'circle-color': '#fb923c',
      'circle-stroke-color': 'rgba(0,0,0,0.3)',
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

  // --- Feeders (colored by loading) ---
  map.addLayer({
    id: 'feeders',
    type: 'line',
    source: 'feeders-source',
    'source-layer': 'feeders',
    paint: {
      'line-color': [
        'interpolate', ['linear'],
        ['coalesce', ['get', 'peak_loading_pct'], 0],
        0, '#22c55e',
        60, '#eab308',
        80, '#f59e0b',
        100, '#ef4444',
      ] as unknown as ExpressionSpecification,
      'line-width': [
        'case',
        ['boolean', ['feature-state', 'hover'], false],
        3,
        1.5,
      ] as unknown as ExpressionSpecification,
      'line-opacity': [
        'case',
        ['boolean', ['feature-state', 'hover'], false],
        1,
        0.6,
      ] as unknown as ExpressionSpecification,
    },
    minzoom: 10,
    layout: {
      visibility: mapStore.showFeeders ? 'visible' : 'none',
    },
  })

  // --- Transmission line voltage labels (zoom 9+) ---
  map.addLayer({
    id: 'transmission-lines-label',
    type: 'symbol',
    source: 'transmission_lines-source',
    'source-layer': 'transmission_lines',
    minzoom: 9,
    layout: {
      'symbol-placement': 'line',
      'text-field': [
        'case',
        ['has', 'voltage_kv'],
        ['concat', ['to-string', ['get', 'voltage_kv']], ' kV'],
        '',
      ] as unknown as ExpressionSpecification,
      'text-size': 11,
      'text-font': ['Open Sans Regular'],
      'text-offset': [0, -0.8],
      'text-max-angle': 30,
      visibility: mapStore.showTransmissionLines ? 'visible' : 'none',
    },
    paint: {
      'text-color': 'rgba(255,255,255,0.8)',
      'text-halo-color': 'rgba(0,0,0,0.6)',
      'text-halo-width': 1.5,
    },
  })

  // --- Hosting capacity feeders (GeoJSON, loaded per utility) ---
  map.addLayer({
    id: 'hosting-capacity',
    type: 'circle',
    source: 'hosting-capacity-source',
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['zoom'],
        4, 3,
        8, 5,
        12, 8,
      ] as unknown as ExpressionSpecification,
      'circle-color': hcRemainingColor,
      'circle-stroke-color': 'rgba(0,0,0,0.3)',
      'circle-stroke-width': 0.5,
      'circle-opacity': 0.8,
    },
    layout: {
      visibility: mapStore.showHostingCapacity ? 'visible' : 'none',
    },
  })

  // ===============================================================
  // GeoPackage Infrastructure Layers (OSM national data)
  // ===============================================================

  // --- Infrastructure power lines (voltage-colored, zoom-aware) ---
  map.addLayer({
    id: 'infra-power-lines',
    type: 'line',
    source: 'gpkg_power_lines-source',
    'source-layer': 'gpkg_power_lines',
    paint: {
      'line-color': [
        'interpolate', ['linear'],
        ['coalesce', ['get', 'max_voltage_kv'], 0],
        0, '#b0bec5',
        69, '#90caf9',
        115, '#42a5f5',
        230, '#1565c0',
        345, '#e53935',
        500, '#b71c1c',
        765, '#4a148c',
      ] as unknown as ExpressionSpecification,
      'line-width': [
        'interpolate', ['linear'],
        ['coalesce', ['get', 'max_voltage_kv'], 0],
        0, 0.3,
        69, 0.5,
        230, 1.5,
        500, 3,
        765, 4,
      ] as unknown as ExpressionSpecification,
      'line-opacity': [
        'case',
        ['boolean', ['feature-state', 'hover'], false],
        1,
        0.6,
      ] as unknown as ExpressionSpecification,
    },
    layout: {
      visibility: mapStore.showInfraLines ? 'visible' : 'none',
    },
  })

  // --- Infrastructure power line voltage labels (zoom 10+) ---
  map.addLayer({
    id: 'infra-power-lines-label',
    type: 'symbol',
    source: 'gpkg_power_lines-source',
    'source-layer': 'gpkg_power_lines',
    minzoom: 10,
    layout: {
      'symbol-placement': 'line',
      'text-field': [
        'case',
        ['has', 'max_voltage_kv'],
        ['concat', ['to-string', ['get', 'max_voltage_kv']], ' kV'],
        '',
      ] as unknown as ExpressionSpecification,
      'text-size': 10,
      'text-font': ['Open Sans Regular'],
      'text-offset': [0, -0.8],
      'text-max-angle': 30,
      visibility: mapStore.showInfraLines ? 'visible' : 'none',
    },
    paint: {
      'text-color': 'rgba(167,139,250,0.8)',
      'text-halo-color': 'rgba(0,0,0,0.6)',
      'text-halo-width': 1.5,
    },
  })

  // --- Infrastructure substations (polygon outlines + fill) ---
  // Grey/muted — substations with DB data get colored point circles on top
  map.addLayer({
    id: 'infra-substations-fill',
    type: 'fill',
    source: 'gpkg_substations-source',
    'source-layer': 'gpkg_substations',
    minzoom: 9,
    paint: {
      'fill-color': '#666666',
      'fill-opacity': 0.2,
    },
    layout: {
      visibility: mapStore.showInfraSubstations ? 'visible' : 'none',
    },
  })

  map.addLayer({
    id: 'infra-substations-outline',
    type: 'line',
    source: 'gpkg_substations-source',
    'source-layer': 'gpkg_substations',
    minzoom: 9,
    paint: {
      'line-color': '#888888',
      'line-width': 1,
      'line-opacity': 0.5,
    },
    layout: {
      visibility: mapStore.showInfraSubstations ? 'visible' : 'none',
    },
  })

  // --- Infrastructure substation labels (zoom 12+) ---
  map.addLayer({
    id: 'infra-substations-label',
    type: 'symbol',
    source: 'gpkg_substations-source',
    'source-layer': 'gpkg_substations',
    minzoom: 12,
    layout: {
      'text-field': ['coalesce', ['get', 'name'], ''] as unknown as ExpressionSpecification,
      'text-size': 11,
      'text-font': ['Open Sans Regular'],
      'text-offset': [0, 1.2],
      'text-max-width': 10,
      visibility: mapStore.showInfraSubstations ? 'visible' : 'none',
    },
    paint: {
      'text-color': 'rgba(255,255,255,0.5)',
      'text-halo-color': 'rgba(0,0,0,0.6)',
      'text-halo-width': 1,
    },
  })

  // --- Infrastructure power plants (polygon outlines + fill) ---
  map.addLayer({
    id: 'infra-power-plants-fill',
    type: 'fill',
    source: 'gpkg_power_plants-source',
    'source-layer': 'gpkg_power_plants',
    minzoom: 7,
    paint: {
      'fill-color': [
        'match', ['coalesce', ['get', 'source'], 'unknown'],
        'solar', '#fdd835',
        'wind', '#4fc3f7',
        'hydro', '#1565c0',
        'gas', '#ff9800',
        'coal', '#616161',
        'nuclear', '#e53935',
        'battery', '#7e57c2',
        'oil', '#795548',
        'biomass', '#66bb6a',
        '#9e9e9e',
      ] as unknown as ExpressionSpecification,
      'fill-opacity': 0.35,
    },
    layout: {
      visibility: mapStore.showInfraPowerPlants ? 'visible' : 'none',
    },
  })

  map.addLayer({
    id: 'infra-power-plants-outline',
    type: 'line',
    source: 'gpkg_power_plants-source',
    'source-layer': 'gpkg_power_plants',
    minzoom: 7,
    paint: {
      'line-color': [
        'match', ['coalesce', ['get', 'source'], 'unknown'],
        'solar', '#f9a825',
        'wind', '#0288d1',
        'hydro', '#0d47a1',
        'gas', '#e65100',
        'coal', '#424242',
        'nuclear', '#b71c1c',
        'battery', '#512da8',
        'oil', '#4e342e',
        'biomass', '#2e7d32',
        '#616161',
      ] as unknown as ExpressionSpecification,
      'line-width': 1.5,
      'line-opacity': 0.8,
    },
    layout: {
      visibility: mapStore.showInfraPowerPlants ? 'visible' : 'none',
    },
  })

  // --- Infrastructure power plant labels (zoom 10+) ---
  map.addLayer({
    id: 'infra-power-plants-label',
    type: 'symbol',
    source: 'gpkg_power_plants-source',
    'source-layer': 'gpkg_power_plants',
    minzoom: 10,
    layout: {
      'text-field': ['coalesce', ['get', 'name'], ''] as unknown as ExpressionSpecification,
      'text-size': 11,
      'text-font': ['Open Sans Regular'],
      'text-offset': [0, 1.2],
      'text-max-width': 10,
      visibility: mapStore.showInfraPowerPlants ? 'visible' : 'none',
    },
    paint: {
      'text-color': 'rgba(74,222,128,0.8)',
      'text-halo-color': 'rgba(0,0,0,0.6)',
      'text-halo-width': 1,
    },
  })

  // Move DB substations (colored circles) above infrastructure polygons
  // so they visually indicate "has data" on top of grey OSM outlines
  map.moveLayer('substations')
  map.moveLayer('substations-count')

}

function setupInteractivity() {
  if (!map) return

  // Cursor changes on hover for interactive layers
  const interactiveLayers = [
    'zones-fill', 'substations', 'pnodes', 'data-centers', 'der-locations',
    'transmission-lines', 'feeders', 'hosting-capacity',
    'infra-power-lines', 'infra-substations-fill', 'infra-power-plants-fill',
    'ba-markers-circle', 'iq-markers-circle',
  ]

  for (const layerId of interactiveLayers) {
    map.on('mouseenter', layerId, () => {
      if (map) map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', layerId, () => {
      if (map) map.getCanvas().style.cursor = ''
    })
  }

  // Hover highlight for transmission lines
  let hoveredTxLineId: number | string | null = null
  map.on('mousemove', 'transmission-lines', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    if (hoveredTxLineId !== null) {
      map.setFeatureState({ source: 'transmission_lines-source', sourceLayer: 'transmission_lines', id: hoveredTxLineId }, { hover: false })
    }
    hoveredTxLineId = e.features[0].id ?? null
    if (hoveredTxLineId !== null) {
      map.setFeatureState({ source: 'transmission_lines-source', sourceLayer: 'transmission_lines', id: hoveredTxLineId }, { hover: true })
    }
  })
  map.on('mouseleave', 'transmission-lines', () => {
    if (map && hoveredTxLineId !== null) {
      map.setFeatureState({ source: 'transmission_lines-source', sourceLayer: 'transmission_lines', id: hoveredTxLineId }, { hover: false })
      hoveredTxLineId = null
    }
  })

  // Hover highlight for feeders
  let hoveredFeederId: number | string | null = null
  map.on('mousemove', 'feeders', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    if (hoveredFeederId !== null) {
      map.setFeatureState({ source: 'feeders-source', sourceLayer: 'feeders', id: hoveredFeederId }, { hover: false })
    }
    hoveredFeederId = e.features[0].id ?? null
    if (hoveredFeederId !== null) {
      map.setFeatureState({ source: 'feeders-source', sourceLayer: 'feeders', id: hoveredFeederId }, { hover: true })
    }
  })
  map.on('mouseleave', 'feeders', () => {
    if (map && hoveredFeederId !== null) {
      map.setFeatureState({ source: 'feeders-source', sourceLayer: 'feeders', id: hoveredFeederId }, { hover: false })
      hoveredFeederId = null
    }
  })

  // Layers that take priority over zone-fill clicks (point features above polygons)
  const pointLayers = [
    'substations', 'pnodes', 'data-centers', 'feeders', 'hosting-capacity',
    'ba-markers-circle', 'iq-markers-circle',
    'infra-substations-fill', 'infra-power-plants-fill',
  ]

  // Click on zone
  map.on('click', 'zones-fill', (e) => {
    // Don't handle zone click if a point feature was also clicked
    const activePt = pointLayers.filter(l => map!.getLayer(l))
    const hits = map!.queryRenderedFeatures(e.point, { layers: activePt })
    if (hits.length > 0) return

    if (e.features && e.features.length > 0) {
      const props = e.features[0].properties
      mapStore.selectedZoneCode = props.zone_code
      selectionStore.selectZone(props.zone_code)
    }
  })

  // Click on substation (DB point layer)
  map.on('click', 'substations', (e) => {
    if (e.features && e.features.length > 0) {
      ;(e.originalEvent as any)._substationHandled = true
      const feature = e.features[0]
      // Feature ID is in feature.id (MVT feature ID), not properties.id
      const featureId = feature.id as number | undefined
      if (featureId) {
        gridStore.selectSubstation(featureId)
      } else {
        // Clustered or missing ID — use proximity lookup
        gridStore.selectSubstationByLocation(e.lngLat.lat, e.lngLat.lng)
      }
    }
  })

  // Click on pnode — show popup
  map.on('click', 'pnodes', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    // Don't show pnode popup if a substation was clicked at the same point
    if ((e.originalEvent as any)._substationHandled) return
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

  // Click on transmission line — show popup
  map.on('click', 'transmission-lines', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    const props = e.features[0].properties
    new maplibregl.Popup({ closeButton: true, maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(`
        <strong>Transmission Line</strong><br/>
        Voltage: ${props.voltage_kv ? props.voltage_kv + ' kV' : 'N/A'}<br/>
        Owner: ${props.owner || 'N/A'}<br/>
        From: ${props.sub_1 || 'N/A'}<br/>
        To: ${props.sub_2 || 'N/A'}
      `)
      .addTo(map)
  })

  // Click on feeder — show popup
  map.on('click', 'feeders', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    const props = e.features[0].properties
    new maplibregl.Popup({ closeButton: true, maxWidth: '260px' })
      .setLngLat(e.lngLat)
      .setHTML(`
        <strong>Feeder ${props.feeder_id_external || ''}</strong><br/>
        Capacity: ${props.capacity_mw ? props.capacity_mw + ' MW' : 'N/A'}<br/>
        Loading: ${props.peak_loading_pct != null ? props.peak_loading_pct.toFixed(1) + '%' : 'N/A'}<br/>
        Voltage: ${props.voltage_kv ? props.voltage_kv + ' kV' : 'N/A'}
      `)
      .addTo(map)
  })

  // Click on hosting capacity feeder — show popup + select in store
  map.on('click', 'hosting-capacity', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    const props = e.features[0].properties
    const coords = (e.features[0].geometry as any).coordinates.slice()
    const hc = props.hosting_capacity_mw != null ? Number(props.hosting_capacity_mw).toFixed(1) : '?'
    const rem = props.remaining_capacity_mw != null ? Number(props.remaining_capacity_mw).toFixed(1) : '?'
    const dg = props.installed_dg_mw != null ? Number(props.installed_dg_mw).toFixed(1) : '?'
    new maplibregl.Popup({ closeButton: true, maxWidth: '280px' })
      .setLngLat(coords)
      .setHTML(`
        <strong>${props.feeder_name || props.feeder_id_external}</strong><br/>
        Hosting: ${hc} MW<br/>
        Remaining: ${rem} MW<br/>
        Installed DG: ${dg} MW<br/>
        Constraint: ${props.constraining_metric || 'N/A'}<br/>
        Voltage: ${props.voltage_kv ? props.voltage_kv + ' kV' : 'N/A'}
      `)
      .addTo(map)

    // Drive the detail panel
    const feeder = enrichStore.hcFeeders.find(f => f.id === props.id)
    if (feeder) enrichStore.selectFeederItem(feeder)
  })

  // Hover highlight for infrastructure power lines
  let hoveredInfraLineId: number | string | null = null
  map.on('mousemove', 'infra-power-lines', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    if (hoveredInfraLineId !== null) {
      map.setFeatureState({ source: 'gpkg_power_lines-source', sourceLayer: 'gpkg_power_lines', id: hoveredInfraLineId }, { hover: false })
    }
    hoveredInfraLineId = e.features[0].id ?? null
    if (hoveredInfraLineId !== null) {
      map.setFeatureState({ source: 'gpkg_power_lines-source', sourceLayer: 'gpkg_power_lines', id: hoveredInfraLineId }, { hover: true })
    }
  })
  map.on('mouseleave', 'infra-power-lines', () => {
    if (map && hoveredInfraLineId !== null) {
      map.setFeatureState({ source: 'gpkg_power_lines-source', sourceLayer: 'gpkg_power_lines', id: hoveredInfraLineId }, { hover: false })
      hoveredInfraLineId = null
    }
  })

  // Click on infrastructure power line
  map.on('click', 'infra-power-lines', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    const props = e.features[0].properties
    new maplibregl.Popup({ closeButton: true, maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(`
        <strong>${props.name || 'Power Line'}</strong><br/>
        Voltage: ${props.max_voltage_kv ? props.max_voltage_kv + ' kV' : 'N/A'}<br/>
        Operator: ${props.operator || 'N/A'}<br/>
        Circuits: ${props.circuits || 'N/A'}<br/>
        Location: ${props.location || 'N/A'}
      `)
      .addTo(map)
  })

  // Click on infrastructure substation — try to match to DB substation
  map.on('click', 'infra-substations-fill', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    // Try to open SubstationPanel via proximity match
    gridStore.selectSubstationByLocation(e.lngLat.lat, e.lngLat.lng).then(match => {
      if (!match && map) {
        // No DB match — show basic popup
        const props = e.features![0].properties
        new maplibregl.Popup({ closeButton: true, maxWidth: '280px' })
          .setLngLat(e.lngLat)
          .setHTML(`
            <strong>${props.name || 'Substation'}</strong><br/>
            Type: ${props.substation_type || 'N/A'}<br/>
            Voltage: ${props.max_voltage_kv ? props.max_voltage_kv + ' kV' : 'N/A'}<br/>
            Operator: ${props.operator || 'N/A'}
          `)
          .addTo(map)
      }
    })
  })

  // Click on infrastructure power plant
  map.on('click', 'infra-power-plants-fill', (e) => {
    if (!map || !e.features || e.features.length === 0) return
    const props = e.features[0].properties
    new maplibregl.Popup({ closeButton: true, maxWidth: '280px' })
      .setLngLat(e.lngLat)
      .setHTML(`
        <strong>${props.name || 'Power Plant'}</strong><br/>
        Source: ${props.source || 'N/A'}<br/>
        Method: ${props.method || 'N/A'}<br/>
        Output: ${props.output_mw ? props.output_mw + ' MW' : 'N/A'}<br/>
        Operator: ${props.operator || 'N/A'}
      `)
      .addTo(map)
  })

  // Click on BA marker
  map.on('click', 'ba-markers-circle', (e) => {
    if (e.features && e.features.length > 0) {
      const props = e.features[0].properties
      if (props.ba_code) {
        gridStore.selectBA(props.ba_code)
      }
    }
  })

  // Click on IQ marker - show popup
  map.on('click', 'iq-markers-circle', (e) => {
    if (e.features && e.features.length > 0 && map) {
      const feat = e.features[0]
      const coords = (feat.geometry as any).coordinates.slice()
      const p = feat.properties
      new maplibregl.Popup({ closeButton: true, maxWidth: '240px' })
        .setLngLat(coords)
        .setHTML(`
          <div style="font-size: 13px;">
            <strong>${p.project_name || 'Unnamed'}</strong><br/>
            ${p.generation_type || '-'} | ${p.capacity_mw ?? '-'} MW<br/>
            Status: ${p.queue_status || '-'}<br/>
            ${p.proposed_online_date ? 'Online: ' + p.proposed_online_date : ''}
          </div>
        `)
        .addTo(map)
    }
  })

  // Click on map background (for siting)
  map.on('click', (e) => {
    // Only trigger if no feature was clicked
    const features = map!.queryRenderedFeatures(e.point, {
      layers: interactiveLayers.filter(l => map!.getLayer(l)),
    })
    if (features.length === 0) {
      mapStore.setClickedPoint({ lat: e.lngLat.lat, lng: e.lngLat.lng })
      selectionStore.clickMap(e.lngLat.lat, e.lngLat.lng)
    }
  })

  // Add empty GeoJSON sources for BA markers and IQ markers
  map.addSource('ba-markers-source', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })
  map.addLayer({
    id: 'ba-markers-circle',
    type: 'circle',
    source: 'ba-markers-source',
    layout: { visibility: 'none' },
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['get', 'peak_import_ratio'],
        0, 4,
        100, 12,
      ],
      'circle-color': [
        'interpolate', ['linear'], ['get', 'congestion_score'],
        0, '#22c55e',
        0.3, '#eab308',
        0.6, '#f59e0b',
        0.9, '#ef4444',
      ],
      'circle-stroke-width': 1,
      'circle-stroke-color': 'rgba(0,0,0,0.3)',
      'circle-opacity': 0.8,
    },
  })

  map.addSource('iq-markers-source', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })
  map.addLayer({
    id: 'iq-markers-circle',
    type: 'circle',
    source: 'iq-markers-source',
    layout: { visibility: 'none' },
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['coalesce', ['get', 'capacity_mw'], 1],
        1, 4,
        100, 10,
        500, 14,
      ],
      'circle-color': [
        'match', ['get', 'queue_status'],
        'active', '#22c55e',
        'completed', '#38bdf8',
        'withdrawn', '#6b7280',
        '#fb923c',
      ],
      'circle-stroke-width': 1.5,
      'circle-stroke-color': 'rgba(0,0,0,0.3)',
      'circle-opacity': 0.8,
    },
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
// Switch zone color mode between classification, value, and severity
watch(() => mapStore.zoneColorMode, (mode) => {
  if (!map) return
  let color: ExpressionSpecification
  if (mode === 'severity') {
    color = severityColor
  } else if (mode === 'value') {
    color = [
      'interpolate', ['linear'],
      ['coalesce', ['get', 'transmission_score'], 0],
      0, '#22c55e',
      30, '#eab308',
      60, '#f59e0b',
      100, '#ef4444',
    ] as unknown as ExpressionSpecification
  } else {
    color = classificationColor
  }
  if (map.getLayer('zones-fill')) {
    map.setPaintProperty('zones-fill', 'fill-color', color)
  }
  if (map.getLayer('zones-outline')) {
    map.setPaintProperty('zones-outline', 'line-color', color)
  }
})
watch(() => mapStore.showTransmissionLines, (v) => {
  setLayerVisibility('transmission-lines', v)
  setLayerVisibility('transmission-lines-label', v)
})
watch(() => mapStore.showFeeders, (v) => {
  setLayerVisibility('feeders', v)
})
watch(() => mapStore.showAssets, (v) => {
  // Assets not yet a vector tile layer
})
watch(() => mapStore.showHostingCapacity, (v) => {
  setLayerVisibility('hosting-capacity', v)
  if (!v) clearBboxMarkers()
})
// Infrastructure layers (GeoPackage/OSM)
watch(() => mapStore.showInfraLines, (v) => {
  setLayerVisibility('infra-power-lines', v)
  setLayerVisibility('infra-power-lines-label', v)
})
watch(() => mapStore.showInfraSubstations, (v) => {
  setLayerVisibility('infra-substations-fill', v)
  setLayerVisibility('infra-substations-outline', v)
  setLayerVisibility('infra-substations-label', v)
  // Also toggle the primary substations point layer
  setLayerVisibility('substations', v)
  setLayerVisibility('substations-count', v)
})
watch(() => mapStore.showInfraPowerPlants, (v) => {
  setLayerVisibility('infra-power-plants-fill', v)
  setLayerVisibility('infra-power-plants-outline', v)
  setLayerVisibility('infra-power-plants-label', v)
})

// BA markers: toggle visibility and load data
watch(() => mapStore.showBAMarkers, (v) => {
  setLayerVisibility('ba-markers-circle', v)
  if (v && gridStore.bas.length === 0) {
    gridStore.loadCongestionData()
  }
})

// Update BA markers GeoJSON when data loads
watch(() => [gridStore.mappableBAs, gridStore.scoresByBA] as const, ([bas, scores]) => {
  if (!map || !map.getSource('ba-markers-source')) return
  const features = bas
    .filter(ba => ba.latitude != null && ba.longitude != null)
    .map(ba => {
      const score = scores.get(ba.ba_code)
      return {
        type: 'Feature' as const,
        geometry: {
          type: 'Point' as const,
          coordinates: [ba.longitude!, ba.latitude!],
        },
        properties: {
          ba_code: ba.ba_code,
          ba_name: ba.ba_name,
          congestion_score: score?.congestion_opportunity_score ?? 0,
          peak_import_ratio: score?.max_import_pct_of_load ?? 0,
        },
      }
    })
  const source = map.getSource('ba-markers-source') as maplibregl.GeoJSONSource
  source.setData({ type: 'FeatureCollection', features })
})

// IQ markers: toggle visibility and load data on first enable
let iqLoaded = false
watch(() => mapStore.showInterconnectionQueue, async (v) => {
  setLayerVisibility('iq-markers-circle', v)
  if (v && !iqLoaded) {
    iqLoaded = true
    try {
      const projects = await allInterconnectionQueue()
      const features = projects
        .filter(p => p.lat != null && p.lon != null)
        .map(p => ({
          type: 'Feature' as const,
          geometry: {
            type: 'Point' as const,
            coordinates: [p.lon!, p.lat!],
          },
          properties: {
            project_name: p.project_name ?? '',
            generation_type: p.generation_type ?? '',
            capacity_mw: p.capacity_mw ?? 0,
            queue_status: p.queue_status ?? 'unknown',
            proposed_online_date: p.proposed_online_date ?? '',
          },
        }))
      if (!map) return
      const source = map.getSource('iq-markers-source') as maplibregl.GeoJSONSource
      if (source) {
        source.setData({ type: 'FeatureCollection', features })
      }
    } catch (e) {
      console.error('Failed to load interconnection queue:', e)
    }
  }
})

// Update HC GeoJSON source when filtered feeders change
watch(() => enrichStore.filteredFeeders, (feeders) => {
  if (!map || !map.getSource('hosting-capacity-source')) return
  const features = feeders
    .filter(f => f.centroid_lat != null && f.centroid_lon != null)
    .map(f => ({
      type: 'Feature' as const,
      geometry: {
        type: 'Point' as const,
        coordinates: [f.centroid_lon!, f.centroid_lat!],
      },
      properties: {
        id: f.id,
        feeder_id_external: f.feeder_id_external,
        feeder_name: f.feeder_name,
        hosting_capacity_mw: f.hosting_capacity_mw,
        remaining_capacity_mw: f.remaining_capacity_mw,
        installed_dg_mw: f.installed_dg_mw,
        constraining_metric: f.constraining_metric,
        voltage_kv: f.voltage_kv,
      },
    }))
  const source = map.getSource('hosting-capacity-source') as maplibregl.GeoJSONSource
  source.setData({ type: 'FeatureCollection', features })
})

// Zoom to utility extent and draw bbox outline when feeders load
function clearBboxMarkers() {
  for (const m of bboxMarkers) m.remove()
  bboxMarkers = []
}

function drawBboxOutline(bounds: [[number, number], [number, number]]) {
  clearBboxMarkers()
  if (!map) return
  const [[w, s], [e, n]] = bounds

  // Create a positioned SVG overlay for the bbox rectangle
  const el = document.createElement('div')
  el.className = 'hc-bbox-overlay'
  // Use a marker at SW corner; the SVG will stretch to cover the bbox
  const marker = new maplibregl.Marker({ element: el, anchor: 'bottom-left' })
    .setLngLat([w, s])
    .addTo(map)
  bboxMarkers.push(marker)

  // Update the overlay size on each render frame
  function updateOverlay() {
    if (!map || !el.parentElement) return
    const sw = map.project([w, s])
    const ne = map.project([e, n])
    const width = Math.abs(ne.x - sw.x)
    const height = Math.abs(sw.y - ne.y)
    el.style.width = `${width}px`
    el.style.height = `${height}px`
    el.style.border = '3px dashed #22d3ee'
    el.style.backgroundColor = 'rgba(34, 211, 238, 0.06)'
    el.style.pointerEvents = 'none'
    el.style.transformOrigin = 'bottom left'
  }

  updateOverlay()
  map.on('move', updateOverlay)
  // Store cleanup ref
  ;(marker as any)._hcCleanup = () => map?.off('move', updateOverlay)
}

watch(() => enrichStore.hcFeeders, (feeders) => {
  if (!map) return
  const withCoords = feeders.filter(f => f.centroid_lat != null && f.centroid_lon != null)
  if (withCoords.length === 0) {
    clearBboxMarkers()
    return
  }

  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity
  for (const f of withCoords) {
    if (f.centroid_lon! < minLon) minLon = f.centroid_lon!
    if (f.centroid_lon! > maxLon) maxLon = f.centroid_lon!
    if (f.centroid_lat! < minLat) minLat = f.centroid_lat!
    if (f.centroid_lat! > maxLat) maxLat = f.centroid_lat!
  }

  const padLon = (maxLon - minLon) * 0.03 || 0.05
  const padLat = (maxLat - minLat) * 0.03 || 0.05
  const bounds: [[number, number], [number, number]] = [
    [minLon - padLon, minLat - padLat],
    [maxLon + padLon, maxLat + padLat],
  ]

  drawBboxOutline(bounds)

  skipCenterSync = true
  map.fitBounds(bounds, { padding: 40, duration: 1200 })
  setTimeout(() => { skipCenterSync = false }, 1500)
})

// Update tile sources and pan when ISO selection changes
watch(() => [...selectionStore.selectedISOs], (isos, oldIsos) => {
  if (!map) return

  // Refresh tile source URLs with new ISO filter
  updateTileSourceUrls()

  // Pan to the most recently added ISO
  const newIso = isos.find(iso => !oldIsos?.includes(iso))
  if (newIso) {
    const view = ISO_VIEW[newIso]
    if (view) {
      skipCenterSync = true
      map.flyTo({ center: [view.lng, view.lat], zoom: view.zoom, duration: 1200 })
      setTimeout(() => { skipCenterSync = false }, 1500)
    }
  }
})

// Fly to BA centroid when a balancing authority is selected
watch(() => selectionStore.selectedBACode, (baCode) => {
  if (!map || !baCode) return
  const ba = gridStore.bas.find(b => b.ba_code === baCode)
  if (ba?.latitude != null && ba?.longitude != null) {
    skipCenterSync = true
    map.flyTo({ center: [ba.longitude, ba.latitude], zoom: 7, duration: 1200 })
    setTimeout(() => { skipCenterSync = false }, 1500)
  }
})

onMounted(() => {
  initMap()
})

onBeforeUnmount(() => {
  clearBboxMarkers()
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
