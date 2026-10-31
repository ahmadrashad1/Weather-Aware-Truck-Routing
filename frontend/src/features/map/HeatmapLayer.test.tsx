import { act, render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { HeatmapResponse } from '@/api/client'
import { forecastStore } from '@/features/forecast/forecastStore'

import { heatmapColor } from './heatmapExpression'
import { HeatmapLayer } from './HeatmapLayer'

const fake = vi.hoisted(() => ({
  sources: {} as Record<string, unknown>,
  layers: {} as Record<string, Record<string, unknown>>,
  setPaintProperty: vi.fn(),
  setData: vi.fn(),
  hasLayer: true,
}))

vi.mock('react-map-gl/maplibre', () => ({
  useMap: () => ({
    current: {
      getMap: () => ({
        getLayer: () => (fake.hasLayer ? {} : undefined),
        setPaintProperty: fake.setPaintProperty,
        getSource: () => ({ setData: fake.setData }),
      }),
    },
  }),
  Source: ({
    id,
    data,
    children,
  }: {
    id: string
    data: unknown
    children: ReactNode
  }) => {
    fake.sources[id] = data
    return <>{children}</>
  },
  Layer: (props: Record<string, unknown>) => {
    fake.layers[String(props.id)] = props
    return null
  },
}))

const data: HeatmapResponse = {
  departure_at: '2026-11-01T15:00:00Z',
  hours: 49,
  points: [[-97, 33]],
  risk: [Array.from({ length: 49 }, () => 1)],
}

let frames: FrameRequestCallback[] = []

function runFrame() {
  act(() => {
    const pending = frames
    frames = []
    pending.forEach((callback) => callback(0))
  })
}

describe('HeatmapLayer', () => {
  beforeEach(() => {
    forecastStore.set(0)
    frames = []
    fake.sources = {}
    fake.layers = {}
    fake.hasLayer = true
    fake.setPaintProperty.mockClear()
    fake.setData.mockClear()
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      frames.push(callback)
      return frames.length
    })
    vi.stubGlobal('cancelAnimationFrame', () => {
      frames = []
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('moving the slider changes the paint colour and never the data', () => {
    render(<HeatmapLayer data={data} />)
    const source = fake.sources['corridor']

    act(() => forecastStore.set(12))
    runFrame()

    expect(fake.setPaintProperty).toHaveBeenCalledTimes(1)
    expect(fake.setPaintProperty).toHaveBeenCalledWith(
      'corridor-heat',
      'circle-color',
      heatmapColor(12),
    )
    expect(fake.setData).not.toHaveBeenCalled()
    expect(fake.sources['corridor']).toBe(source)
  })

  it('updates at most once per frame, using the latest hour', () => {
    render(<HeatmapLayer data={data} />)
    act(() => {
      forecastStore.set(1)
      forecastStore.set(2)
      forecastStore.set(3)
    })
    runFrame()
    expect(fake.setPaintProperty).toHaveBeenCalledTimes(1)
    expect(fake.setPaintProperty.mock.calls[0][2]).toEqual(heatmapColor(3))
  })

  it('does not re-render itself when the hour changes', () => {
    const { rerender } = render(<HeatmapLayer data={data} />)
    const paintBefore = fake.layers['corridor-heat'].paint
    act(() => forecastStore.set(20))
    runFrame()
    rerender(<HeatmapLayer data={data} />)
    // The declared paint stays as it was, so React can't undo the direct update.
    expect(fake.layers['corridor-heat'].paint).toBe(paintBefore)
  })

  it('starts from the current hour', () => {
    forecastStore.set(7)
    render(<HeatmapLayer data={data} />)
    const paint = fake.layers['corridor-heat'].paint as Record<string, unknown>
    expect(paint['circle-color']).toEqual(heatmapColor(7))
  })

  it('draws under the route lines', () => {
    render(<HeatmapLayer data={data} />)
    expect(fake.layers['corridor-heat'].beforeId).toBe('route-casing')
  })

  it('waits if the layer is not on the map yet', () => {
    fake.hasLayer = false
    render(<HeatmapLayer data={data} />)
    act(() => forecastStore.set(5))
    runFrame()
    expect(fake.setPaintProperty).not.toHaveBeenCalled()
  })

  it('stops following the slider once removed', () => {
    const { unmount } = render(<HeatmapLayer data={data} />)
    unmount()
    act(() => forecastStore.set(5))
    runFrame()
    expect(fake.setPaintProperty).not.toHaveBeenCalled()
  })
})
