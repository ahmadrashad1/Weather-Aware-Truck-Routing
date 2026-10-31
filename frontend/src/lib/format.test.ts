import { describe, expect, it } from 'vitest'

import {
  formatDuration,
  formatEta,
  formatMileMarker,
  formatMiles,
  localInputToOffsetIso,
  nextHourLocalInput,
} from './format'

describe('formatDuration', () => {
  it.each([
    [59 * 60, '59 min'],
    [3600, '1 h 0 min'],
    [47280, '13 h 8 min'],
    [171720, '47 h 42 min'],
  ])('formats %i seconds', (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected)
  })
})

describe('formatMiles', () => {
  it.each([
    [0, '0 mi'],
    [12.5, '12.5 mi'],
    [797.55, '797.6 mi'],
    [3032.49, '3,032.5 mi'],
  ])('formats %f', (miles, expected) => {
    expect(formatMiles(miles)).toBe(expected)
  })
})

describe('formatMileMarker', () => {
  it.each([
    [0, 'Mile 0'],
    [50, 'Mile 50'],
    [1250.25, 'Mile 1,250.3'],
  ])('formats %f', (mile, expected) => {
    expect(formatMileMarker(mile)).toBe(expected)
  })
})

describe('formatEta', () => {
  it('shows the instant in the given time zone with its abbreviation', () => {
    const text = formatEta('2026-11-01T15:00:00Z', 'America/Chicago')
    expect(text).toContain('9:00')
    expect(text).toContain('Nov 1')
    expect(text).toContain('CST')
  })

  it('crosses midnight into the next local day', () => {
    expect(formatEta('2026-11-02T03:00:00Z', 'America/Chicago')).toContain(
      'Nov 1',
    )
    expect(formatEta('2026-11-02T06:30:00Z', 'America/Chicago')).toContain(
      'Nov 2',
    )
  })
})

describe('localInputToOffsetIso', () => {
  it('adds the browser offset to a local date and time', () => {
    const iso = localInputToOffsetIso('2026-11-01T12:30')
    expect(iso).toMatch(/^2026-11-01T12:30:00[+-]\d{2}:\d{2}$/)
    expect(new Date(iso).getTime()).toBe(
      new Date(2026, 10, 1, 12, 30).getTime(),
    )
  })
})

describe('nextHourLocalInput', () => {
  it('rounds up to the next whole hour in local time', () => {
    expect(nextHourLocalInput(new Date(2026, 10, 1, 9, 12))).toBe(
      '2026-11-01T10:00',
    )
  })

  it('rolls over midnight', () => {
    expect(nextHourLocalInput(new Date(2026, 11, 31, 23, 45))).toBe(
      '2027-01-01T00:00',
    )
  })
})
