import type { FeatureCollection, Point } from 'geojson'
import type { ExpressionSpecification } from 'maplibre-gl'

import type { HeatmapResponse } from '@/api/client'
import { RISK_DISPLAY } from '@/lib/risk'

const NO_DATA = -1
const UNSHADED = 'rgba(0, 0, 0, 0)'

export type HourlyRisk = Record<string, number | null>

export function hourProperty(hour: number): string {
  return `h${hour}`
}

/**
 * Colour each point by the backend's risk level for this hour. Low and missing hours stay clear.
 *
 * This is a blurred circle layer rather than MapLibre's heatmap layer on purpose. A heatmap layer
 * colours by summed density, so No Travel can look as mild as Moderate, and a cluster of Moderate
 * points can look like No Travel. Here the colour always matches the legend.
 */
export function heatmapColor(hour: number): ExpressionSpecification {
  return [
    'match',
    ['coalesce', ['get', hourProperty(hour)], NO_DATA],
    1,
    RISK_DISPLAY.moderate.color,
    2,
    RISK_DISPLAY.high.color,
    3,
    RISK_DISPLAY.severe.color,
    4,
    RISK_DISPLAY.no_travel.color,
    UNSHADED,
  ]
}

export function heatmapToGeoJson(
  data: HeatmapResponse,
): FeatureCollection<Point, HourlyRisk> {
  return {
    type: 'FeatureCollection',
    features: data.points.map((coordinates, index) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates },
      properties: Object.fromEntries(
        data.risk[index].map((level, hour) => [hourProperty(hour), level]),
      ),
    })),
  }
}
