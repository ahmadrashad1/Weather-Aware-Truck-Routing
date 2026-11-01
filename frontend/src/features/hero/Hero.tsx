import { ChevronDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import posterUrl from '@/assets/hero/poster.jpg'
import mp4Url from '@/assets/hero/routes.mp4'
import webmUrl from '@/assets/hero/routes.webm'

import { parallaxAt } from './parallax'

function prefersStill(): boolean {
  const connection = (
    navigator as Navigator & { connection?: { saveData?: boolean } }
  ).connection
  return (
    Boolean(connection?.saveData) ||
    (typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  )
}

export function Hero() {
  const [still] = useState(prefersStill)
  const mediaRef = useRef<HTMLDivElement>(null)
  const copyRef = useRef<HTMLDivElement>(null)
  const cueRef = useRef<HTMLAnchorElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    if (still) return
    let frame: number | null = null
    let covered = false

    // Written straight to the layers, tied 1:1 to the scroll, so nothing re-renders in React.
    function apply() {
      frame = null
      const progress = window.scrollY / window.innerHeight
      const layers = parallaxAt(progress)
      if (mediaRef.current) {
        mediaRef.current.style.transform = `translate3d(0, ${layers.mediaY}vh, 0) scale(${layers.mediaScale})`
      }
      if (copyRef.current) {
        copyRef.current.style.transform = `translate3d(0, ${layers.copyY}vh, 0)`
        copyRef.current.style.opacity = String(layers.copyOpacity)
      }
      if (cueRef.current) {
        cueRef.current.style.opacity = String(layers.cueOpacity)
      }
      // A film nobody can see shouldn't compete with the map for the graphics chip.
      const nowCovered = progress >= 1
      if (nowCovered !== covered && videoRef.current) {
        covered = nowCovered
        if (covered) videoRef.current.pause()
        else void videoRef.current.play()
      }
    }

    function onScroll() {
      if (frame === null) frame = requestAnimationFrame(apply)
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame !== null) cancelAnimationFrame(frame)
    }
  }, [still])

  return (
    <>
      {/* The hero is sticky, so the browser thinks it's always in view and won't scroll to it. */}
      <span id="top" aria-hidden className="absolute top-0" />
      <header className="sticky top-0 isolate flex h-dvh snap-start flex-col overflow-hidden bg-black text-white">
        <div
          ref={mediaRef}
          data-layer="media"
          aria-hidden
          className="absolute inset-0 -z-10 will-change-transform"
        >
          {still ? (
            <img
              src={posterUrl}
              alt=""
              className="size-full object-cover object-[50%_70%]"
            />
          ) : (
            <video
              ref={videoRef}
              autoPlay
              muted
              loop
              playsInline
              poster={posterUrl}
              className="size-full object-cover object-[50%_70%]"
            >
              <source src={webmUrl} type="video/webm" />
              <source src={mp4Url} type="video/mp4" />
            </video>
          )}
        </div>

        {/* Keeps the words readable over the film, whatever frame it's on. */}
        <div
          aria-hidden
          className="absolute inset-x-0 top-0 -z-10 h-[62%] bg-gradient-to-b from-black via-black/85 to-transparent"
        />

        <div
          ref={copyRef}
          data-layer="copy"
          className="mx-auto flex w-full max-w-4xl flex-col items-center px-6 pt-[max(12dvh,4.5rem)] text-center will-change-transform"
        >
          <h1 className="display-type text-balance">
            Weather-Aware Truck Routing
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-snug text-balance text-white/70 sm:text-xl">
            Three routes, checked against the forecast for the hour your truck
            reaches each mile. Then the one with the least severe weather,
            chosen for you.
          </p>
          <a
            href="#plan"
            className="pressable mt-7 rounded-full bg-action px-6 py-3 text-base font-medium text-white hover:bg-action/90 focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-white"
          >
            Plan a trip
          </a>
        </div>

        <a
          ref={cueRef}
          href="#plan"
          aria-label="Scroll down to the route planner"
          className="pressable absolute inset-x-0 bottom-6 mx-auto flex w-fit flex-col items-center gap-1 rounded-full px-4 py-2 text-sm text-white/70 hover:text-white focus-visible:outline-2 focus-visible:outline-white"
        >
          Scroll
          <ChevronDown aria-hidden className="scroll-cue size-5" />
        </a>
      </header>
    </>
  )
}
