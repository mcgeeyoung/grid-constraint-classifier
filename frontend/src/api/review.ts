import client from './client'

export interface ReviewItem {
  id: number
  extraction_type: string
  confidence: string
  review_status: string
  source_file: string | null
  llm_model: string | null
  utility_name: string | null
  docket_number: string | null
  record_count: number
  created_at: string | null
  reviewed_at: string | null
}

export interface ReviewDetail {
  id: number
  extraction_type: string
  extracted_data: Record<string, any>
  confidence: string
  review_status: string
  source_file: string | null
  raw_text_snippet: string | null
  source_page: number | null
  llm_model: string | null
  extraction_notes: string | null
  reviewer_notes: string | null
  promoted_count: number | null
  utility_id: number | null
  utility_name: string | null
  filing_id: number | null
  docket_number: string | null
  created_at: string | null
  reviewed_at: string | null
}

export interface ReviewStats {
  total: number
  pending: number
  approved: number
  rejected: number
  edited: number
  by_type: Record<string, number>
  by_confidence: Record<string, number>
}

export async function fetchReviewQueue(params: {
  status?: string
  extraction_type?: string
  confidence?: string
  limit?: number
  offset?: number
} = {}): Promise<ReviewItem[]> {
  const { data } = await client.get<ReviewItem[]>('/review/queue', { params })
  return data
}

export async function fetchReviewStats(): Promise<ReviewStats> {
  const { data } = await client.get<ReviewStats>('/review/stats')
  return data
}

export async function fetchReviewItem(id: number): Promise<ReviewDetail> {
  const { data } = await client.get<ReviewDetail>(`/review/queue/${id}`)
  return data
}

export async function approveItem(
  id: number,
  reviewerNotes?: string,
): Promise<ReviewDetail> {
  const { data } = await client.post<ReviewDetail>(
    `/review/queue/${id}/approve`,
    { reviewer_notes: reviewerNotes },
  )
  return data
}

export async function rejectItem(
  id: number,
  reviewerNotes?: string,
): Promise<ReviewDetail> {
  const { data } = await client.post<ReviewDetail>(
    `/review/queue/${id}/reject`,
    { reviewer_notes: reviewerNotes },
  )
  return data
}

export async function editAndApprove(
  id: number,
  extractedData: Record<string, any>,
  reviewerNotes?: string,
): Promise<ReviewDetail> {
  const { data } = await client.put<ReviewDetail>(
    `/review/queue/${id}`,
    { extracted_data: extractedData, reviewer_notes: reviewerNotes },
  )
  return data
}
