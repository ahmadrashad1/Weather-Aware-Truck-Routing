import type { components } from './schema'

type Schemas = components['schemas']

export type PlanRequest = Schemas['PlanRequest']
export type PlanResponse = Schemas['PlanResponse']
export type Route = Schemas['Route']
export type Checkpoint = Schemas['Checkpoint']
export type Segment = Schemas['Segment']
export type Location = Schemas['Location']
export type RiskCode = Schemas['RiskOrUnknownEnum']
export type HeatmapRequest = Schemas['HeatmapRequest']
export type HeatmapResponse = Schemas['HeatmapResponse']

const API_BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly fields?: Record<string, unknown>

  constructor(
    code: string,
    message: string,
    status: number,
    fields?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.fields = fields
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new ApiError(
      'network_error',
      'The server could not be reached. Check your connection and try again.',
      0,
    )
  }
  if (response.ok) {
    return (await response.json()) as T
  }
  throw await readError(response)
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as Schemas['Error']
    return new ApiError(body.code, body.message, response.status, body.fields)
  } catch {
    return new ApiError(
      'server_error',
      'Something went wrong on the server. Try again shortly.',
      response.status,
    )
  }
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function planTrip(body: PlanRequest): Promise<PlanResponse> {
  return postJson('/api/v1/trips/plan', body)
}

export function fetchHeatmap(body: HeatmapRequest): Promise<HeatmapResponse> {
  return postJson('/api/v1/trips/heatmap', body)
}

export function fetchAttribution(
  signal?: AbortSignal,
): Promise<Schemas['AttributionResponse']> {
  return request('/api/v1/attribution', { signal })
}

export function geocode(
  query: string,
  signal?: AbortSignal,
): Promise<Schemas['GeocodeResponse']> {
  return request(`/api/v1/geocode?q=${encodeURIComponent(query)}`, { signal })
}
