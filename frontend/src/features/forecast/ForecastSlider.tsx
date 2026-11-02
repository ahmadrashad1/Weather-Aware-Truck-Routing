import { useMemo } from 'react'

import { ApiError, type HeatmapResponse } from '@/api/client'
import { Button } from '@/components/ui/button'
import { formatEta } from '@/lib/format'

import { forecastStore, useForecastHour } from './forecastStore'

const LAST_HOUR = 48
const MS_PER_HOUR = 60 * 60 * 1000
// Floats over the top of the map on a phone, above the sheet, and low on a wide map, where the
// map leaves room for it when fitting a trip.
const PANEL_CLASS =
  'material absolute inset-x-3 top-14 z-10 rounded-2xl px-3.5 py-2 text-sm lg:top-auto lg:right-4 lg:bottom-9 lg:left-[27.5rem] lg:mx-auto lg:max-w-xl lg:px-4 lg:py-2.5'

function hourLabel(departureAt: string, hour: number, timeZone?: string) {
  const at = new Date(Date.parse(departureAt) + hour * MS_PER_HOUR)
  return `Hour ${hour}: ${formatEta(at.toISOString(), timeZone)}`
}

interface ForecastSliderProps {
  departureAt: string
  data: HeatmapResponse | undefined
  isLoading: boolean
  error: ApiError | null
  onRetry: () => void
  timeZone?: string
}

export function ForecastSlider({
  departureAt,
  data,
  isLoading,
  error,
  onRetry,
  timeZone,
}: ForecastSliderProps) {
  if (error) {
    return (
      <div role="alert" className={PANEL_CLASS}>
        <p>{error.message}</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-1.5"
          onClick={onRetry}
        >
          Try again
        </Button>
      </div>
    )
  }
  if (isLoading || !data) {
    return (
      <p role="status" className={PANEL_CLASS}>
        Loading the forecast. This can take up to a minute when the weather
        service is busy.
      </p>
    )
  }
  return <Slider departureAt={departureAt} data={data} timeZone={timeZone} />
}

function Slider({
  departureAt,
  data,
  timeZone,
}: {
  departureAt: string
  data: HeatmapResponse
  timeZone?: string
}) {
  // Only this component follows the hour, so moving the slider re-renders nothing else.
  const hour = useForecastHour()
  const label = hourLabel(departureAt, hour, timeZone)
  const missingByHour = useMemo(
    () =>
      Array.from(
        { length: data.hours },
        (_, frame) =>
          data.risk.filter((frames) => frames[frame] === null).length,
      ),
    [data],
  )
  const missing = missingByHour[hour] ?? 0

  return (
    <div className={PANEL_CLASS}>
      <label htmlFor="forecast-hour" className="block font-semibold">
        Forecast hour
      </label>
      <p className="tabular-nums">{label}</p>
      <input
        id="forecast-hour"
        type="range"
        min={0}
        max={LAST_HOUR}
        step={1}
        value={hour}
        aria-valuetext={label}
        className="h-8 w-full accent-action lg:my-1 lg:h-auto"
        onChange={(event) => forecastStore.set(Number(event.target.value))}
      />
      <p className="hidden text-xs text-asphalt/70 lg:block">
        Shading shows risk for this load at the hour above. Route colours use
        each checkpoint&apos;s arrival time.
      </p>
      {missing > 0 ? (
        <p className="text-xs font-medium">
          No forecast for {missing} of {data.risk.length} points at this hour.
        </p>
      ) : null}
    </div>
  )
}
