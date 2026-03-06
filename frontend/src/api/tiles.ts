export function tileUrl(layer: string, isoCode?: string): string {
  const params = isoCode ? `?iso_code=${isoCode}` : ''
  return `/api/v1/tiles/${layer}/{z}/{x}/{y}.mvt${params}`
}

export function gpkgTileUrl(layer: string): string {
  return `/api/v1/tiles/gpkg/${layer}/{z}/{x}/{y}.mvt`
}
