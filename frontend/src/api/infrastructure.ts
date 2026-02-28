/**
 * API client for GeoPackage infrastructure data (OSM power lines, substations, plants).
 */

import client from './client'

// ── Types ────────────────────────────────────────────────────────────

export interface GPKGPowerLine {
  id: number
  osm_id: number | null
  name: string | null
  operator: string | null
  max_voltage_kv: number | null
  voltages: string | null
  circuits: number | null
  location: string | null
}

export interface GPKGSubstation {
  id: number
  osm_id: number | null
  name: string | null
  operator: string | null
  substation_type: string | null
  max_voltage_kv: number | null
  voltages: string | null
  centroid_lat: number | null
  centroid_lon: number | null
}

export interface GPKGPowerPlant {
  id: number
  osm_id: number | null
  name: string | null
  operator: string | null
  source: string | null
  method: string | null
  output_mw: number | null
  centroid_lat: number | null
  centroid_lon: number | null
}

export interface LayerSummary {
  layer: string
  total_features: number
  with_name: number
  with_operator: number
}

export interface VoltageStatEntry {
  voltage_kv: number
  count: number
}

export interface TypeStatEntry {
  type: string
  count: number
}

export interface SourceStatEntry {
  source: string
  count: number
  total_output_mw: number | null
}

// ── API Calls ────────────────────────────────────────────────────────

export async function fetchInfrastructureSummary(): Promise<LayerSummary[]> {
  const { data } = await client.get<LayerSummary[]>('/infrastructure/summary')
  return data
}

export async function fetchPowerLines(params?: {
  limit?: number
  offset?: number
  bbox?: string
  min_voltage_kv?: number
  operator?: string
}): Promise<GPKGPowerLine[]> {
  const { data } = await client.get<GPKGPowerLine[]>('/infrastructure/power-lines', { params })
  return data
}

export async function fetchPowerLinesVoltageStats(bbox?: string): Promise<VoltageStatEntry[]> {
  const { data } = await client.get<{ voltage_distribution: VoltageStatEntry[] }>(
    '/infrastructure/power-lines/voltage-stats',
    { params: bbox ? { bbox } : undefined },
  )
  return data.voltage_distribution
}

export async function fetchSubstations(params?: {
  limit?: number
  offset?: number
  bbox?: string
  substation_type?: string
  operator?: string
  min_voltage_kv?: number
}): Promise<GPKGSubstation[]> {
  const { data } = await client.get<GPKGSubstation[]>('/infrastructure/substations', { params })
  return data
}

export async function fetchSubstationsTypeStats(bbox?: string): Promise<TypeStatEntry[]> {
  const { data } = await client.get<{ type_distribution: TypeStatEntry[] }>(
    '/infrastructure/substations/type-stats',
    { params: bbox ? { bbox } : undefined },
  )
  return data.type_distribution
}

export async function fetchPowerPlants(params?: {
  limit?: number
  offset?: number
  bbox?: string
  source?: string
  operator?: string
  min_output_mw?: number
}): Promise<GPKGPowerPlant[]> {
  const { data } = await client.get<GPKGPowerPlant[]>('/infrastructure/power-plants', { params })
  return data
}

export async function fetchPowerPlantsSourceStats(bbox?: string): Promise<SourceStatEntry[]> {
  const { data } = await client.get<{ source_distribution: SourceStatEntry[] }>(
    '/infrastructure/power-plants/source-stats',
    { params: bbox ? { bbox } : undefined },
  )
  return data.source_distribution
}
