import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import {
  firstRoute,
  plan,
  secondRoute,
  severeCheckpoint,
  unknownCheckpoint,
} from '@/test/fixtures/plan'

import { Alerts } from './Alerts'
import { ApiError } from '@/api/client'
import { CheckpointDetails } from './CheckpointDetails'
import { RouteCard } from './RouteCard'
import { RouteList } from './RouteList'

describe('RouteCard', () => {
  it('shows the API values unchanged', () => {
    render(
      <RouteCard
        route={secondRoute}
        isRecommended={false}
        isSelected={false}
        onSelect={vi.fn()}
      />,
    )
    const card = screen.getByRole('button', { name: /Route 2/ })
    expect(within(card).getByText('125 mi')).toBeInTheDocument()
    expect(within(card).getByText('1 h 30 min')).toBeInTheDocument()
    expect(within(card).getByText('50 mi')).toBeInTheDocument()
    expect(within(card).getByText('12.5 mi')).toBeInTheDocument()
    expect(within(card).getByText('25 mi')).toBeInTheDocument()
    expect(within(card).getByText('1.5')).toBeInTheDocument()
    expect(within(card).getByText(secondRoute.rationale)).toBeInTheDocument()
    expect(within(card).getByText(/Arrives/)).toBeInTheDocument()
  })

  it('marks only the recommended route', () => {
    const { rerender } = render(
      <RouteCard
        route={firstRoute}
        isRecommended
        isSelected={false}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText('Recommended')).toBeInTheDocument()
    rerender(
      <RouteCard
        route={firstRoute}
        isRecommended={false}
        isSelected={false}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
  })

  it('hides the unknown miles row when weather is complete', () => {
    render(
      <RouteCard
        route={firstRoute}
        isRecommended
        isSelected={false}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.queryByText('No weather')).not.toBeInTheDocument()
  })

  it('shows average risk as unavailable when the API has none', () => {
    const route = {
      ...firstRoute,
      summary: { ...firstRoute.summary, average_risk: null },
    }
    render(
      <RouteCard
        route={route}
        isRecommended={false}
        isSelected={false}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
  })

  it('shows No Travel miles when a route has them', () => {
    const route = {
      ...firstRoute,
      summary: { ...firstRoute.summary, no_travel_miles: 15 },
    }
    render(
      <RouteCard
        route={route}
        isRecommended={false}
        isSelected={false}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText('No Travel')).toBeInTheDocument()
    expect(screen.getByText('15 mi')).toBeInTheDocument()
  })

  it('draws the strip map in proportion to each stretch of road', () => {
    render(
      <RouteCard
        route={secondRoute}
        isRecommended={false}
        isSelected={false}
        onSelect={vi.fn()}
      />,
    )
    const strip = screen.getByRole('img', { name: /Risk along the route/ })
    const widths = Array.from(strip.children).map(
      (child) => (child as HTMLElement).style.width,
    )
    expect(widths).toEqual(['20%', '60%', '20%'])
    expect(strip.getAttribute('aria-label')).toContain('Severe from mile 25')
  })

  it('reports selection, and exposes it to assistive technology', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(
      <RouteCard
        route={firstRoute}
        isRecommended
        isSelected
        onSelect={onSelect}
      />,
    )
    const card = screen.getByRole('button', { name: /Route 1/ })
    expect(card).toHaveAttribute('aria-pressed', 'true')
    await user.click(card)
    expect(onSelect).toHaveBeenCalledWith('route-2')
  })
})

describe('RouteList', () => {
  it('keeps the order the API sent and never re-sorts', () => {
    const reversed = { ...plan, routes: [secondRoute, firstRoute] }
    render(
      <RouteList plan={reversed} selectedRouteId={null} onSelect={vi.fn()} />,
    )
    const headings = screen.getAllByRole('button').map((b) => b.textContent)
    expect(headings[0]).toContain('Route 2')
    expect(headings[1]).toContain('Route 1')
  })

  it('recommends only the route the API names', () => {
    render(<RouteList plan={plan} selectedRouteId={null} onSelect={vi.fn()} />)
    const card = screen.getByRole('button', { name: /Route 1/ })
    expect(within(card).getByText('Recommended')).toBeInTheDocument()
    expect(screen.getAllByText('Recommended')).toHaveLength(1)
  })

  it('shows no recommendation when the API names none', () => {
    const blocked = { ...plan, recommended_route_id: null, no_safe_route: true }
    render(
      <RouteList plan={blocked} selectedRouteId={null} onSelect={vi.fn()} />,
    )
    expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
  })
})

describe('CheckpointDetails', () => {
  it('lists every checkpoint with its ETA and risk', () => {
    render(
      <CheckpointDetails
        route={secondRoute}
        selectedCheckpointId={null}
        onSelect={vi.fn()}
      />,
    )
    const rows = screen.getAllByRole('button')
    expect(rows).toHaveLength(3)
    expect(rows[1]).toHaveTextContent('Mile 50')
    expect(rows[1]).toHaveTextContent('Severe')
  })

  it('shows the readings of the selected checkpoint', () => {
    render(
      <CheckpointDetails
        route={secondRoute}
        selectedCheckpointId={severeCheckpoint.id}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText('38.2 mph')).toBeInTheDocument()
    expect(screen.getByText('0.12 in/hr')).toBeInTheDocument()
    expect(
      screen.getByText('Wind risk raised because of the load weight.'),
    ).toBeInTheDocument()
  })

  it('says weather is unavailable rather than showing zeros', () => {
    render(
      <CheckpointDetails
        route={secondRoute}
        selectedCheckpointId={unknownCheckpoint.id}
        onSelect={vi.fn()}
      />,
    )
    expect(
      screen.getByText('Weather is unavailable for this checkpoint.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('0 mph')).not.toBeInTheDocument()
  })

  it('reports the checkpoint chosen', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(
      <CheckpointDetails
        route={secondRoute}
        selectedCheckpointId={null}
        onSelect={onSelect}
      />,
    )
    await user.click(screen.getAllByRole('button')[1])
    expect(onSelect).toHaveBeenCalledWith(severeCheckpoint.id)
  })
})

describe('Alerts', () => {
  const noop = vi.fn()

  it('says when no route is safe', () => {
    const blocked = { ...plan, recommended_route_id: null, no_safe_route: true }
    render(<Alerts plan={blocked} isPending={false} onRetry={noop} />)
    expect(screen.getByRole('alert')).toHaveTextContent('No safe route')
  })

  it('explains when nothing could be recommended for lack of weather', () => {
    const none = { ...plan, recommended_route_id: null }
    render(<Alerts plan={none} isPending={false} onRetry={noop} />)
    expect(screen.getByRole('alert')).toHaveTextContent(
      'No route can be recommended',
    )
  })

  it('shows every warning from the API', () => {
    const warned = { ...plan, warnings: ['First warning.', 'Second warning.'] }
    render(<Alerts plan={warned} isPending={false} onRetry={noop} />)
    expect(screen.getByText('First warning.')).toBeInTheDocument()
    expect(screen.getByText('Second warning.')).toBeInTheDocument()
  })

  it('offers a retry for an outage', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const error = new ApiError('provider_unavailable', 'Service down.', 503)
    render(<Alerts error={error} isPending={false} onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Service down.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalled()
  })

  it.each(['rate_limited', 'network_error', 'server_error'])(
    'offers a retry for %s',
    (code) => {
      const error = new ApiError(code, 'Failed.', 500)
      render(<Alerts error={error} isPending={false} onRetry={noop} />)
      expect(
        screen.getByRole('button', { name: 'Try again' }),
      ).toBeInTheDocument()
    },
  )

  it('explains that no route exists, without a pointless retry', () => {
    const error = new ApiError(
      'no_route',
      'No truck route connects these.',
      422,
    )
    render(<Alerts error={error} isPending={false} onRetry={noop} />)
    expect(screen.getByRole('alert')).toHaveTextContent(
      'No truck route connects these.',
    )
    expect(
      screen.queryByRole('button', { name: 'Try again' }),
    ).not.toBeInTheDocument()
  })

  it('leaves field errors to the form', () => {
    const error = new ApiError('validation_error', 'Check fields.', 400, {})
    const { container } = render(
      <Alerts error={error} isPending={false} onRetry={noop} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('warns that a long trip can take over a minute while planning', () => {
    render(<Alerts isPending onRetry={noop} />)
    expect(screen.getByRole('status')).toHaveTextContent('over a minute')
  })
})
