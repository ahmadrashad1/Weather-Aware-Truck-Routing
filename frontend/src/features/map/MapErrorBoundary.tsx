import { Component, type ReactNode } from 'react'

interface MapErrorBoundaryProps {
  children: ReactNode
}

/** The map needs WebGL. Without it, the route list still has everything the driver needs. */
export class MapErrorBoundary extends Component<
  MapErrorBoundaryProps,
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <p role="status" className="max-w-sm p-6 text-center text-asphalt/70">
          The map could not start in this browser. Use the route list to compare
          routes and checkpoints.
        </p>
      )
    }
    return this.props.children
  }
}
