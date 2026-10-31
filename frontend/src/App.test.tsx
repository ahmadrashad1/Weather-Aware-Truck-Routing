import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { plan, secondRoute } from '@/test/fixtures/plan'
import { jsonResponse, renderWithQueries } from '@/test/render'

import App from './App'

// The map needs WebGL, so its own tests cover it. These cover how the app drives it.
vi.mock('@/features/map/MapPanel', () => ({
  default: (props: {
    selectedRouteId: string | null
    selectedCheckpointId: string | null
    onSelectRoute: (id: string) => void
    onSelectCheckpoint: (routeId: string, id: string | null) => void
  }) => (
    <div>
      <p>Map shows route {String(props.selectedRouteId)}</p>
      <p>Map shows checkpoint {String(props.selectedCheckpointId)}</p>
      <button type="button" onClick={() => props.onSelectRoute('route-1')}>
        Map selects route
      </button>
      <button
        type="button"
        onClick={() => props.onSelectCheckpoint('route-1', 'route-1-1')}
      >
        Map selects checkpoint
      </button>
    </div>
  ),
}))

const DALLAS = { label: 'Dallas, TX', lat: 32.77, lon: -96.79 }
const DENVER = { label: 'Denver, CO', lat: 39.73, lon: -104.99 }

function stubApi(planResponse: () => Response) {
  const fetchMock = vi.fn<
    (input: string, init?: RequestInit) => Promise<Response>
  >((input) => {
    if (input.includes('/geocode')) {
      const results = input.includes('Dal') ? [DALLAS] : [DENVER]
      return Promise.resolve(jsonResponse({ results }))
    }
    return Promise.resolve(planResponse())
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function submitTrip(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole('combobox', { name: 'Origin' }), 'Dal')
  await user.click(await screen.findByRole('option', { name: 'Dallas, TX' }))
  await user.type(screen.getByRole('combobox', { name: 'Destination' }), 'Den')
  await user.click(await screen.findByRole('option', { name: 'Denver, CO' }))
  await user.type(screen.getByLabelText('Load weight (lb)'), '45000')
  await user.click(screen.getByRole('button', { name: 'Plan routes' }))
}

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the heading', () => {
    renderWithQueries(<App />)
    expect(
      screen.getByRole('heading', { name: 'Weather-Aware Truck Routing' }),
    ).toBeInTheDocument()
  })

  it('invites the user to plan a trip before there are routes', () => {
    renderWithQueries(<App />)
    expect(screen.getByText(/Enter a trip/)).toBeInTheDocument()
  })

  it('shows ranked routes after planning and selects the recommended one', async () => {
    const user = userEvent.setup()
    stubApi(() => jsonResponse(plan))
    renderWithQueries(<App />)
    await submitTrip(user)

    const card = await screen.findByRole('button', { name: /Route 1/ })
    expect(card).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /Route 2/ })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('selects the first route when nothing is recommended', async () => {
    const user = userEvent.setup()
    stubApi(() =>
      jsonResponse({
        ...plan,
        recommended_route_id: null,
        no_safe_route: true,
      }),
    )
    renderWithQueries(<App />)
    await submitTrip(user)

    expect(
      await screen.findByRole('button', { name: /Route 1/ }),
    ).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('No safe route')
  })

  it('shows the selected route’s checkpoints', async () => {
    const user = userEvent.setup()
    stubApi(() => jsonResponse(plan))
    renderWithQueries(<App />)
    await submitTrip(user)

    await user.click(await screen.findByRole('button', { name: /Route 2/ }))
    const list = screen.getByRole('list', { name: 'Checkpoints' })
    expect(within(list).getAllByRole('button')).toHaveLength(
      secondRoute.checkpoints.length,
    )
  })

  it('keeps the map and the route list on the same route', async () => {
    const user = userEvent.setup()
    stubApi(() => jsonResponse(plan))
    renderWithQueries(<App />)
    await submitTrip(user)

    expect(
      await screen.findByText('Map shows route route-2'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Route 2/ }))
    expect(
      await screen.findByText('Map shows route route-1'),
    ).toBeInTheDocument()
  })

  it('selecting a checkpoint on the map selects its route and opens it in the list', async () => {
    const user = userEvent.setup()
    stubApi(() => jsonResponse(plan))
    renderWithQueries(<App />)
    await submitTrip(user)

    await user.click(
      await screen.findByRole('button', { name: 'Map selects checkpoint' }),
    )
    expect(screen.getByRole('button', { name: /Route 2/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    const list = screen.getByRole('list', { name: 'Checkpoints' })
    expect(within(list).getByText('38.2 mph')).toBeInTheDocument()
    expect(
      screen.getByText('Map shows checkpoint route-1-1'),
    ).toBeInTheDocument()
  })

  it('choosing another route closes the open checkpoint', async () => {
    const user = userEvent.setup()
    stubApi(() => jsonResponse(plan))
    renderWithQueries(<App />)
    await submitTrip(user)

    await user.click(
      await screen.findByRole('button', { name: 'Map selects checkpoint' }),
    )
    await user.click(screen.getByRole('button', { name: /Route 1/ }))
    expect(screen.getByText('Map shows checkpoint null')).toBeInTheDocument()
  })

  it('clicking an open checkpoint row closes it', async () => {
    const user = userEvent.setup()
    stubApi(() => jsonResponse(plan))
    renderWithQueries(<App />)
    await submitTrip(user)
    await user.click(await screen.findByRole('button', { name: /Route 2/ }))

    const list = screen.getByRole('list', { name: 'Checkpoints' })
    const row = within(list).getByRole('button', { name: /Mile 50/ })
    await user.click(row)
    expect(row).toHaveAttribute('aria-expanded', 'true')
    await user.click(row)
    expect(row).toHaveAttribute('aria-expanded', 'false')
  })

  it('keeps the form usable after an outage and can retry', async () => {
    const user = userEvent.setup()
    let attempts = 0
    const fetchMock = stubApi(() => {
      attempts += 1
      return attempts === 1
        ? jsonResponse({ code: 'provider_unavailable', message: 'Down.' }, 503)
        : jsonResponse(plan)
    })
    renderWithQueries(<App />)
    await submitTrip(user)

    await user.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(
      await screen.findByRole('button', { name: /Route 1/ }),
    ).toBeInTheDocument()
    const planCalls = fetchMock.mock.calls.filter(([url]) =>
      url.includes('/trips/plan'),
    )
    expect(planCalls).toHaveLength(2)
    expect(planCalls[1][1]).toEqual(planCalls[0][1])
  })

  it('clears old routes when a new plan fails', async () => {
    const user = userEvent.setup()
    let attempts = 0
    stubApi(() => {
      attempts += 1
      return attempts === 1
        ? jsonResponse(plan)
        : jsonResponse({ code: 'no_route', message: 'No road.' }, 422)
    })
    renderWithQueries(<App />)
    await submitTrip(user)
    await screen.findByRole('button', { name: /Route 1/ })

    await user.click(screen.getByRole('button', { name: 'Plan routes' }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('No road.'),
    )
    expect(
      screen.queryByRole('button', { name: /Route 1/ }),
    ).not.toBeInTheDocument()
  })
})
