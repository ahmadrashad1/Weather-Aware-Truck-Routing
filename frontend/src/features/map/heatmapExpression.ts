import type { FeatureCollection, Point } from 'geojson'
import type { ExpressionSpecification } from 'maplibre-gl'

import type { HeatmapResponse } from '@/api/client'
import { RISK_DISPLAY } from '@/lib/risk'

const NO_DATA = -1
const LOW_OPACITY = 0.25
const RISK_OPACITY = 0.6
const MISSING_OPACITY = 0.45

export type HourlyRisk = Record<string, number | null>

export function hourProperty(hour: number): string {
  return `h${hour}`
}

/**
 * Colour each point by the backend's risk level for this hour, using the legend's colours.
 *
 * This is a blurred circle layer rather than MapLibre's heatmap layer on purpose. A heatmap layer
 * colours by summed density, so No Travel can look as mild as Moderate, and a cluster of Moderate
 * points can look like No Travel. Low is a faint tint and missing hours are grey, so a calm
 * forecast still shows the corridor, and missing data can't pass for safe.
 */
export function heatmapColor(hour: number): ExpressionSpecification {
  return [
    'match',
    ['coalesce', ['get', hourProperty(hour)], NO_DATA],
    0,
    withOpacity(RISK_DISPLAY.low.color, LOW_OPACITY),
    1,
    withOpacity(RISK_DISPLAY.moderate.color, RISK_OPACITY),
    2,
    withOpacity(RISK_DISPLAY.high.color, RISK_OPACITY),
    3,
    withOpacity(RISK_DISPLAY.severe.color, RISK_OPACITY),
    4,
    withOpacity(RISK_DISPLAY.no_travel.color, RISK_OPACITY),
    withOpacity(RISK_DISPLAY.unknown.color, MISSING_OPACITY),
  ]
}

function withOpacity(hex: string, opacity: number): string {
  const channel = (start: number) => parseInt(hex.slice(start, start + 2), 16)
  return `rgba(${channel(1)}, ${channel(3)}, ${channel(5)}, ${opacity})`
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
