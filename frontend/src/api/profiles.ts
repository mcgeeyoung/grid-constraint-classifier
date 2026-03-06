import client from './client'
import type {
  ConstraintProfile,
  DERProfile,
  DERGridScores,
  Intersection,
  LoadshapeHour,
} from '@/types/constraints'

export async function getConstraintProfile(profileId: number): Promise<ConstraintProfile> {
  const { data } = await client.get<ConstraintProfile>(`/profiles/constraint/${profileId}`)
  return data
}

export async function getDERProfile(derType: string): Promise<DERProfile> {
  const { data } = await client.get<DERProfile>(`/profiles/der/${derType}`)
  return data
}

export async function listDERProfiles(): Promise<DERProfile[]> {
  const { data } = await client.get<DERProfile[]>('/profiles/der')
  return data
}

export async function getIntersection(
  constraintProfileId: number,
  derType: string,
): Promise<Intersection> {
  const { data } = await client.get<Intersection>('/profiles/intersection', {
    params: { constraint_profile_id: constraintProfileId, der_type: derType },
  })
  return data
}

export async function getDERGridScores(
  lat: number,
  lon: number,
  derType: string,
): Promise<DERGridScores> {
  const { data } = await client.get<DERGridScores>('/profiles/der-grid-scores', {
    params: { lat, lon, der_type: derType },
  })
  return data
}

export async function zoneLoadshape(
  isoCode: string,
  zoneCode: string,
  month?: number,
): Promise<LoadshapeHour[]> {
  const params: Record<string, number> = {}
  if (month !== undefined) params.month = month
  const { data } = await client.get<LoadshapeHour[]>(
    `/profiles/zone/${isoCode}/${zoneCode}/loadshape`,
    { params },
  )
  return data
}
