import { afterEach, describe, expect, it, vi } from 'vitest'

import { sendVital } from './vitals'

describe('sendVital', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends only the name, value and rating', async () => {
    const sendBeacon = vi.fn<(url: string, body: Blob) => boolean>(() => true)
    vi.stubGlobal('navigator', { sendBeacon })

    // The library's metrics also carry page details, which must stay out of the request.
    const metric = {
      name: 'LCP' as const,
      value: 3152.5,
      rating: 'needs-improvement' as const,
      id: 'private-id',
    }
    sendVital(metric)

    const [url, body] = sendBeacon.mock.calls[0]
    expect(url).toBe('/api/v1/vitals')
    expect(body.type).toBe('application/json')
    expect(JSON.parse(await body.text())).toEqual({
      name: 'LCP',
      value: 3152.5,
      rating: 'needs-improvement',
    })
  })

  it('does nothing in a browser without sendBeacon', () => {
    vi.stubGlobal('navigator', {})
    expect(() =>
      sendVital({ name: 'CLS', value: 0.1, rating: 'good' }),
    ).not.toThrow()
  })
})
