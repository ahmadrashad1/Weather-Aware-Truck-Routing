import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { jsonResponse, renderWithQueries } from '@/test/render'

import { TripForm } from './TripForm'

const DALLAS = { label: 'Dallas, TX', lat: 32.77, lon: -96.79 }
const DENVER = { label: 'Denver, CO', lat: 39.73, lon: -104.99 }

function stubGeocoding() {
  const fetchMock = vi.fn((input: string) => {
    const query = decodeURIComponent(input.split('q=')[1])
    const results = query.startsWith('Dal') ? [DALLAS] : [DENVER]
    return Promise.resolve(jsonResponse({ results }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function choosePlace(
  user: ReturnType<typeof userEvent.setup>,
  field: string,
  text: string,
  label: string,
) {
  await user.type(screen.getByRole('combobox', { name: field }), text)
  await user.click(await screen.findByRole('option', { name: label }))
}

describe('TripForm', () => {
  beforeEach(() => {
    stubGeocoding()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('submits the trip with an ISO departure that includes an offset', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    renderWithQueries(<TripForm onSubmit={onSubmit} isPending={false} />)

    await choosePlace(user, 'Origin', 'Dal', 'Dallas, TX')
    await choosePlace(user, 'Destination', 'Den', 'Denver, CO')
    await user.clear(screen.getByLabelText('Departure'))
    await user.type(screen.getByLabelText('Departure'), '2026-11-01T12:30')
    await user.type(screen.getByLabelText('Load weight (lb)'), '45000')
    await user.click(screen.getByRole('radio', { name: '10 mi' }))
    await user.click(screen.getByRole('button', { name: 'Plan routes' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    const request = onSubmit.mock.calls[0][0]
    expect(request).toMatchObject({
      origin: DALLAS,
      destination: DENVER,
      load_lb: 45000,
      interval_miles: 10,
    })
    expect(request.departure_at).toMatch(/^2026-11-01T12:30:00[+-]\d{2}:\d{2}$/)
  })

  it('offers exactly the 10, 25 and 50 mile intervals', () => {
    renderWithQueries(<TripForm onSubmit={vi.fn()} isPending={false} />)
    const group = screen.getByRole('radiogroup', {
      name: 'Weather check every',
    })
    const names = within(group)
      .getAllByRole('radio')
      .map((radio) => radio.getAttribute('value'))
    expect(names).toEqual(['10', '25', '50'])
  })

  it('requires places chosen from the suggestions, not free text', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    renderWithQueries(<TripForm onSubmit={onSubmit} isPending={false} />)

    await user.type(screen.getByRole('combobox', { name: 'Origin' }), 'Dal')
    await user.type(
      screen.getByRole('combobox', { name: 'Destination' }),
      'Den',
    )
    await user.click(screen.getByRole('button', { name: 'Plan routes' }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(
      screen.getAllByText('Choose a place from the suggestions.'),
    ).toHaveLength(2)
  })

  it('requires a load weight, with no default that could change the risk', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    renderWithQueries(<TripForm onSubmit={onSubmit} isPending={false} />)

    expect(screen.getByLabelText('Load weight (lb)')).toHaveValue(null)
    await choosePlace(user, 'Origin', 'Dal', 'Dallas, TX')
    await choosePlace(user, 'Destination', 'Den', 'Denver, CO')
    await user.click(screen.getByRole('button', { name: 'Plan routes' }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText('Enter the load weight.')).toBeInTheDocument()
  })

  it('defaults the departure to a future time', () => {
    renderWithQueries(<TripForm onSubmit={vi.fn()} isPending={false} />)
    const value = (screen.getByLabelText('Departure') as HTMLInputElement).value
    expect(new Date(value).getTime()).toBeGreaterThan(Date.now())
  })

  it('clears a chosen place when its text is edited', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    renderWithQueries(<TripForm onSubmit={onSubmit} isPending={false} />)

    await choosePlace(user, 'Origin', 'Dal', 'Dallas, TX')
    await choosePlace(user, 'Destination', 'Den', 'Denver, CO')
    await user.type(screen.getByRole('combobox', { name: 'Origin' }), 'x')
    await user.click(screen.getByRole('button', { name: 'Plan routes' }))

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('chooses a suggestion with the keyboard', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    renderWithQueries(<TripForm onSubmit={onSubmit} isPending={false} />)

    await user.type(screen.getByRole('combobox', { name: 'Origin' }), 'Dal')
    await screen.findByRole('option', { name: 'Dallas, TX' })
    await user.keyboard('{ArrowDown}{Enter}')

    expect(screen.getByRole('combobox', { name: 'Origin' })).toHaveValue(
      'Dallas, TX',
    )
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('waits for a pause in typing before searching', async () => {
    const user = userEvent.setup()
    const fetchMock = stubGeocoding()
    renderWithQueries(<TripForm onSubmit={vi.fn()} isPending={false} />)

    await user.type(screen.getByRole('combobox', { name: 'Origin' }), 'Dallas')
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not search for a single character', async () => {
    const user = userEvent.setup()
    const fetchMock = stubGeocoding()
    renderWithQueries(<TripForm onSubmit={vi.fn()} isPending={false} />)

    await user.type(screen.getByRole('combobox', { name: 'Origin' }), 'D')
    await new Promise((resolve) => setTimeout(resolve, 350))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('says when a search finds nothing', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ results: [] }))),
    )
    renderWithQueries(<TripForm onSubmit={vi.fn()} isPending={false} />)

    await user.type(screen.getByRole('combobox', { name: 'Origin' }), 'Zzz')
    expect(await screen.findByText('No places found.')).toBeInTheDocument()
  })

  it('says when place search is unavailable', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ code: 'provider_unavailable', message: 'x' }, 503),
        ),
      ),
    )
    renderWithQueries(<TripForm onSubmit={vi.fn()} isPending={false} />)

    await user.type(screen.getByRole('combobox', { name: 'Origin' }), 'Dal')
    expect(
      await screen.findByText(
        'Place search is unavailable. Try again shortly.',
      ),
    ).toBeInTheDocument()
  })

  it('shows field errors returned by the API beside their fields', () => {
    const error = new ApiError('validation_error', 'Check', 400, {
      load_lb: ['Ensure this value is at most 80000.'],
      departure_at: ['Departure cannot be in the past.'],
      origin: { lat: ['Too far north.'] },
    })
    renderWithQueries(
      <TripForm onSubmit={vi.fn()} isPending={false} error={error} />,
    )
    expect(
      screen.getByText('Ensure this value is at most 80000.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Departure cannot be in the past.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Too far north.')).toBeInTheDocument()
  })

  it('disables the button and says so while planning', () => {
    renderWithQueries(<TripForm onSubmit={vi.fn()} isPending />)
    expect(
      screen.getByRole('button', { name: 'Planning routes' }),
    ).toBeDisabled()
  })
})
