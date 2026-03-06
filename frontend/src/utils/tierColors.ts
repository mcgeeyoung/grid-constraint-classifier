export function severityTierColor(tier: string | undefined): string {
  switch (tier) {
    case 'critical': return '#ef4444'
    case 'elevated': return '#f59e0b'
    case 'moderate': return '#eab308'
    case 'low': return '#22c55e'
    default: return '#6b7280'
  }
}

export function constraintTypeColor(type: string): string {
  switch (type) {
    case 'congestion': return '#38bdf8'
    case 'loading': return '#fb923c'
    case 'capacity': return '#4ade80'
    case 'import_stress': return '#c084fc'
    default: return '#6b7280'
  }
}

export function valueTierColor(tier: string): string {
  switch (tier) {
    case 'premium': return '#22c55e'
    case 'high': return '#4ade80'
    case 'moderate': return '#facc15'
    case 'low': return '#6b7280'
    default: return '#6b7280'
  }
}

export function severityBarColor(score: number): string {
  if (score >= 0.75) return '#ef4444'
  if (score >= 0.50) return '#f59e0b'
  if (score >= 0.25) return '#eab308'
  return '#22c55e'
}
