import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse } from '@/test/render'

import { ApiError, fetchHeatmap, geocode, planTrip } from './client'

const request = {
  origin: { label: 'Dallas, TX', lat: 32.77, lon: -96.79 },
  destination: { label: 'Denver, CO', lat: 39.73, lon: -104.99 },
  departure_at: '2026-11-01T12:00:00-05:00',
  load_lb: 45000,
  interval_miles: 25 as const,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API client', () => {
  it('posts a plan request as JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        recommended_route_id: null,
        no_safe_route: false,
        warnings: [],
        routes: [],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await planTrip(request)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/trips/plan')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(request)
  })

  it('encodes the geocode query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ results: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await geocode('Fort Worth, TX')
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/geocode?q=Fort%20Worth%2C%20TX',
    )
  })

  it('posts the route lines for a heatmap', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ departure_at: '', hours: 49, points: [], risk: [] }),
      )
    vi.stubGlobal('fetch', fetchMock)
    const body = { routes: [[[-96, 32]]], departure_at: 'x', load_lb: 1 }
    await fetchHeatmap(body)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/trips/heatmap')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(body)
  })

  it('turns an API error into ApiError with its fields', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            code: 'validation_error',
            message: 'Please check the highlighted fields.',
            fields: { load_lb: ['Too heavy.'] },
          },
          400,
        ),
      ),
    )
    const error = await planTrip(request).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      code: 'validation_error',
      status: 400,
      fields: { load_lb: ['Too heavy.'] },
    })
  })

  it('reports an unreachable server as a network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')))
    await expect(planTrip(request)).rejects.toMatchObject({
      code: 'network_error',
    })
  })

  it('reports a non-JSON error response as a server error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>', { status: 502 })),
    )
    await expect(planTrip(request)).rejects.toMatchObject({
      code: 'server_error',
      status: 502,
    })
  })

  it('lets a caller cancel, without reporting a network error', async () => {
    const abort = new DOMException('Aborted', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort))
    await expect(geocode('Dal')).rejects.toBe(abort)
  })
})
