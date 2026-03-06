export interface ConstraintProfile {
  id: number
  location_level: string
  location_id: number
  location_name?: string
  constraint_type: string
  period_year: number
  profile_12x24: Record<string, number[]>
  peak_intensity: number
  peak_month: number
  peak_hour: number
  mean_intensity: number
  total_constrained_hours: number
  constrained_hours_pct: number
  severity_score: number
  severity_tier: string
  avg_marginal_cost?: number
  annual_cost?: number
  annotations: Annotation[]
}

export interface Annotation {
  id: number
  annotation_type: string
  title: string
  summary?: string
  planned_solution?: string
  deferral_value_estimate?: number
  source_url?: string
  confidence: number
}

export interface ZoneConstraintSummary {
  iso_code: string
  zone_code: string
  zone_name: string
  centroid_lat?: number
  centroid_lon?: number
  primary_constraint_type?: string
  severity_score?: number
  severity_tier?: string
  peak_month?: number
  peak_hour?: number
  constrained_hours_pct?: number
  best_der_type?: string
  best_der_value_per_kw_year?: number
  annotation_count: number
}

export interface GeoResolution {
  lat: number
  lon: number
  iso_code: string | null
  zone_code: string | null
  substation_name?: string | null
  nearest_pnode_name?: string | null
  feeder_id?: number | null
  resolution_depth: string
  constraints: ConstraintLayer[]
  best_der?: string | null
  total_value_per_kw_year?: number | null
}

export interface ConstraintLayer {
  constraint_type: string
  severity_score: number
  severity_tier: string
  peak_month: number
  peak_hour: number
}

export interface ValueStack {
  geo_resolution: GeoResolution
  congestion_value_per_kw_year: number
  loading_value_per_kw_year: number
  capacity_value_per_kw_year: number
  import_stress_value_per_kw_year: number
  total_value_per_kw_year: number
  composite_coincidence_factor: number
  value_tier: string
  constraint_layers: ConstraintLayer[]
  annotations: Annotation[]
}

export interface DERProfile {
  id: number
  der_type: string
  eac_category: string
  profile_12x24?: Record<string, number[]>
  is_dispatchable: boolean
  max_dispatch_hours?: number
  dispatch_power_mw?: number
  capacity_factor?: number
}

export interface Intersection {
  constraint_profile: ConstraintProfile
  der_profile: DERProfile
  coincidence_factor: number
  overlap_hours: number
  overlap_12x24?: Record<string, number[]>
  value_per_kw_year: number
  value_tier: string
}

export interface DERComparisonItem {
  der_type: string
  eac_category: string
  total_value_per_kw_year: number
  coincidence_factor: number
  value_tier: string
  is_dispatchable: boolean
}

export interface LocationRanking {
  location_level: string
  location_id: number
  location_name?: string
  lat?: number
  lon?: number
  total_value_per_kw_year: number
  value_tier: string
  coincidence_factor: number
}

export interface GridLevelScore {
  level: string
  name?: string | null
  constraint_loadshape?: Record<string, number[]> | null
  grid_score?: number | null
  score_label: string
  tier?: string | null
  coincidence_factor?: number | null
  overlap_12x24?: Record<string, number[]> | null
}

export interface DERGridScores {
  location: {
    lat: number
    lon: number
    iso_code?: string | null
    zone_code?: string | null
    substation_name?: string | null
    ba_code?: string | null
  }
  der_type: string
  der_profile_12x24?: Record<string, number[]> | null
  levels: GridLevelScore[]
}

export interface LoadshapeHour {
  hour: number
  avg_congestion: number
}

export interface ISO {
  id?: number
  iso_code: string
  iso_name: string
  timezone: string
  has_decomposition: boolean
  has_node_pricing?: boolean
  ba_code?: string | null
  is_rto?: boolean
}

export interface PnodeScore {
  node_id_external: string
  node_name: string | null
  severity_score: number
  tier: string
  avg_congestion: number | null
  max_congestion: number | null
  congested_hours_pct: number | null
  lat: number | null
  lon: number | null
}

export interface ZoneLMP {
  timestamp_utc: string
  lmp: number
  energy: number | null
  congestion: number | null
  loss: number | null
  hour_local: number
  month: number
}

export interface HCFeeder {
  feeder_name: string | null
  substation_name: string | null
  hosting_capacity_mw: number | null
  remaining_capacity_mw: number | null
  constraining_metric: string | null
  capacity_status: string | null
  has_ica: string | null
  utility_code?: string
  distance_km?: number
}

export interface InterconnectionProject {
  project_name: string | null
  generation_type: string | null
  capacity_mw: number | null
  queue_status: string | null
  proposed_online_date: string | null
  lat: number | null
  lon: number | null
}

export interface UtilityFiling {
  id: number
  docket_number: string | null
  filing_type: string | null
  title: string | null
  filed_date: string | null
  source_url: string | null
  summary: string | null
}

export interface Utility {
  id: number
  utility_name: string
  utility_id_eia: string | null
  state: string | null
  ownership_type: string | null
}
