import client from './client'

export interface WattCarbonAsset {
  id: number
  wattcarbon_asset_id: string | null
  iso_code: string | null
  zone_code: string | null
  substation_name: string | null
  der_type: string
  eac_category: string | null
  capacity_mw: number
  lat: number | null
  lon: number | null
}

export interface WattCarbonAssetDetail extends WattCarbonAsset {
  feeder_id: number | null
  circuit_id: number | null
  nearest_pnode_name: string | null
  pnode_distance_km: number | null
  latest_valuation: {
    total_constraint_relief_value: number
    value_tier: string
    coincidence_factor: number
    value_breakdown: Record<string, number>
  } | null
  latest_retrospective: {
    actual_savings_mwh: number
    actual_constraint_relief_value: number
    retrospective_start: string | null
    retrospective_end: string | null
  } | null
}

export interface ProspectiveValuation {
  wattcarbon_asset_id: string
  zone_congestion_value: number
  pnode_multiplier: number
  substation_loading_value: number
  feeder_capacity_value: number
  total_constraint_relief_value: number
  coincidence_factor: number
  effective_capacity_mw: number
  value_per_kw_year: number
  value_tier: string
  value_breakdown: Record<string, number>
}

export interface RetrospectiveValuation {
  wattcarbon_asset_id: string
  actual_savings_mwh: number
  actual_constraint_relief_value: number
  actual_zone_congestion_value: number
  actual_substation_value: number
  actual_feeder_value: number
  retrospective_start: string | null
  retrospective_end: string | null
}

export async function fetchWattCarbonAssets(
  isoCode?: string,
  derType?: string,
): Promise<WattCarbonAsset[]> {
  const params: Record<string, string> = {}
  if (isoCode) params.iso_code = isoCode
  if (derType) params.der_type = derType
  const { data } = await client.get<WattCarbonAsset[]>('/wattcarbon/assets', { params })
  return data
}

export async function fetchWattCarbonAssetDetail(
  assetId: string,
): Promise<WattCarbonAssetDetail> {
  const { data } = await client.get<WattCarbonAssetDetail>(`/wattcarbon/assets/${assetId}`)
  return data
}

export async function computeAssetValuation(
  assetId: string,
  pipelineRunId?: number,
): Promise<ProspectiveValuation> {
  const params: Record<string, number> = {}
  if (pipelineRunId !== undefined) params.pipeline_run_id = pipelineRunId
  const { data } = await client.get<ProspectiveValuation>(
    `/wattcarbon/assets/${assetId}/valuation`,
    { params },
  )
  return data
}

export async function runRetrospectiveValuation(
  assetId: string,
  start: string,
  end: string,
  pipelineRunId?: number,
): Promise<RetrospectiveValuation> {
  const body: Record<string, string | number> = { start, end }
  if (pipelineRunId !== undefined) body.pipeline_run_id = pipelineRunId
  const { data } = await client.post<RetrospectiveValuation>(
    `/wattcarbon/assets/${assetId}/retrospective`,
    body,
  )
  return data
}
