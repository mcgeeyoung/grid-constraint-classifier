import client from './client'

export interface GeoResolution {
  lat: number
  lon: number
  iso_code: string | null
  zone_code: string | null
  substation_name: string | null
  substation_distance_km: number | null
  nearest_pnode_name: string | null
  pnode_distance_km: number | null
  feeder_id: number | null
  circuit_id: number | null
  resolution_depth: string
  confidence: string
  errors: string[]
}

export interface ValuationResult {
  zone_congestion_value: number
  pnode_multiplier: number
  substation_loading_value: number
  feeder_capacity_value: number
  total_constraint_relief_value: number
  coincidence_factor: number
  effective_capacity_mw: number
  value_per_kw_year: number
  value_tier: string
  value_breakdown: Record<string, any>
  geo_resolution: GeoResolution
}

export interface DERLocation {
  id: number
  iso_code: string | null
  zone_code: string | null
  substation_name: string | null
  der_type: string
  eac_category: string | null
  capacity_mw: number
  lat: number | null
  lon: number | null
  source: string
  wattcarbon_asset_id: string | null
  resolution_depth?: string | null
}

export async function prospectiveValuation(
  lat: number,
  lon: number,
  derType: string,
  capacityMw: number,
): Promise<ValuationResult> {
  const { data } = await client.post<ValuationResult>('/valuations/prospective', {
    lat,
    lon,
    der_type: derType,
    capacity_mw: capacityMw,
  })
  return data
}

export async function geoResolve(lat: number, lon: number): Promise<GeoResolution> {
  const { data } = await client.get<GeoResolution>('/geo/resolve', {
    params: { lat, lon },
  })
  return data
}

export async function fetchDERLocations(
  isoCode?: string | string[],
  zoneCode?: string,
  derType?: string,
): Promise<DERLocation[]> {
  const params: Record<string, string> = {}
  if (isoCode) {
    params.iso_id = Array.isArray(isoCode) ? isoCode.join(',') : isoCode
  }
  if (zoneCode) params.zone_code = zoneCode
  if (derType) params.der_type = derType
  const { data } = await client.get<DERLocation[]>('/der-locations', { params })
  return data
}

export async function createDERLocation(
  lat: number,
  lon: number,
  derType: string,
  capacityMw: number,
): Promise<DERLocation> {
  const { data } = await client.post<DERLocation>('/der-locations', {
    lat,
    lon,
    der_type: derType,
    capacity_mw: capacityMw,
    source: 'manual',
  })
  return data
}
