export const DER_LABELS: Record<string, string> = {
  solar: 'Solar',
  wind: 'Wind',
  storage: 'Storage',
  demand_response: 'Demand Response',
  energy_efficiency: 'Energy Efficiency',
  weatherization: 'Weatherization',
  combined_heat_power: 'CHP',
  fuel_cell: 'Fuel Cell',
}

export function derLabel(type: string): string {
  return DER_LABELS[type] ?? type
}
