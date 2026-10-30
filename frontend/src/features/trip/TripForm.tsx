import { useState, type FormEvent } from 'react'

import { ApiError, type Location, type PlanRequest } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { localInputToOffsetIso, nextHourLocalInput } from '@/lib/format'

import { PlaceInput } from './PlaceInput'

const INTERVALS = [10, 25, 50] as const
type Interval = (typeof INTERVALS)[number]

interface FieldErrors {
  origin?: string
  destination?: string
  departure_at?: string
  load_lb?: string
}

function firstMessage(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return firstMessage(value[0])
  if (value && typeof value === 'object') {
    return firstMessage(Object.values(value)[0])
  }
  return undefined
}

function apiFieldErrors(error?: ApiError | null): FieldErrors {
  const fields = error?.fields ?? {}
  return {
    origin: firstMessage(fields.origin),
    destination: firstMessage(fields.destination),
    departure_at: firstMessage(fields.departure_at),
    load_lb: firstMessage(fields.load_lb),
  }
}

interface TripFormProps {
  onSubmit: (request: PlanRequest) => void
  isPending: boolean
  error?: ApiError | null
}

export function TripForm({ onSubmit, isPending, error }: TripFormProps) {
  const [origin, setOrigin] = useState<Location | null>(null)
  const [destination, setDestination] = useState<Location | null>(null)
  const [departure, setDeparture] = useState(() =>
    nextHourLocalInput(new Date()),
  )
  const [load, setLoad] = useState('')
  const [interval, setInterval] = useState<Interval>(25)
  const [localErrors, setLocalErrors] = useState<FieldErrors>({})

  const errors = { ...apiFieldErrors(error), ...localErrors }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const missing: FieldErrors = {}
    if (!origin) missing.origin = 'Choose a place from the suggestions.'
    if (!destination) {
      missing.destination = 'Choose a place from the suggestions.'
    }
    if (!departure) missing.departure_at = 'Choose a departure time.'
    if (load.trim() === '') missing.load_lb = 'Enter the load weight.'
    setLocalErrors(missing)
    if (!origin || !destination || Object.keys(missing).length > 0) return

    onSubmit({
      origin,
      destination,
      departure_at: localInputToOffsetIso(departure),
      load_lb: Number(load),
      interval_miles: interval,
    })
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <PlaceInput
        label="Origin"
        value={origin}
        onChange={setOrigin}
        error={errors.origin}
      />
      <PlaceInput
        label="Destination"
        value={destination}
        onChange={setDestination}
        error={errors.destination}
      />

      <div className="grid gap-3 sm:grid-cols-[3fr_2fr]">
        <div className="grid content-start gap-1.5">
          <Label htmlFor="departure">Departure</Label>
          <Input
            id="departure"
            type="datetime-local"
            className="bg-white"
            value={departure}
            aria-invalid={Boolean(errors.departure_at)}
            onChange={(event) => setDeparture(event.target.value)}
          />
          {errors.departure_at ? (
            <p className="text-sm font-medium text-risk-severe">
              {errors.departure_at}
            </p>
          ) : null}
        </div>
        <div className="grid content-start gap-1.5">
          <Label htmlFor="load">Load weight (lb)</Label>
          <Input
            id="load"
            type="number"
            inputMode="numeric"
            min={0}
            step={500}
            className="bg-white"
            value={load}
            aria-invalid={Boolean(errors.load_lb)}
            onChange={(event) => setLoad(event.target.value)}
          />
          {errors.load_lb ? (
            <p className="text-sm font-medium text-risk-severe">
              {errors.load_lb}
            </p>
          ) : null}
        </div>
      </div>

      <fieldset
        role="radiogroup"
        aria-label="Weather check every"
        className="grid gap-1.5"
      >
        <legend className="mb-1.5 text-sm leading-none font-medium">
          Weather check every
        </legend>
        <div className="grid grid-cols-3 overflow-hidden rounded-md border border-asphalt/25 bg-white">
          {INTERVALS.map((value) => (
            <label
              key={value}
              className="cursor-pointer border-l border-asphalt/25 py-2 text-center text-sm font-medium first:border-l-0 has-checked:bg-asphalt has-checked:text-white has-focus-visible:outline-2 has-focus-visible:-outline-offset-2 has-focus-visible:outline-sign-green"
            >
              <input
                type="radio"
                name="interval"
                value={value}
                checked={interval === value}
                onChange={() => setInterval(value)}
                className="sr-only"
              />
              {value} mi
            </label>
          ))}
        </div>
      </fieldset>

      <Button type="submit" disabled={isPending} className="h-11 text-base">
        {isPending ? 'Planning routes' : 'Plan routes'}
      </Button>
    </form>
  )
}
