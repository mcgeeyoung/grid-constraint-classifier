import client from './client'

export interface Substation {
  id: number
  substation_name: string | null
  bank_name: string | null
  division: string | null
  facility_rating_mw: number | null
  facility_loading_mw: number | null
  peak_loading_pct: number | null
  facility_type: string | null
  lat: number | null
  lon: number | null
  zone_code: string | null
  nearest_pnode_name: string | null
}

export interface SubstationDetail extends Substation {
  zone_id: number | null
  nearest_pnode_id: number | null
  feeder_count: number
}

export interface Feeder {
  id: number
  substation_id: number
  feeder_id_external: string | null
  capacity_mw: number | null
  peak_loading_mw: number | null
  peak_loading_pct: number | null
  voltage_kv: number | null
}

export interface HierarchyScore {
  id: number
  pipeline_run_id: number
  level: string
  entity_id: number
  congestion_score: number | null
  loading_score: number | null
  combined_score: number | null
  constraint_tier: string | null
  entity_name: string | null
}

export async function fetchSubstations(
  isoCode: string,
  zoneCode?: string,
  minLoadingPct?: number,
): Promise<Substation[]> {
  const params: Record<string, string | number> = {}
  if (zoneCode) params.zone_code = zoneCode
  if (minLoadingPct !== undefined) params.min_loading_pct = minLoadingPct
  const { data } = await client.get<Substation[]>(`/isos/${isoCode}/substations`, { params })
  return data
}

export async function fetchSubstationDetail(substationId: number): Promise<SubstationDetail> {
  const { data } = await client.get<SubstationDetail>(`/substations/${substationId}`)
  return data
}

export async function fetchFeeders(
  substationId: number,
): Promise<Feeder[]> {
  const { data } = await client.get<Feeder[]>(`/substations/${substationId}/feeders`)
  return data
}

export async function fetchHierarchyScores(
  level?: string,
  entityId?: number,
): Promise<HierarchyScore[]> {
  const params: Record<string, string | number> = {}
  if (level) params.level = level
  if (entityId !== undefined) params.entity_id = entityId
  const { data } = await client.get<HierarchyScore[]>('/hierarchy-scores', { params })
  return data
}
