import client from './client'

export interface HCFeeder {
  id: number
  utility_code: string
  feeder_id_external: string
  feeder_name: string | null
  substation_name: string | null
  hosting_capacity_mw: number | null
  hosting_capacity_min_mw: number | null
  hosting_capacity_max_mw: number | null
  remaining_capacity_mw: number | null
  installed_dg_mw: number | null
  queued_dg_mw: number | null
  constraining_metric: string | null
  voltage_kv: number | null
  phase_config: string | null
  centroid_lat: number | null
  centroid_lon: number | null
}

export interface HCUtility {
  utility_code: string
  utility_name: string
  parent_company: string | null
  iso_code: string | null
  states: string[] | null
  data_source_type: string
  total_feeders: number | null
  total_hosting_capacity_mw: number | null
  total_remaining_capacity_mw: number | null
  last_ingested_at: string | null
}

export interface HCSummary {
  utility_code: string
  utility_name: string
  total_feeders: number
  total_hosting_capacity_mw: number
  total_installed_dg_mw: number
  total_remaining_capacity_mw: number
  avg_utilization_pct: number | null
  constrained_feeders_count: number
  constraint_breakdown: Record<string, number> | null
  computed_at: string | null
}

export async function fetchUtilities(): Promise<HCUtility[]> {
  const { data } = await client.get<HCUtility[]>('/utilities')
  return data
}

export async function fetchHostingCapacity(
  utilityCode: string,
  options?: { bbox?: string; limit?: number; constraint?: string },
): Promise<HCFeeder[]> {
  const params: Record<string, string | number> = {}
  if (options?.bbox) params.bbox = options.bbox
  if (options?.limit) params.limit = options.limit
  if (options?.constraint) params.constraint = options.constraint
  const { data } = await client.get<HCFeeder[]>(
    `/utilities/${utilityCode}/hosting-capacity`,
    { params },
  )
  return data
}

export async function fetchHostingCapacityGeoJSON(
  utilityCode: string,
  options?: { bbox?: string; limit?: number },
): Promise<GeoJSON.FeatureCollection> {
  const params: Record<string, string | number> = {}
  if (options?.bbox) params.bbox = options.bbox
  if (options?.limit) params.limit = options.limit
  const { data } = await client.get<GeoJSON.FeatureCollection>(
    `/utilities/${utilityCode}/hosting-capacity/geojson`,
    { params },
  )
  return data
}

export async function fetchHCSummary(utilityCode: string): Promise<HCSummary> {
  const { data } = await client.get<HCSummary>(
    `/utilities/${utilityCode}/hosting-capacity/summary`,
  )
  return data
}
