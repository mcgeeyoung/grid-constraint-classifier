export function formatCurrency(value: number, decimals = 0): string {
  return `$${value.toFixed(decimals)}`
}

export function formatPercent(value: number, decimals = 1): string {
  return `${(value * 100).toFixed(decimals)}%`
}
