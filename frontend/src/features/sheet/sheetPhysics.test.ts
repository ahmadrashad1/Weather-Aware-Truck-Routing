import { describe, expect, it } from 'vitest'

import {
  detentPositions,
  nearestDetent,
  project,
  rubberband,
  stepSpring,
} from './sheetPhysics'

describe('detentPositions', () => {
  it('orders the sheet from nearly full height down to a peek', () => {
    const { full, half, peek } = detentPositions(800)
    expect(full).toBeLessThan(half)
    expect(half).toBeLessThan(peek)
    expect(peek).toBeLessThan(800)
  })
})

describe('project', () => {
  it('throws a flick further than its release point', () => {
    expect(project(1000)).toBeGreaterThan(100)
    expect(project(-1000)).toBeLessThan(-100)
  })

  it('leaves a still release where it is', () => {
    expect(project(0)).toBe(0)
  })
})

describe('nearestDetent', () => {
  const positions = { full: 50, half: 400, peek: 700 }

  it('chooses the closest stop', () => {
    expect(nearestDetent(100, positions)).toBe('full')
    expect(nearestDetent(420, positions)).toBe('half')
    expect(nearestDetent(900, positions)).toBe('peek')
  })
})

describe('rubberband', () => {
  it('follows less the further past the edge the finger goes', () => {
    const near = rubberband(50, 800)
    const far = rubberband(200, 800)
    expect(near).toBeLessThan(50)
    expect(far).toBeGreaterThan(near)
    expect(far - near).toBeLessThan(150)
  })

  it('has no effect at the edge itself', () => {
    expect(rubberband(0, 800)).toBe(0)
  })
})

describe('stepSpring', () => {
  function settle(from: number, velocity: number, target: number) {
    let state = { position: from, velocity }
    const path = [state.position]
    for (let frame = 0; frame < 240; frame++) {
      state = stepSpring(state.position, state.velocity, target, 1 / 60)
      path.push(state.position)
    }
    return { state, path }
  }

  it('reaches its target', () => {
    const { state } = settle(700, 0, 100)
    expect(state.position).toBeCloseTo(100, 0)
    expect(Math.abs(state.velocity)).toBeLessThan(1)
  })

  it('never overshoots when released from rest', () => {
    const { path } = settle(700, 0, 100)
    expect(Math.min(...path)).toBeGreaterThanOrEqual(99.9)
  })

  it('carries the release velocity into its first frame', () => {
    const still = stepSpring(400, 0, 100, 1 / 60)
    const flicked = stepSpring(400, -2000, 100, 1 / 60)
    expect(flicked.position).toBeLessThan(still.position)
  })

  it('stays put once it has arrived', () => {
    expect(stepSpring(100, 0, 100, 1 / 60)).toEqual({
      position: 100,
      velocity: 0,
    })
  })
})
