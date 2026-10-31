import { beforeEach, describe, expect, it, vi } from 'vitest'

import { forecastStore } from './forecastStore'

describe('forecastStore', () => {
  beforeEach(() => {
    forecastStore.set(0)
  })

  it('starts at the hour it was last set to', () => {
    forecastStore.set(12)
    expect(forecastStore.get()).toBe(12)
  })

  it('tells subscribers about a change', () => {
    const listener = vi.fn()
    const unsubscribe = forecastStore.subscribe(listener)
    forecastStore.set(5)
    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
  })

  it('stays quiet when the hour has not changed', () => {
    forecastStore.set(5)
    const listener = vi.fn()
    const unsubscribe = forecastStore.subscribe(listener)
    forecastStore.set(5)
    expect(listener).not.toHaveBeenCalled()
    unsubscribe()
  })

  it('stops telling a subscriber who has left', () => {
    const listener = vi.fn()
    forecastStore.subscribe(listener)()
    forecastStore.set(9)
    expect(listener).not.toHaveBeenCalled()
  })
})
