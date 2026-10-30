import type { Checkpoint, PlanResponse, Route } from '@/api/client'

export const lowCheckpoint: Checkpoint = {
  id: 'route-1-0',
  mile: 0,
  lat: 32.77667,
  lon: -96.79699,
  eta: '2026-11-01T15:00:00Z',
  represented_miles: 25,
  weather: { wind_mph: 10.6, rain_in_hr: 0, snow_in_hr: 0 },
  risk: 'low',
  wind_risk: 'low',
  rain_risk: 'low',
  snow_risk: 'low',
  load_adjusted: false,
  drivers: [],
}

export const severeCheckpoint: Checkpoint = {
  id: 'route-1-1',
  mile: 50,
  lat: 33.2,
  lon: -97.2,
  eta: '2026-11-01T16:00:00Z',
  represented_miles: 50,
  weather: { wind_mph: 38.2, rain_in_hr: 0.12, snow_in_hr: 0 },
  risk: 'severe',
  wind_risk: 'severe',
  rain_risk: 'moderate',
  snow_risk: 'low',
  load_adjusted: true,
  drivers: ['wind'],
}

export const unknownCheckpoint: Checkpoint = {
  id: 'route-1-2',
  mile: 100,
  lat: 33.9,
  lon: -98.1,
  eta: '2026-11-01T17:00:00Z',
  represented_miles: 25,
  weather: null,
  risk: 'unknown',
  wind_risk: null,
  rain_risk: null,
  snow_risk: null,
  load_adjusted: false,
  drivers: [],
}

const summary = {
  distance_miles: 100,
  duration_seconds: 7500,
  arrival_at: '2026-11-01T17:05:00Z',
  severe_miles: 0,
  high_miles: 0,
  moderate_miles: 0,
  low_miles: 100,
  no_travel_miles: 0,
  unknown_miles: 0,
  average_risk: 0,
}

export const firstRoute: Route = {
  id: 'route-2',
  rank: 1,
  rationale: 'Recommended for fewest Severe miles (0.0 vs 50.0).',
  summary,
  geometry: {
    type: 'LineString',
    coordinates: [
      [-96.797, 32.777],
      [-104.99, 39.739],
    ],
  },
  segments: [
    {
      risk: 'low',
      from_mile: 0,
      to_mile: 100,
      coordinates: [
        [-96.797, 32.777],
        [-104.99, 39.739],
      ],
    },
  ],
  checkpoints: [lowCheckpoint],
}

export const secondRoute: Route = {
  id: 'route-1',
  rank: 2,
  rationale: 'Ranks lower for more Severe miles (50.0 vs 0.0).',
  summary: {
    ...summary,
    distance_miles: 125,
    duration_seconds: 5400,
    severe_miles: 50,
    high_miles: 12.5,
    low_miles: 37.5,
    unknown_miles: 25,
    average_risk: 1.5,
  },
  geometry: {
    type: 'LineString',
    coordinates: [
      [-96.8, 32.8],
      [-98.1, 33.9],
    ],
  },
  segments: [
    { risk: 'low', from_mile: 0, to_mile: 25, coordinates: [] },
    { risk: 'severe', from_mile: 25, to_mile: 100, coordinates: [] },
    { risk: 'unknown', from_mile: 100, to_mile: 125, coordinates: [] },
  ],
  checkpoints: [lowCheckpoint, severeCheckpoint, unknownCheckpoint],
}

export const plan: PlanResponse = {
  recommended_route_id: 'route-2',
  no_safe_route: false,
  warnings: [],
  routes: [firstRoute, secondRoute],
}
