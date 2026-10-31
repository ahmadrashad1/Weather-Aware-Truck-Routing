import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, type HeatmapResponse } from '@/api/client'

import { ForecastSlider } from './ForecastSlider'
import { forecastStore } from './forecastStore'

const DEPARTURE = '2026-11-01T15:00:00Z'

function heatmap(risk: (number | null)[][]): HeatmapResponse {
  return {
    departure_at: DEPARTURE,
    hours: 49,
    points: risk.map(() => [-97, 33]),
    risk,
  }
}

const COMPLETE = heatmap([
  Array.from({ length: 49 }, () => 0),
  Array.from({ length: 49 }, () => 1),
])

function setup(overrides: Partial<Parameters<typeof ForecastSlider>[0]> = {}) {
  const props = {
    departureAt: DEPARTURE,
    data: COMPLETE,
    isLoading: false,
    error: null,
    onRetry: vi.fn(),
    timeZone: 'America/Chicago',
    ...overrides,
  }
  render(<ForecastSlider {...props} />)
  return props
}

describe('ForecastSlider', () => {
  beforeEach(() => {
    forecastStore.set(0)
  })

  it('covers hour 0 to hour 48 in steps of one', () => {
    setup()
    const slider = screen.getByRole('slider', { name: 'Forecast hour' })
    expect(slider).toHaveAttribute('min', '0')
    expect(slider).toHaveAttribute('max', '48')
    expect(slider).toHaveAttribute('step', '1')
  })

  it('labels the hour with its clock time from departure', () => {
    setup()
    expect(screen.getByText(/Hour 0/)).toHaveTextContent('Nov 1, 9:00 AM CST')
    fireEvent.change(screen.getByRole('slider'), { target: { value: '24' } })
    expect(screen.getByText(/Hour 24/)).toHaveTextContent('Nov 2, 9:00 AM CST')
  })

  it('describes the hour to assistive technology', () => {
    setup()
    fireEvent.change(screen.getByRole('slider'), { target: { value: '12' } })
    expect(screen.getByRole('slider')).toHaveAttribute(
      'aria-valuetext',
      expect.stringContaining('Hour 12'),
    )
  })

  it('moves the shared hour, so the map can follow', () => {
    setup()
    fireEvent.change(screen.getByRole('slider'), { target: { value: '30' } })
    expect(forecastStore.get()).toBe(30)
  })

  it('follows the shared hour when something else resets it', () => {
    setup()
    fireEvent.change(screen.getByRole('slider'), { target: { value: '30' } })
    expect(screen.getByRole('slider')).toHaveValue('30')
  })

  it('notes points with no weather at this hour, and only at this hour', () => {
    const frames: (number | null)[] = Array.from({ length: 49 }, () => 0)
    frames[3] = null
    setup({ data: heatmap([frames, Array.from({ length: 49 }, () => 1)]) })
    expect(screen.queryByText(/No forecast/)).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('slider'), { target: { value: '3' } })
    expect(
      screen.getByText(/No forecast for 1 of 2 points/),
    ).toBeInTheDocument()
  })

  it('explains what the shading shows, and how it differs from route colours', () => {
    setup()
    expect(screen.getByText(/Shading shows risk/)).toBeInTheDocument()
    expect(screen.getByText(/arrival time/)).toBeInTheDocument()
  })

  it('says the forecast is loading, without a slider to move yet', () => {
    setup({ data: undefined, isLoading: true })
    expect(screen.getByRole('status')).toHaveTextContent(/Loading the forecast/)
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
  })

  it('reports a failed forecast with a way to retry', async () => {
    const user = userEvent.setup()
    const error = new ApiError('provider_unavailable', 'Service down.', 503)
    const { onRetry } = setup({ data: undefined, error })
    expect(screen.getByRole('alert')).toHaveTextContent('Service down.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalled()
  })
})
