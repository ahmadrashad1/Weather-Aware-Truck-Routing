// How far each layer travels by the time the next page has covered the hero.
const MEDIA_TRAVEL_VH = 14
const MEDIA_GROWTH = 0.08
const COPY_TRAVEL_VH = -30
const COPY_FADE_RATE = 1 / 0.7
const CUE_FADE_RATE = 4

function clamp(value: number): number {
  return Math.min(Math.max(value, 0), 1)
}

export function parallaxAt(rawProgress: number) {
  const progress = clamp(rawProgress)
  return {
    mediaY: progress * MEDIA_TRAVEL_VH,
    mediaScale: 1 + progress * MEDIA_GROWTH,
    copyY: progress * COPY_TRAVEL_VH || 0,
    copyOpacity: clamp(1 - progress * COPY_FADE_RATE),
    cueOpacity: clamp(1 - progress * CUE_FADE_RATE),
  }
}
