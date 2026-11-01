import { useMutation, useQuery } from '@tanstack/react-query'

import {
  ApiError,
  fetchAttribution,
  fetchHeatmap,
  geocode,
  planTrip,
  type HeatmapResponse,
  type PlanRequest,
  type PlanResponse,
} from './client'

const MIN_SEARCH_LENGTH = 2

// A plan is large, and query keys are hashed on every render, so key on a small id per plan.
// Route ids repeat between plans, so they cannot identify one.
const planIds = new WeakMap<PlanResponse, number>()
let nextPlanId = 1

function planId(plan: PlanResponse | undefined): number | null {
  if (!plan) return null
  let id = planIds.get(plan)
  if (id === undefined) {
    id = nextPlanId++
    planIds.set(plan, id)
  }
  return id
}

export function usePlanTrip() {
  return useMutation<PlanResponse, ApiError, PlanRequest>({
    mutationFn: planTrip,
  })
}

export function useGeocode(query: string) {
  const trimmed = query.trim()
  return useQuery({
    queryKey: ['geocode', trimmed.toLowerCase()],
    queryFn: ({ signal }) => geocode(trimmed, signal),
    enabled: trimmed.length >= MIN_SEARCH_LENGTH,
    // TomTom's terms allow client caching only when its response has cache headers, and search
    // responses don't. A result is gone as soon as nothing is showing it.
    staleTime: 0,
    gcTime: 0,
  })
}

export function useAttribution() {
  return useQuery({
    queryKey: ['attribution'],
    queryFn: ({ signal }) => fetchAttribution(signal),
  })
}

export function useHeatmap(
  plan: PlanResponse | undefined,
  request: PlanRequest | undefined,
) {
  return useQuery<HeatmapResponse, ApiError>({
    queryKey: ['heatmap', planId(plan)],
    queryFn: () =>
      fetchHeatmap({
        routes: plan!.routes.map((route) => route.geometry.coordinates),
        departure_at: request!.departure_at,
        load_lb: request!.load_lb,
      }),
    enabled: Boolean(plan && request && plan.routes.length > 0),
    staleTime: Infinity,
  })
}
