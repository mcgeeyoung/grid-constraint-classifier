import client, { v1Client } from './client'
import type {
  GeoResolution,
  ISO,
  ZoneConstraintSummary,
  ConstraintProfile,
  Annotation,
  PnodeScore,
  ZoneLMP,
} from '@/types/constraints'

export async function resolveLocation(lat: number, lon: number): Promise<GeoResolution> {
  const { data } = await client.get<GeoResolution>('/resolve', {
    params: { lat, lon },
  })
  return data
}

export async function listISOs(isRto?: boolean): Promise<ISO[]> {
  const params: Record<string, any> = {}
  if (isRto !== undefined) params.is_rto = isRto
  const { data } = await client.get<ISO[]>('/isos', { params })
  return data
}

export async function listZones(isoCode: string): Promise<ZoneConstraintSummary[]> {
  const { data } = await client.get<ZoneConstraintSummary[]>(`/zones/${isoCode}`)
  return data
}

export async function zoneGeometries(isoCode: string): Promise<any[]> {
  const { data } = await client.get<any[]>(`/zones/${isoCode}/geometry`)
  return data
}

export async function zoneConstraints(
  isoCode: string,
  zoneCode: string,
): Promise<{
  profiles: ConstraintProfile[]
  pnode_hotspots: PnodeScore[]
}> {
  const { data } = await client.get(`/zones/${isoCode}/${zoneCode}/constraints`)
  return data
}

export async function zoneLMPs(
  isoCode: string,
  zoneCode: string,
  params?: { limit?: number; month?: number },
): Promise<ZoneLMP[]> {
  const { data } = await client.get<ZoneLMP[]>(
    `/zones/${isoCode}/${zoneCode}/lmps`,
    { params },
  )
  return data
}

export async function locationProfile(
  level: string,
  locationId: number,
): Promise<ConstraintProfile> {
  const { data } = await client.get<ConstraintProfile>(
    `/locations/${level}/${locationId}/profile`,
  )
  return data
}

// Legacy v1 endpoints still used during transition (tile sources, data centers, etc.)
export async function fetchDataCenters(isoCodes?: string | string[]): Promise<any[]> {
  const params: Record<string, string | number> = { limit: 5000 }
  if (isoCodes) {
    params.iso_id = Array.isArray(isoCodes) ? isoCodes.join(',') : isoCodes
  }
  const { data } = await v1Client.get<any[]>('/data-centers', { params })
  return data
}

export async function fetchDERLocations(
  isoCode?: string | string[],
  zoneCode?: string,
  derType?: string,
): Promise<any[]> {
  const params: Record<string, string> = {}
  if (isoCode) {
    params.iso_id = Array.isArray(isoCode) ? isoCode.join(',') : isoCode
  }
  if (zoneCode) params.zone_code = zoneCode
  if (derType) params.der_type = derType
  const { data } = await v1Client.get<any[]>('/der-locations', { params })
  return data
}
