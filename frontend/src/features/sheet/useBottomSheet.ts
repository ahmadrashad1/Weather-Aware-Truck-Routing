import {
  useCallback,
  useEffect,
  useRef,
  type FocusEvent,
  type MouseEvent,
  type PointerEvent,
} from 'react'

import {
  detentPositions,
  nearestDetent,
  project,
  rubberband,
  stepSpring,
  type Detent,
} from './sheetPhysics'

const PHONE_QUERY = '(max-width: 1023px)'
// Movement before a press counts as a drag, so tapping the header's button still works.
const DRAG_THRESHOLD = 8
const VELOCITY_WINDOW_MS = 100
const NEXT_DETENT: Record<Detent, Detent> = {
  peek: 'half',
  half: 'full',
  full: 'half',
}

interface Sample {
  y: number
  time: number
}

function matches(query: string): boolean {
  return (
    typeof window.matchMedia === 'function' && window.matchMedia(query).matches
  )
}

/**
 * The phone's draggable panel. Its position lives outside React and goes straight to the element,
 * so a drag at full frame rate never re-renders the map or the lists. On wide screens it does
 * nothing, and the panel is laid out by CSS alone.
 */
export function useBottomSheet() {
  const sheetRef = useRef<HTMLElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const position = useRef(0)
  const velocity = useRef(0)
  const detent = useRef<Detent>('full')
  const frame = useRef<number | null>(null)
  const samples = useRef<Sample[]>([])
  const grab = useRef<{
    pointer: number
    startY: number
    offset: number
  } | null>(null)
  const dragged = useRef(false)

  const height = () => sheetRef.current?.parentElement?.clientHeight ?? 0

  const place = useCallback((y: number) => {
    position.current = y
    if (sheetRef.current) {
      sheetRef.current.style.transform = `translate3d(0, ${y}px, 0)`
    }
  }, [])

  // The part of the sheet below the screen must still be reachable by scrolling.
  const reserveScrollRoom = useCallback((y: number) => {
    if (contentRef.current)
      contentRef.current.style.paddingBottom = `${y + 24}px`
  }, [])

  const stop = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = null
  }, [])

  const settle = useCallback(
    (next: Detent) => {
      stop()
      detent.current = next
      const target = detentPositions(height())[next]
      reserveScrollRoom(Math.max(target, position.current))
      if (matches('(prefers-reduced-motion: reduce)')) {
        place(target)
        reserveScrollRoom(target)
        return
      }
      let last = performance.now()
      const tick = (now: number) => {
        const seconds = Math.min((now - last) / 1000, 1 / 30)
        last = now
        const state = stepSpring(
          position.current,
          velocity.current,
          target,
          seconds,
        )
        velocity.current = state.velocity
        place(state.position)
        if (state.position === target && state.velocity === 0) {
          frame.current = null
          reserveScrollRoom(target)
          return
        }
        frame.current = requestAnimationFrame(tick)
      }
      frame.current = requestAnimationFrame(tick)
    },
    [place, reserveScrollRoom, stop],
  )

  const snapTo = useCallback(
    (next: Detent) => {
      if (matches(PHONE_QUERY) && detent.current !== next) settle(next)
    },
    [settle],
  )

  // Fit the current stop whenever the layout changes, and hand over to CSS on wide screens.
  useEffect(() => {
    const sheet = sheetRef.current
    if (!sheet?.parentElement || typeof ResizeObserver !== 'function') return
    const fit = () => {
      if (!matches(PHONE_QUERY)) {
        stop()
        sheet.style.transform = ''
        if (contentRef.current) contentRef.current.style.paddingBottom = ''
        return
      }
      stop()
      velocity.current = 0
      const target = detentPositions(height())[detent.current]
      place(target)
      reserveScrollRoom(target)
    }
    const observer = new ResizeObserver(fit)
    observer.observe(sheet.parentElement)
    return () => {
      observer.disconnect()
      stop()
    }
  }, [place, reserveScrollRoom, stop])

  const onPointerDown = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      if (!matches(PHONE_QUERY)) return
      if ((event.target as HTMLElement).closest('a')) return
      // Catches a moving sheet where it is, rather than where it was heading.
      stop()
      velocity.current = 0
      dragged.current = false
      grab.current = {
        pointer: event.pointerId,
        startY: event.clientY,
        offset: event.clientY - position.current,
      }
      samples.current = [{ y: event.clientY, time: event.timeStamp }]
    },
    [stop],
  )

  const onPointerMove = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      const held = grab.current
      if (!held || held.pointer !== event.pointerId) return
      if (
        !dragged.current &&
        Math.abs(event.clientY - held.startY) < DRAG_THRESHOLD
      ) {
        return
      }
      if (!dragged.current) {
        dragged.current = true
        event.currentTarget.setPointerCapture(event.pointerId)
      }
      const { full, peek } = detentPositions(height())
      const wanted = event.clientY - held.offset
      let y = wanted
      if (wanted < full) y = full - rubberband(full - wanted, height())
      if (wanted > peek) y = peek + rubberband(wanted - peek, height())
      place(y)
      samples.current.push({ y: event.clientY, time: event.timeStamp })
      samples.current = samples.current.filter(
        (sample) => event.timeStamp - sample.time <= VELOCITY_WINDOW_MS,
      )
    },
    [place],
  )

  const onPointerEnd = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      const held = grab.current
      if (!held || held.pointer !== event.pointerId) return
      grab.current = null
      if (!dragged.current) return
      const first = samples.current[0]
      const last = samples.current[samples.current.length - 1]
      const elapsed = (last.time - first.time) / 1000
      // Handed to the spring, so there's no seam between the finger and the animation.
      velocity.current = elapsed > 0 ? (last.y - first.y) / elapsed : 0
      settle(
        nearestDetent(
          position.current + project(velocity.current),
          detentPositions(height()),
        ),
      )
    },
    [settle],
  )

  const onHandleClick = useCallback(
    (event: MouseEvent<HTMLElement>) => {
      // The click that ends a drag isn't a tap.
      if (dragged.current) {
        event.preventDefault()
        dragged.current = false
        return
      }
      snapTo(NEXT_DETENT[detent.current])
    },
    [snapTo],
  )

  const onContentFocus = useCallback(
    (event: FocusEvent<HTMLElement>) => {
      // The keyboard takes half the screen, so give the field all the room there is.
      if ((event.target as HTMLElement).matches('input:not([type="range"])')) {
        snapTo('full')
      }
    },
    [snapTo],
  )

  return {
    sheetRef,
    contentRef,
    snapTo,
    onHandleClick,
    onContentFocus,
    onPointerDown,
    onPointerMove,
    onPointerEnd,
  }
}
