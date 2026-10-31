import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode, Ref } from 'react'
import { Profiler, useImperativeHandle } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  plan,
  secondRoute,
  severeCheckpoint,
  unknownCheckpoint,
} from '@/test/fixtures/plan'

import { forecastStore } from '@/features/forecast/forecastStore'

import MapPanel from './MapPanel'

const HEATMAP = {
  departure_at: '2026-11-01T15:00:00Z',
  hours: 49,
  points: [[-97, 33]],
  risk: [Array.from({ length: 49 }, () => 1)],
}

// jsdom has no WebGL, so only the map library's React components are replaced. The app's own
// layers, data and event handling all run for real. A real browser check covers the rest.
const fake = vi.hoisted(() => ({
  mapProps: {} as Record<string, (...args: never[]) => unknown>,
  sources: {} as Record<string, unknown>,
  layers: {} as Record<string, Record<string, unknown>>,
  fitBounds: vi.fn(),
  easeTo: vi.fn(),
  contains: vi.fn(() => true),
  setWorkerUrl: vi.fn(),
}))

vi.mock('maplibre-gl', () => ({ setWorkerUrl: fake.setWorkerUrl }))

vi.mock('react-map-gl/maplibre', () => ({
  Map: ({
    ref,
    children,
    ...props
  }: {
    ref?: Ref<unknown>
    children: ReactNode
    [key: string]: unknown
  }) => {
    fake.mapProps = props as typeof fake.mapProps
    useImperativeHandle(ref, () => ({
      fitBounds: fake.fitBounds,
      easeTo: fake.easeTo,
      getBounds: () => ({ contains: fake.contains }),
      getContainer: () => ({ clientHeight: 300 }),
    }))
    return <div data-testid="map">{children}</div>
  },
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
  Marker: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Popup: ({
    children,
    onClose,
    longitude,
    latitude,
  }: {
    children: ReactNode
    onClose: () => void
    longitude: number
    latitude: number
  }) => (
    <div data-testid="popup" data-position={`${longitude},${latitude}`}>
      {children}
      <button type="button" onClick={onClose}>
        Close popup
      </button>
    </div>
  ),
  NavigationControl: () => null,
  useMap: () => ({ current: undefined }),
}))

function setup(overrides: Partial<Parameters<typeof MapPanel>[0]> = {}) {
  const props = {
    plan,
    selectedRouteId: 'route-1',
    selectedCheckpointId: null,
    onSelectRoute: vi.fn(),
    onSelectCheckpoint: vi.fn(),
    ...overrides,
  }
  const view = render(<MapPanel {...props} />)
  return { props, ...view }
}

function clickFeatures(features: unknown[]) {
  act(() => {
    ;(fake.mapProps.onClick as unknown as (event: unknown) => void)({
      features,
    })
  })
}

function loadMap() {
  act(() => {
    ;(fake.mapProps.onLoad as unknown as () => void)()
  })
}

describe('map worker', () => {
  it('tells MapLibre where the bundler put its worker', async () => {
    // MapLibre otherwise looks beside its own script, and the map silently never draws.
    fake.setWorkerUrl.mockClear()
    vi.resetModules()
    await import('./MapPanel')
    expect(fake.setWorkerUrl.mock.calls).toEqual([
      [expect.stringContaining('maplibre-gl-worker')],
    ])
  })
})

describe('MapPanel', () => {
  beforeEach(() => {
    fake.sources = {}
    fake.layers = {}
    fake.fitBounds.mockClear()
    fake.easeTo.mockClear()
    fake.contains.mockReturnValue(true)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('selecting a route changes only paint values, leaving route data untouched', () => {
    const { rerender, props } = setup({ selectedRouteId: 'route-1' })
    const routes = fake.sources['routes']
    const checkpoints = fake.sources['checkpoints']
    const paintBefore = fake.layers['route-lines'].paint

    rerender(<MapPanel {...props} selectedRouteId="route-2" />)

    // react-map-gl calls setData only when this object's identity changes.
    expect(fake.sources['routes']).toBe(routes)
    expect(fake.sources['checkpoints']).toBe(checkpoints)
    expect(fake.layers['route-lines'].paint).not.toEqual(paintBefore)
  })

  it('makes the selected route stand out in width and opacity', () => {
    setup({ selectedRouteId: 'route-1' })
    const paint = fake.layers['route-lines'].paint as Record<string, unknown>
    const selected = ['==', ['get', 'route_id'], 'route-1']
    expect(paint['line-width']).toEqual(['case', selected, 6, 3])
    expect(paint['line-opacity']).toEqual(['case', selected, 1, 0.45])
  })

  it('colours lines and checkpoints by the risk the API sent', () => {
    setup()
    const line = fake.layers['route-lines'].paint as Record<string, unknown>
    const point = fake.layers['checkpoints'].paint as Record<string, unknown>
    for (const color of [line['line-color'], point['circle-color']]) {
      const expression = color as unknown[]
      expect(expression[0]).toBe('match')
      expect(expression).toContain('severe')
      expect(expression).toContain('#c4122f')
    }
  })

  it('fits the map to all routes once loaded', () => {
    setup()
    expect(fake.fitBounds).not.toHaveBeenCalled()
    loadMap()
    expect(fake.fitBounds).toHaveBeenCalledTimes(1)
    expect(fake.fitBounds.mock.calls[0][0]).toEqual([
      -104.99, 32.777, -96.797, 39.739,
    ])
  })

  it('fits again for a new plan, but not when the selection changes', () => {
    const { rerender, props } = setup()
    loadMap()
    rerender(<MapPanel {...props} selectedRouteId="route-2" />)
    expect(fake.fitBounds).toHaveBeenCalledTimes(1)
    rerender(<MapPanel {...props} plan={{ ...plan }} />)
    expect(fake.fitBounds).toHaveBeenCalledTimes(2)
  })

  it('jumps instead of animating when reduced motion is requested', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({ matches: query.includes('reduced-motion') })),
    )
    setup()
    loadMap()
    expect(fake.fitBounds.mock.calls[0][1]).toMatchObject({ duration: 0 })
  })

  it('leaves room for the forecast panel when it floats over a wide map', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({ matches: query.includes('min-width') })),
    )
    setup()
    loadMap()
    const padding = fake.fitBounds.mock.calls[0][1].padding
    expect(padding.bottom).toBeGreaterThan(padding.top)
  })

  it('uses even padding on a phone, where the panel sits below the map', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: false })),
    )
    setup()
    loadMap()
    expect(fake.fitBounds.mock.calls[0][1].padding).toBe(60)
  })

  it('moving the forecast hour does not re-render the map panel', () => {
    const onRender = vi.fn()
    render(
      <Profiler id="map" onRender={onRender}>
        <MapPanel
          plan={plan}
          heatmap={HEATMAP}
          selectedRouteId="route-1"
          selectedCheckpointId={null}
          onSelectRoute={vi.fn()}
          onSelectCheckpoint={vi.fn()}
        />
      </Profiler>,
    )
    const commits = onRender.mock.calls.length
    act(() => {
      for (let hour = 0; hour <= 48; hour += 1) forecastStore.set(hour)
    })
    expect(onRender.mock.calls.length).toBe(commits)
    forecastStore.set(0)
  })

  it('adds the corridor heatmap only once its data arrives', () => {
    const { rerender, props } = setup()
    expect(fake.sources['corridor']).toBeUndefined()
    rerender(<MapPanel {...props} heatmap={HEATMAP} />)
    expect(fake.sources['corridor']).toBeDefined()
  })

  it('shows no route layers before a plan exists', () => {
    setup({ plan: undefined, selectedRouteId: null })
    expect(fake.sources).toEqual({})
    expect(screen.queryByTestId('popup')).not.toBeInTheDocument()
  })

  it('shrinks checkpoints when zoomed out, so they cannot hide the risk colours', () => {
    setup({ selectedRouteId: 'route-1' })
    const paint = fake.layers['checkpoints'].paint as Record<string, unknown[]>
    const radius = paint['circle-radius']
    expect(radius.slice(0, 3)).toEqual(['interpolate', ['linear'], ['zoom']])
    const selected = ['==', ['get', 'route_id'], 'route-1']
    expect(radius[4]).toEqual(['case', selected, 2, 1])
    expect(radius[6]).toEqual(['case', selected, 6, 3])
  })

  it('collapses the attribution so it fits a small map', () => {
    setup()
    expect(fake.mapProps.attributionControl).toEqual({ compact: true })
  })

  it('makes checkpoints and route lines clickable', () => {
    setup()
    expect(fake.mapProps.interactiveLayerIds).toEqual([
      'checkpoints',
      'route-hit-area',
    ])
  })

  it('clicking a checkpoint selects it and its route', () => {
    const { props } = setup()
    clickFeatures([
      {
        layer: { id: 'checkpoints' },
        properties: { id: severeCheckpoint.id, route_id: 'route-1' },
      },
    ])
    expect(props.onSelectCheckpoint).toHaveBeenCalledWith(
      'route-1',
      severeCheckpoint.id,
    )
  })

  it('clicking a route line selects that route', () => {
    const { props } = setup()
    clickFeatures([
      { layer: { id: 'route-hit-area' }, properties: { route_id: 'route-2' } },
    ])
    expect(props.onSelectRoute).toHaveBeenCalledWith('route-2')
    expect(props.onSelectCheckpoint).not.toHaveBeenCalled()
  })

  it('prefers the checkpoint when a click lands on both', () => {
    const { props } = setup()
    clickFeatures([
      {
        layer: { id: 'checkpoints' },
        properties: { id: severeCheckpoint.id, route_id: 'route-1' },
      },
      { layer: { id: 'route-hit-area' }, properties: { route_id: 'route-1' } },
    ])
    expect(props.onSelectRoute).not.toHaveBeenCalled()
    expect(props.onSelectCheckpoint).toHaveBeenCalled()
  })

  it('ignores a click on empty map', () => {
    const { props } = setup()
    clickFeatures([])
    expect(props.onSelectRoute).not.toHaveBeenCalled()
    expect(props.onSelectCheckpoint).not.toHaveBeenCalled()
  })

  it('shows the selected checkpoint’s mile, ETA, readings and risk in a popup', () => {
    setup({ selectedCheckpointId: severeCheckpoint.id })
    const popup = within(screen.getByTestId('popup'))
    expect(popup.getByText(/Mile 50/)).toBeInTheDocument()
    expect(popup.getByText(/Arrives/)).toBeInTheDocument()
    expect(popup.getByText('38.2 mph')).toBeInTheDocument()
    expect(popup.getByText('0.12 in/hr')).toBeInTheDocument()
    expect(popup.getAllByText('Severe').length).toBeGreaterThan(0)
    expect(popup.getByText(/raised because of the load/)).toBeInTheDocument()
    expect(screen.getByTestId('popup')).toHaveAttribute(
      'data-position',
      `${severeCheckpoint.lon},${severeCheckpoint.lat}`,
    )
  })

  it('says weather is unavailable rather than showing zeros', () => {
    setup({ selectedCheckpointId: unknownCheckpoint.id })
    const popup = within(screen.getByTestId('popup'))
    expect(popup.getByText(/Weather is unavailable/)).toBeInTheDocument()
    expect(popup.queryByText(/mph/)).not.toBeInTheDocument()
  })

  it('closes the popup by clearing the selection', async () => {
    const user = userEvent.setup()
    const { props } = setup({ selectedCheckpointId: severeCheckpoint.id })
    await user.click(screen.getByRole('button', { name: 'Close popup' }))
    expect(props.onSelectCheckpoint).toHaveBeenCalledWith('route-1', null)
  })

  it('pans to a selected checkpoint that is out of view', () => {
    fake.contains.mockReturnValue(false)
    const { rerender, props } = setup()
    loadMap()
    rerender(<MapPanel {...props} selectedCheckpointId={severeCheckpoint.id} />)
    expect(fake.easeTo).toHaveBeenCalledTimes(1)
    expect(fake.easeTo.mock.calls[0][0]).toMatchObject({
      center: [severeCheckpoint.lon, severeCheckpoint.lat],
    })
  })

  it('leaves the map alone when the selected checkpoint is in view', () => {
    const { rerender, props } = setup()
    loadMap()
    rerender(<MapPanel {...props} selectedCheckpointId={severeCheckpoint.id} />)
    expect(fake.easeTo).not.toHaveBeenCalled()
  })

  it('on a phone, moves a selected checkpoint low so its whole popup fits', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: false })),
    )
    const { rerender, props } = setup()
    loadMap()
    rerender(<MapPanel {...props} selectedCheckpointId={severeCheckpoint.id} />)
    expect(fake.easeTo).toHaveBeenCalledTimes(1)
    expect(fake.easeTo.mock.calls[0][0]).toMatchObject({
      center: [severeCheckpoint.lon, severeCheckpoint.lat],
      offset: [0, 105],
    })
  })

  it('labels each route and selects it from the label', async () => {
    const user = userEvent.setup()
    const { props } = setup()
    await user.click(
      screen.getByRole('button', { name: `Select route ${secondRoute.rank}` }),
    )
    expect(props.onSelectRoute).toHaveBeenCalledWith(secondRoute.id)
  })

  it('has a legend naming every risk level', () => {
    setup()
    const legend = within(screen.getByRole('list', { name: 'Risk levels' }))
    for (const label of [
      'Low',
      'Moderate',
      'High',
      'Severe',
      'No Travel',
      'No weather',
    ]) {
      expect(legend.getByText(label)).toBeInTheDocument()
    }
  })

  it('says when the base map fails, while routes stay usable', () => {
    setup()
    act(() => {
      ;(fake.mapProps.onError as unknown as () => void)()
    })
    expect(screen.getByRole('status')).toHaveTextContent(
      'background map could not load',
    )
    expect(fake.sources['routes']).toBeDefined()
  })
})
