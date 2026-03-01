import client from './client'

export interface BA {
  ba_code: string
  ba_name: string | null
  region: string | null
  interconnection: string | null
  is_rto: boolean
  rto_neighbor: string | null
  rto_neighbor_secondary: string | null
  interface_points: any[] | null
  latitude: number | null
  longitude: number | null
  transfer_limit_mw: number | null
  transfer_limit_method: string | null
}

export interface CongestionScore {
  ba_code: string
  ba_name: string | null
  region: string | null
  period_start: string
  period_end: string
  period_type: string | null
  hours_total: number | null
  hours_importing: number | null
  pct_hours_importing: number | null
  hours_above_80: number | null
  hours_above_90: number | null
  hours_above_95: number | null
  avg_import_pct_of_load: number | null
  max_import_pct_of_load: number | null
  avg_congestion_premium: number | null
  congestion_opportunity_score: number | null
  transfer_limit_used: number | null
  lmp_coverage: string | null
  data_quality_flag: string | null
}

export interface DurationCurve {
  ba_code: string
  ba_name: string | null
  year: number
  transfer_limit_mw: number | null
  values: number[]
  hours_count: number
}

export interface HourlyData {
  timestamp_utc: string
  demand_mw: number | null
  net_generation_mw: number | null
  total_interchange_mw: number | null
  net_imports_mw: number | null
  import_utilization: number | null
}

export async function fetchBAs(rtoOnly = false): Promise<BA[]> {
  const { data } = await client.get<BA[]>('/congestion/bas', {
    params: { rto_only: rtoOnly },
  })
  return data
}

export async function fetchScores(
  periodType = 'year',
  year?: number,
): Promise<CongestionScore[]> {
  const { data } = await client.get<CongestionScore[]>('/congestion/scores', {
    params: { period_type: periodType, year },
  })
  return data
}

export async function fetchBAScores(
  baCode: string,
  periodType = 'month',
  year?: number,
): Promise<CongestionScore[]> {
  const { data } = await client.get<CongestionScore[]>(
    `/congestion/scores/${baCode}`,
    { params: { period_type: periodType, year } },
  )
  return data
}

export async function fetchDurationCurve(
  baCode: string,
  year = 2024,
): Promise<DurationCurve> {
  const { data } = await client.get<DurationCurve>(
    `/congestion/duration-curve/${baCode}`,
    { params: { year } },
  )
  return data
}

export async function fetchHourlyData(
  baCode: string,
  start: string,
  end: string,
): Promise<HourlyData[]> {
  const { data } = await client.get<HourlyData[]>(
    `/congestion/hourly/${baCode}`,
    { params: { start, end } },
  )
  return data
}
