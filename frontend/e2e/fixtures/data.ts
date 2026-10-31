import type { components } from '../../src/api/schema.d.ts'

type Schemas = components['schemas']
export type PlanResponse = Schemas['PlanResponse']
export type HeatmapResponse = Schemas['HeatmapResponse']
type Route = Schemas['Route']
type Checkpoint = Schemas['Checkpoint']
type Risk = Schemas['RiskOrUnknownEnum']

// Typed against the API schema, so a change to the API fails the type check here too.

export const DALLAS = { label: 'Dallas, TX', lat: 32.78, lon: -96.8 }
export const DENVER = { label: 'Denver, CO', lat: 39.74, lon: -104.99 }

const DEPARTURE_MS = Date.parse('2026-11-01T15:00:00Z')
const MILES = 800
const SECONDS = 48_000

function line(bendLon: number, bendLat: number): number[][] {
  return [
    [DALLAS.lon, DALLAS.lat],
    [bendLon, bendLat],
    [DENVER.lon, DENVER.lat],
  ]
}

function along(coordinates: number[][], fraction: number): [number, number] {
  const scaled = fraction * (coordinates.length - 1)
  const index = Math.min(Math.floor(scaled), coordinates.length - 2)
  const part = scaled - index
  const [lonA, latA] = coordinates[index]
  const [lonB, latB] = coordinates[index + 1]
  return [lonA + (lonB - lonA) * part, latA + (latB - latA) * part]
}

function checkpoint(
  routeId: string,
  index: number,
  coordinates: number[][],
  risk: Risk,
): Checkpoint {
  const fraction = index / 4
  const [lon, lat] = along(coordinates, fraction)
  const known = risk !== 'unknown'
  return {
    id: `${routeId}-${index}`,
    mile: MILES * fraction,
    lat,
    lon,
    eta: new Date(DEPARTURE_MS + SECONDS * fraction * 1000).toISOString(),
    represented_miles: MILES / 4,
    weather: known ? { wind_mph: 38.2, rain_in_hr: 0.12, snow_in_hr: 0 } : null,
    risk,
    wind_risk: known ? (risk as Schemas['RiskEnum']) : null,
    rain_risk: known ? 'moderate' : null,
    snow_risk: known ? 'low' : null,
    load_adjusted: risk === 'severe',
    drivers: known && risk !== 'low' ? ['wind'] : [],
  }
}

function route(
  id: string,
  rank: number,
  coordinates: number[][],
  risks: Risk[],
  summary: Partial<Schemas['RouteSummary']>,
  rationale: string,
): Route {
  return {
    id,
    rank,
    rationale,
    summary: {
      distance_miles: MILES,
      duration_seconds: SECONDS,
      arrival_at: new Date(DEPARTURE_MS + SECONDS * 1000).toISOString(),
      severe_miles: 0,
      high_miles: 0,
      moderate_miles: 0,
      low_miles: MILES,
      no_travel_miles: 0,
      unknown_miles: 0,
      average_risk: 0,
      ...summary,
    },
    geometry: { type: 'LineString', coordinates },
    segments: risks.slice(0, 4).map((risk, index) => ({
      risk,
      from_mile: (MILES / 4) * index,
      to_mile: (MILES / 4) * (index + 1),
      coordinates: [
        along(coordinates, index / 4),
        along(coordinates, (index + 1) / 4),
      ],
    })),
    checkpoints: risks.map((risk, index) =>
      checkpoint(id, index, coordinates, risk),
    ),
  }
}

export const NORTH = line(-98, 38.5)
export const MIDDLE = line(-101, 36)
export const SOUTH = line(-103, 33.5)

export const plan: PlanResponse = {
  recommended_route_id: 'route-2',
  no_safe_route: false,
  warnings: [],
  routes: [
    route(
      'route-2',
      1,
      MIDDLE,
      ['low', 'low', 'moderate', 'low', 'low'],
      { moderate_miles: 200, low_miles: 600, average_risk: 0.25 },
      'Recommended for fewest Severe miles (0.0 vs 200.0).',
    ),
    route(
      'route-1',
      2,
      SOUTH,
      ['low', 'severe', 'high', 'low', 'low'],
      {
        severe_miles: 200,
        high_miles: 200,
        low_miles: 400,
        average_risk: 1.25,
        duration_seconds: 40_000,
      },
      'Ranks lower for more Severe miles (200.0 vs 0.0).',
    ),
    route(
      'route-3',
      3,
      NORTH,
      ['low', 'no_travel', 'unknown', 'low', 'low'],
      {
        no_travel_miles: 200,
        unknown_miles: 200,
        low_miles: 400,
        average_risk: 1.33,
      },
      'Has 200 No Travel miles, so it cannot be recommended.',
    ),
  ],
}

export const noSafeRoutePlan: PlanResponse = {
  ...plan,
  recommended_route_id: null,
  no_safe_route: true,
}

const FRAMES = 49

function frames(level: (hour: number) => number | null): (number | null)[] {
  return Array.from({ length: FRAMES }, (_, hour) => level(hour))
}

function heatPoints(): number[][] {
  const points: number[][] = []
  for (let lon = -105; lon <= -96; lon += 0.75) {
    for (let lat = 32.5; lat <= 40; lat += 0.75) {
      points.push([lon, lat])
    }
  }
  return points
}

/**
 * Calm at hour 0 and hour 48, a mixed storm at hour 12, and no data for hour 30. Everywhere is
 * Moderate at hour 5 and No Travel at hour 6, to check colour follows risk rather than density.
 */
export const heatmap: HeatmapResponse = {
  departure_at: '2026-11-01T15:00:00Z',
  hours: FRAMES,
  points: heatPoints(),
  risk: heatPoints().map((_, index) =>
    frames((hour) => {
      if (hour === 30) return index % 2 === 0 ? null : 0
      if (hour === 12) return (index % 4) + 1
      if (hour === 5) return 1
      if (hour === 6) return 4
      return 0
    }),
  ),
}
