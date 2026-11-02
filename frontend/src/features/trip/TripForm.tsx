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
        <div className="relative grid grid-cols-3 rounded-xl bg-asphalt/5 p-0.5">
          {/* One thumb that slides, as on a segmented control, rather than a colour swap. */}
          <span
            aria-hidden
            data-testid="interval-thumb"
            className="absolute inset-y-0.5 left-0.5 w-[calc((100%-0.25rem)/3)] rounded-[0.625rem] bg-white shadow-[0_1px_4px_rgb(0_0_0/0.16)] transition-transform duration-300 ease-[var(--ease-settle)] motion-reduce:transition-none"
            style={{
              transform: `translateX(${INTERVALS.indexOf(interval) * 100}%)`,
            }}
          />
          {INTERVALS.map((value) => (
            <label
              key={value}
              className="relative flex min-h-11 cursor-pointer items-center justify-center rounded-[0.625rem] text-sm font-medium lg:min-h-9 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-action"
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

      <Button type="submit" disabled={isPending} className="h-12 text-base">
        {isPending ? 'Planning routes' : 'Plan routes'}
      </Button>
    </form>
  )
}
