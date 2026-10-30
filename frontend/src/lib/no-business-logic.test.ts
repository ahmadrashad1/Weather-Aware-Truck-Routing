import { describe, expect, it } from 'vitest'

const WEATHER_WORD = String.raw`\b\w*(?:wind|rain|snow)\w*(?:\.\w+)*`
const COMPARISON = String.raw`\s*(?:<=?|>=?)\s*`
const NUMBER = String.raw`\d`
const THRESHOLD_PATTERNS = [
  new RegExp(WEATHER_WORD + COMPARISON + NUMBER, 'i'),
  new RegExp(NUMBER + COMPARISON + WEATHER_WORD, 'i'),
]

const sources = import.meta.glob<string>(
  [
    '../**/*.{ts,tsx}',
    '!../**/*.test.{ts,tsx}',
    '!../**/*.d.ts',
    '!../test/**',
  ],
  { query: '?raw', import: 'default', eager: true },
)

describe('risk rules stay in the backend', () => {
  it('finds source files to check', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(5)
  })

  it('recognises a threshold when it sees one', () => {
    const samples = ['wind_mph >= 55', 'weather.rain_in_hr < 0.1', '3 > snow']
    for (const sample of samples) {
      expect(THRESHOLD_PATTERNS.some((p) => p.test(sample))).toBe(true)
    }
  })

  it('has no numeric comparison with wind, rain or snow in the frontend', () => {
    const offenders = Object.entries(sources)
      .filter(([, source]) => THRESHOLD_PATTERNS.some((p) => p.test(source)))
      .map(([file]) => file)
    expect(offenders).toEqual([])
  })
})
