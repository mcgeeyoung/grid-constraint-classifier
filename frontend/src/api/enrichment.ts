import client from './client'
import type {
  HCFeeder,
  InterconnectionProject,
  UtilityFiling,
  Utility,
} from '@/types/constraints'

export async function nearbyHostingCapacity(
  lat: number,
  lon: number,
  radiusKm = 10,
): Promise<HCFeeder[]> {
  const { data } = await client.get<HCFeeder[]>('/enrichment/hosting-capacity', {
    params: { lat, lon, radius_km: radiusKm },
  })
  return data
}

export async function nearbyInterconnection(
  lat: number,
  lon: number,
  radiusKm = 50,
): Promise<InterconnectionProject[]> {
  const { data } = await client.get<InterconnectionProject[]>(
    '/enrichment/interconnection-queue',
    { params: { lat, lon, radius_km: radiusKm } },
  )
  return data
}

export async function utilityFilings(
  utilityCode: string,
  filingType?: string,
): Promise<UtilityFiling[]> {
  const params: Record<string, string> = {}
  if (filingType) params.filing_type = filingType
  const { data } = await client.get<UtilityFiling[]>(
    `/enrichment/filings/${utilityCode}`,
    { params },
  )
  return data
}

export async function allInterconnectionQueue(): Promise<InterconnectionProject[]> {
  const { data } = await client.get<InterconnectionProject[]>(
    '/enrichment/interconnection-queue/all',
  )
  return data
}

export async function listUtilities(
  state?: string,
  isoCode?: string,
): Promise<Utility[]> {
  const params: Record<string, string> = {}
  if (state) params.state = state
  if (isoCode) params.iso_code = isoCode
  const { data } = await client.get<Utility[]>('/enrichment/utilities', { params })
  return data
}
