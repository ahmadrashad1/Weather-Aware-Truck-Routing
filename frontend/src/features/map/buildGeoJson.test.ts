import { describe, expect, it } from 'vitest'

import {
  firstRoute,
  lowCheckpoint,
  plan,
  secondRoute,
  severeCheckpoint,
} from '@/test/fixtures/plan'

import {
  checkpointsToPoints,
  planBounds,
  routeLabelPositions,
  routesToSegments,
} from './buildGeoJson'

describe('routesToSegments', () => {
  it('emits one line per API segment, carrying its route and risk', () => {
    const { features } = routesToSegments(plan)
    expect(features).toHaveLength(
      firstRoute.segments.length + secondRoute.segments.length,
    )
    expect(features[0].properties).toEqual({
      route_id: 'route-2',
      risk: 'low',
    })
    expect(features[2].properties).toEqual({
      route_id: 'route-1',
      risk: 'severe',
    })
    expect(features[0].geometry).toEqual({
      type: 'LineString',
      coordinates: firstRoute.segments[0].coordinates,
    })
  })
})

describe('checkpointsToPoints', () => {
  it('emits one point per checkpoint on every route', () => {
    const { features } = checkpointsToPoints(plan)
    expect(features).toHaveLength(
      firstRoute.checkpoints.length + secondRoute.checkpoints.length,
    )
  })

  it('places the point at longitude then latitude, with its identity', () => {
    const { features } = checkpointsToPoints(plan)
    expect(features[2].geometry).toEqual({
      type: 'Point',
      coordinates: [severeCheckpoint.lon, severeCheckpoint.lat],
    })
    expect(features[2].properties).toEqual({
      id: severeCheckpoint.id,
      route_id: 'route-1',
      risk: 'severe',
    })
  })

  it('keeps the same checkpoint id apart on different routes', () => {
    const { features } = checkpointsToPoints(plan)
    expect(features[0].properties.id).toBe(lowCheckpoint.id)
    expect(features[0].properties.route_id).toBe('route-2')
  })
})

describe('planBounds', () => {
  it('encloses every route as [west, south, east, north]', () => {
    expect(planBounds(plan)).toEqual([-104.99, 32.777, -96.797, 39.739])
  })

  it('finds no bounds for a plan with no routes', () => {
    expect(planBounds({ ...plan, routes: [] })).toBeNull()
  })
})

describe('routeLabelPositions', () => {
  it('gives each route one label position on its own line', () => {
    const route = {
      ...firstRoute,
      geometry: {
        type: 'LineString' as const,
        coordinates: [
          [0, 0],
          [1, 1],
          [2, 2],
          [3, 3],
          [4, 4],
        ],
      },
    }
    const [label] = routeLabelPositions({ ...plan, routes: [route] })
    expect(label.route).toBe(route)
    expect(route.geometry.coordinates).toContainEqual([label.lon, label.lat])
  })

  it('spreads labels along shared lines so they do not stack', () => {
    const coordinates = Array.from({ length: 100 }, (_, i) => [i, i])
    const shared = { type: 'LineString' as const, coordinates }
    const routes = [
      { ...firstRoute, geometry: shared, rank: 1 },
      { ...secondRoute, geometry: shared, rank: 2 },
    ]
    const [first, second] = routeLabelPositions({ ...plan, routes })
    expect(first.lon).not.toBe(second.lon)
  })
})
