import { describe, expect, it } from 'vitest'

import type { HeatmapResponse } from '@/api/client'

import { RISK_DISPLAY } from '@/lib/risk'

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

  it('gives each risk level exactly its legend colour', () => {
    const expression = heatmapColor(0) as unknown[]
    const colors = Object.fromEntries(
      [1, 2, 3, 4].map((level) => [
        level,
        expression[expression.indexOf(level) + 1],
      ]),
    )
    expect(colors).toEqual({
      1: RISK_DISPLAY.moderate.color,
      2: RISK_DISPLAY.high.color,
      3: RISK_DISPLAY.severe.color,
      4: RISK_DISPLAY.no_travel.color,
    })
  })

  it('leaves Low and missing hours unshaded', () => {
    const expression = heatmapColor(0) as unknown[]
    expect(expression.at(-1)).toBe('rgba(0, 0, 0, 0)')
    expect(expression).not.toContain(0)
    expect(expression).not.toContain(-1)
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
