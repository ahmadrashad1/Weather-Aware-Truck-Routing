import { useSyncExternalStore } from 'react'

type Listener = () => void

let currentHour = 0
const listeners = new Set<Listener>()

/**
 * The slider's hour lives outside React. Dragging it can fire dozens of updates a second, and
 * keeping it in component state would re-render the map panel on every one.
 */
export const forecastStore = {
  get: (): number => currentHour,
  set(hour: number): void {
    if (hour === currentHour) return
    currentHour = hour
    listeners.forEach((listener) => listener())
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  },
}

export function useForecastHour(): number {
  return useSyncExternalStore(forecastStore.subscribe, forecastStore.get)
}
