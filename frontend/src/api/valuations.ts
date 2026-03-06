import client, { v1Client } from './client'
import type {
  ValueStack,
  DERComparisonItem,
  LocationRanking,
} from '@/types/constraints'

export async function prospectiveValuation(
  lat: number,
  lon: number,
  derType: string,
  capacityMw?: number,
): Promise<ValueStack> {
  const { data } = await client.post<ValueStack>('/valuations/prospective', {
    lat,
    lon,
    der_type: derType,
    capacity_mw: capacityMw ?? 1.0,
  })
  return data
}

export async function compareDERTypes(
  lat: number,
  lon: number,
): Promise<{ geo_resolution: any; comparisons: DERComparisonItem[] }> {
  const { data } = await client.get('/valuations/compare', {
    params: { lat, lon },
  })
  return data
}

export async function valueRankings(
  isoCode: string,
  derType: string,
  params?: { limit?: number; offset?: number },
): Promise<LocationRanking[]> {
  const { data } = await client.get<LocationRanking[]>('/valuations/rankings', {
    params: { iso_code: isoCode, der_type: derType, ...params },
  })
  return data
}

export interface BatchItem {
  lat: number
  lon: number
  der_type: string
  capacity_mw?: number
}

export async function batchValuation(
  items: BatchItem[],
  apiKey: string,
): Promise<any[]> {
  const { data } = await client.post('/valuations/batch', { items }, {
    headers: { 'X-API-Key': apiKey },
  })
  return data
}

// Legacy: create DER location (still on v1)
export async function createDERLocation(
  lat: number,
  lon: number,
  derType: string,
  capacityMw: number,
): Promise<any> {
  const { data } = await v1Client.post('/der-locations', {
    lat,
    lon,
    der_type: derType,
    capacity_mw: capacityMw,
    source: 'manual',
  })
  return data
}
