import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Hero } from './Hero'
import { parallaxAt } from './parallax'

let nextFrame: FrameRequestCallback | undefined

function setReducedMotion(reduced: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('prefers-reduced-motion') && reduced,
  }))
}

function scrollTo(y: number) {
  vi.stubGlobal('scrollY', y)
  act(() => {
    window.dispatchEvent(new Event('scroll'))
    nextFrame?.(0)
  })
}

describe('parallaxAt', () => {
  it('leaves everything in place at the top of the page', () => {
    expect(parallaxAt(0)).toEqual({
      mediaY: 0,
      mediaScale: 1,
      copyY: 0,
      copyOpacity: 1,
      cueOpacity: 1,
    })
  })

  it('moves the film and the words at different speeds', () => {
    const { mediaY, copyY } = parallaxAt(0.5)
    expect(mediaY).toBeGreaterThan(0)
    expect(copyY).toBeLessThan(0)
    expect(Math.abs(copyY)).toBeGreaterThan(mediaY)
  })

  it('fades the words out before the next page covers them', () => {
    expect(parallaxAt(0.7).copyOpacity).toBe(0)
    expect(parallaxAt(0.25).cueOpacity).toBe(0)
  })

  it('never goes past either end of the scroll', () => {
    expect(parallaxAt(-1)).toEqual(parallaxAt(0))
    expect(parallaxAt(4)).toEqual(parallaxAt(1))
  })
})

describe('Hero', () => {
  beforeEach(() => {
    setReducedMotion(false)
    vi.stubGlobal('requestAnimationFrame', (run: FrameRequestCallback) => {
      nextFrame = run
      return 1
    })
    vi.stubGlobal('innerHeight', 800)
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('introduces the software and leads to the planner', () => {
    render(<Hero />)
    expect(
      screen.getByRole('heading', { name: 'Weather-Aware Truck Routing' }),
    ).toBeVisible()
    expect(screen.getByRole('link', { name: 'Plan a trip' })).toHaveAttribute(
      'href',
      '#plan',
    )
    expect(
      screen.getByRole('link', { name: 'Scroll down to the route planner' }),
    ).toHaveAttribute('href', '#plan')
  })

  it('moves its layers as the page scrolls, without re-rendering', () => {
    const { container } = render(<Hero />)
    const media = container.querySelector<HTMLElement>('[data-layer="media"]')!
    const copy = container.querySelector<HTMLElement>('[data-layer="copy"]')!
    scrollTo(400)
    expect(media.style.transform).toContain('translate3d')
    expect(copy.style.opacity).not.toBe('1')
  })

  it('stops the film once the next page has covered it', () => {
    const { container } = render(<Hero />)
    const video = container.querySelector('video')!
    scrollTo(800)
    expect(video.pause).toHaveBeenCalled()
    scrollTo(100)
    expect(video.play).toHaveBeenCalled()
  })

  it('shows a still and no parallax for people who reduce motion', () => {
    setReducedMotion(true)
    const { container } = render(<Hero />)
    expect(container.querySelector('video')).toBeNull()
    expect(container.querySelector('img')).not.toBeNull()
    scrollTo(400)
    const media = container.querySelector<HTMLElement>('[data-layer="media"]')!
    expect(media.style.transform).toBe('')
  })
})
