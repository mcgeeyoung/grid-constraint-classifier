import client from './client'

export interface ISO {
  iso_code: string
  iso_name: string
  timezone: string
  has_decomposition: boolean
  has_node_pricing: boolean
}

export interface Zone {
  zone_code: string
  zone_name: string | null
  centroid_lat: number | null
  centroid_lon: number | null
  states: string[] | null
}

export interface ZoneClassification {
  zone_code: string
  zone_name: string | null
  classification: string
  transmission_score: number
  generation_score: number
  avg_abs_congestion: number | null
  max_congestion: number | null
  congested_hours_pct: number | null
}

export interface DataCenter {
  external_slug: string | null
  facility_name: string | null
  status: string | null
  capacity_mw: number | null
  lat: number | null
  lon: number | null
  state_code: string | null
  county: string | null
  operator: string | null
  iso_code: string | null
  zone_code: string | null
}

export interface DERRecommendation {
  zone_code: string
  classification: string | null
  rationale: string | null
  congestion_value: number | null
  primary_rec: Record<string, any> | null
  secondary_rec: Record<string, any> | null
  tertiary_rec: Record<string, any> | null
}

export interface Overview {
  iso_code: string
  iso_name: string
  zones_count: number
  latest_run_year: number | null
  latest_run_status: string | null
  transmission_constrained: number
  generation_constrained: number
  both_constrained: number
  unconstrained: number
}

export async function fetchISOs(): Promise<ISO[]> {
  const { data } = await client.get<ISO[]>('/isos')
  return data
}

export async function fetchZones(isoCode: string): Promise<Zone[]> {
  const { data } = await client.get<Zone[]>(`/isos/${isoCode}/zones`)
  return data
}

export async function fetchClassifications(isoCode: string): Promise<ZoneClassification[]> {
  const { data } = await client.get<ZoneClassification[]>(`/isos/${isoCode}/classifications`)
  return data
}

export async function fetchDataCenters(isoCode?: string): Promise<DataCenter[]> {
  const params = isoCode ? { iso_id: isoCode } : {}
  const { data } = await client.get<DataCenter[]>('/data-centers', { params })
  return data
}

export async function fetchRecommendations(isoCode: string): Promise<DERRecommendation[]> {
  const { data } = await client.get<DERRecommendation[]>(`/isos/${isoCode}/recommendations`)
  return data
}

export async function fetchOverview(): Promise<Overview[]> {
  const { data } = await client.get<Overview[]>('/overview')
  return data
}
