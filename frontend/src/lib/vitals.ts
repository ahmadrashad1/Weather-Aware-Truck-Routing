import { onCLS, onFCP, onINP, onLCP, onTTFB } from 'web-vitals'

import type { components } from '@/api/schema'

type Vital = components['schemas']['Vital']

const API_BASE = import.meta.env.VITE_API_URL ?? ''

/** Measurements are best effort, so a lost one never affects the page. */
export function sendVital({ name, value, rating }: Vital): void {
  if (typeof navigator.sendBeacon !== 'function') return
  // A beacon still arrives if the page is closing, which is when several of these are reported.
  navigator.sendBeacon(
    `${API_BASE}/api/v1/vitals`,
    new Blob([JSON.stringify({ name, value, rating })], {
      type: 'application/json',
    }),
  )
}

export function reportVitals(): void {
  onCLS(sendVital)
  onFCP(sendVital)
  onINP(sendVital)
  onLCP(sendVital)
  onTTFB(sendVital)
}
