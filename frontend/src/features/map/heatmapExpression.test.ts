import { describe, expect, it } from 'vitest'

import type { HeatmapResponse } from '@/api/client'

import { heatmapColor, heatmapToGeoJson } from './heatmapExpression'

const data: HeatmapResponse = {
  departure_at: '2026-11-01T15:00:00Z',
  hours: 3,
  points: [
    [-97, 33],
    [-98, 34],
  ],
  risk: [
    [0, 2, 4],
    [1, null, 3],
  ],
}

describe('heatmapColor', () => {
  it('reads the selected hour', () => {
    const expression = heatmapColor(12) as unknown[]
    expect(expression.slice(0, 2)).toEqual([
      'match',
      ['coalesce', ['get', 'h12'], -1],
    ])
  })

  it('gives every risk level its legend colour, faintly for Low', () => {
    const expression = heatmapColor(0) as unknown[]
    const colors = Object.fromEntries(
      [0, 1, 2, 3, 4].map((level) => [
        level,
        expression[expression.indexOf(level) + 1],
      ]),
    )
    expect(colors).toEqual({
      0: 'rgba(47, 143, 91, 0.25)',
      1: 'rgba(227, 181, 5, 0.6)',
      2: 'rgba(232, 119, 12, 0.6)',
      3: 'rgba(196, 18, 47, 0.6)',
      4: 'rgba(74, 13, 26, 0.6)',
    })
  })

  it('shows a missing hour in the legend grey, so it can’t pass for safe', () => {
    const expression = heatmapColor(0) as unknown[]
    expect(expression.at(-1)).toBe('rgba(154, 163, 168, 0.45)')
  })
})

describe('heatmapToGeoJson', () => {
  it('makes one point per location, with a value for each hour', () => {
    const { features } = heatmapToGeoJson(data)
    expect(features).toHaveLength(2)
    expect(features[0].geometry).toEqual({
      type: 'Point',
      coordinates: [-97, 33],
    })
    expect(features[0].properties).toEqual({ h0: 0, h1: 2, h2: 4 })
  })

  it('leaves a missing hour empty rather than calling it Low', () => {
    const { features } = heatmapToGeoJson(data)
    expect(features[1].properties).toEqual({ h0: 1, h1: null, h2: 3 })
  })
})
