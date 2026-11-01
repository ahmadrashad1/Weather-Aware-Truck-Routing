import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { plan } from '@/test/fixtures/plan'
import { jsonResponse } from '@/test/render'

import type { PlanRequest, PlanResponse } from './client'
import { useGeocode, useHeatmap } from './queries'

const request: PlanRequest = {
  origin: { label: 'Dallas, TX', lat: 32.77, lon: -96.79 },
  destination: { label: 'Denver, CO', lat: 39.73, lon: -104.99 },
  departure_at: '2026-11-01T12:00:00-05:00',
  load_lb: 45000,
  interval_miles: 25,
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function stubHeatmap() {
  const fetchMock = vi.fn(() =>
    Promise.resolve(
      jsonResponse({ departure_at: '', hours: 49, points: [], risk: [] }),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('useHeatmap', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('waits for a plan', () => {
    const fetchMock = stubHeatmap()
    renderHook(() => useHeatmap(undefined, undefined), { wrapper })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sends each route line with the departure and load', async () => {
    const fetchMock = stubHeatmap()
    const { result } = renderHook(() => useHeatmap(plan, request), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(JSON.parse(String(init.body))).toEqual({
      routes: plan.routes.map((route) => route.geometry.coordinates),
      departure_at: request.departure_at,
      load_lb: request.load_lb,
    })
  })

  it('fetches once per plan, and again for a new plan with the same ids', async () => {
    const fetchMock = stubHeatmap()
    const newPlan: PlanResponse = { ...plan }
    const { result, rerender } = renderHook(
      ({ current }) => useHeatmap(current, request),
      { wrapper, initialProps: { current: plan } },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    rerender({ current: plan })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    rerender({ current: newPlan })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})

describe('useGeocode', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // TomTom's terms allow client caching only when its responses carry cache headers, and search
  // responses have none.
  it('searches again when the same text comes back', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ results: [] })),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { result, rerender } = renderHook(({ text }) => useGeocode(text), {
      wrapper,
      initialProps: { text: 'Dallas' },
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    rerender({ text: 'Denver' })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await act(async () => {
      await new Promise((done) => setTimeout(done, 0))
    })
    rerender({ text: 'Dallas' })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
  })

  it('keeps no results once the search is done with', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ results: [] }))),
    )
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const { result, unmount } = renderHook(() => useGeocode('Dallas'), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    unmount()
    await waitFor(() => expect(client.getQueryCache().getAll()).toEqual([]))
  })
})
