import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import type { ExpressionSpecification } from 'maplibre-gl'

import type { PlanResponse, RiskCode, Route } from '@/api/client'
import { RISK_DISPLAY } from '@/lib/risk'

export interface SegmentProperties {
  route_id: string
  risk: RiskCode
}

export interface CheckpointProperties extends SegmentProperties {
  id: string
}

export type Bounds = [west: number, south: number, east: number, north: number]

export interface RouteLabel {
  route: Route
  lon: number
  lat: number
}

export const ROUTE_HIT_LAYER = 'route-hit-area'
export const CHECKPOINT_LAYER = 'checkpoints'

// Different positions along each line, so labels stay apart where routes share a road.
const LABEL_POSITIONS = [0.5, 0.35, 0.65]

export const RISK_COLOR_EXPRESSION = [
  'match',
  ['get', 'risk'],
  ...Object.entries(RISK_DISPLAY).flatMap(([risk, { color }]) => [risk, color]),
  RISK_DISPLAY.unknown.color,
] as unknown as ExpressionSpecification

export function selectedValue(
  selectedRouteId: string | null,
  whenSelected: number,
  otherwise: number,
): ExpressionSpecification {
  return [
    'case',
    ['==', ['get', 'route_id'], selectedRouteId ?? ''],
    whenSelected,
    otherwise,
  ]
}

export function routesToSegments(
  plan: PlanResponse,
): FeatureCollection<LineString, SegmentProperties> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((route) =>
      route.segments.map((segment): Feature<LineString, SegmentProperties> => ({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: segment.coordinates },
        properties: { route_id: route.id, risk: segment.risk },
      })),
    ),
  }
}

export function checkpointsToPoints(
  plan: PlanResponse,
): FeatureCollection<Point, CheckpointProperties> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((route) =>
      route.checkpoints.map(
        (checkpoint): Feature<Point, CheckpointProperties> => ({
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [checkpoint.lon, checkpoint.lat],
          },
          properties: {
            id: checkpoint.id,
            route_id: route.id,
            risk: checkpoint.risk,
          },
        }),
      ),
    ),
  }
}

export function planBounds(plan: PlanResponse): Bounds | null {
  let bounds: Bounds | null = null
  for (const route of plan.routes) {
    for (const [lon, lat] of route.geometry.coordinates) {
      bounds = bounds
        ? [
            Math.min(bounds[0], lon),
            Math.min(bounds[1], lat),
            Math.max(bounds[2], lon),
            Math.max(bounds[3], lat),
          ]
        : [lon, lat, lon, lat]
    }
  }
  return bounds
}

export function routeLabelPositions(plan: PlanResponse): RouteLabel[] {
  return plan.routes.map((route, index) => {
    const { coordinates } = route.geometry
    const fraction = LABEL_POSITIONS[index % LABEL_POSITIONS.length]
    const [lon, lat] = coordinates[Math.floor(coordinates.length * fraction)]
    return { route, lon, lat }
  })
}
