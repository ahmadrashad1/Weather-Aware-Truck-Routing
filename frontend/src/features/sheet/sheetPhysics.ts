export type Detent = 'full' | 'half' | 'peek'
export type DetentPositions = Record<Detent, number>

const FULL_TOP_GAP = 56
const PEEK_HEIGHT = 86
// Where the top of the half-open sheet sits, as a share of the screen's height.
export const HALF_TOP_SHARE = 0.54

/** Apple's rate for a normal scroll feel, from Designing Fluid Interfaces. */
const DECELERATION_RATE = 0.998
const RUBBERBAND_CONSTANT = 0.55
/** How quickly the spring reaches its target, in seconds. It has no fixed duration. */
const RESPONSE_SECONDS = 0.38
const AT_REST_DISTANCE = 0.5
const AT_REST_SPEED = 5

export function detentPositions(height: number): DetentPositions {
  return {
    full: FULL_TOP_GAP,
    half: Math.round(height * HALF_TOP_SHARE),
    peek: height - PEEK_HEIGHT,
  }
}

/** How far momentum would carry a released sheet, so a flick can throw it past a stop. */
export function project(velocity: number): number {
  return ((velocity / 1000) * DECELERATION_RATE) / (1 - DECELERATION_RATE)
}

export function nearestDetent(
  position: number,
  positions: DetentPositions,
): Detent {
  const stops = Object.entries(positions) as [Detent, number][]
  return stops.reduce((best, stop) =>
    Math.abs(stop[1] - position) < Math.abs(best[1] - position) ? stop : best,
  )[0]
}

/** Resist more the further past an edge the finger goes, instead of stopping dead. */
export function rubberband(overshoot: number, dimension: number): number {
  return (
    (overshoot * dimension * RUBBERBAND_CONSTANT) /
    (dimension + RUBBERBAND_CONSTANT * Math.abs(overshoot))
  )
}

/**
 * One frame of a critically damped spring: no overshoot, unless a flick carries it there. It works
 * from the current position and velocity, so it can be grabbed or redirected at any moment.
 */
export function stepSpring(
  position: number,
  velocity: number,
  target: number,
  seconds: number,
): { position: number; velocity: number } {
  const omega = (2 * Math.PI) / RESPONSE_SECONDS
  const offset = position - target
  const rate = velocity + omega * offset
  const decay = Math.exp(-omega * seconds)
  const next = {
    position: target + (offset + rate * seconds) * decay,
    velocity: (rate - omega * (offset + rate * seconds)) * decay,
  }
  const atRest =
    Math.abs(next.position - target) < AT_REST_DISTANCE &&
    Math.abs(next.velocity) < AT_REST_SPEED
  return atRest ? { position: target, velocity: 0 } : next
}
