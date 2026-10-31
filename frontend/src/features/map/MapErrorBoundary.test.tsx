import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { MapErrorBoundary } from './MapErrorBoundary'

function Broken(): never {
  throw new Error('WebGL is not available')
}

describe('MapErrorBoundary', () => {
  it('explains the map is unavailable and points to the route list', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <MapErrorBoundary>
        <Broken />
      </MapErrorBoundary>,
    )
    expect(screen.getByRole('status')).toHaveTextContent(
      'The map could not start in this browser',
    )
    expect(screen.getByRole('status')).toHaveTextContent('route list')
    quiet.mockRestore()
  })

  it('shows the map when nothing is wrong', () => {
    render(
      <MapErrorBoundary>
        <p>Working map</p>
      </MapErrorBoundary>,
    )
    expect(screen.getByText('Working map')).toBeInTheDocument()
  })
})
