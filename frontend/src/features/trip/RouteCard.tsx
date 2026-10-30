import { memo } from 'react'

import type { Route } from '@/api/client'
import { formatDuration, formatEta, formatMiles } from '@/lib/format'
import { RISK_DISPLAY } from '@/lib/risk'
import { cn } from '@/lib/utils'

interface RouteCardProps {
  route: Route
  isRecommended: boolean
  isSelected: boolean
  onSelect: (routeId: string) => void
}

function StripMap({ route }: { route: Route }) {
  const total = route.summary.distance_miles
  const description = route.segments
    .map(
      (segment) =>
        `${RISK_DISPLAY[segment.risk].label} from mile ${segment.from_mile} to ${segment.to_mile}`,
    )
    .join(', ')
  return (
    <span
      role="img"
      aria-label={`Risk along the route: ${description}`}
      className="flex h-3.5 w-full overflow-hidden rounded-sm border border-white bg-white"
    >
      {route.segments.map((segment) => (
        <span
          key={segment.from_mile}
          className="block h-full"
          style={{
            width: `${Math.round(((segment.to_mile - segment.from_mile) / total) * 10000) / 100}%`,
            backgroundColor: RISK_DISPLAY[segment.risk].color,
          }}
        />
      ))}
    </span>
  )
}

function Reading({ label, value }: { label: string; value: string }) {
  return (
    <span className="block">
      <span className="block text-xs opacity-75">{label}</span>
      <span className="block font-semibold tabular-nums">{value}</span>
    </span>
  )
}

export const RouteCard = memo(function RouteCard({
  route,
  isRecommended,
  isSelected,
  onSelect,
}: RouteCardProps) {
  const { summary } = route
  return (
    <button
      type="button"
      aria-pressed={isSelected}
      onClick={() => onSelect(route.id)}
      className={cn(
        'block w-full px-4 py-3.5 text-left focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-amber',
        isRecommended
          ? // Styled as a highway guide sign, with its inset white keyline.
            'rounded-lg bg-sign-green text-white outline-2 -outline-offset-[5px] outline-white'
          : 'rounded-md border border-transparent hover:bg-white',
        !isRecommended && isSelected && 'border-asphalt/30 bg-white',
        isRecommended && isSelected && 'ring-3 ring-amber',
      )}
    >
      <span className="flex items-baseline justify-between gap-3 px-1">
        <span className="text-lg font-bold">Route {route.rank}</span>
        {isRecommended ? (
          <span className="text-sm font-semibold">Recommended</span>
        ) : null}
      </span>

      <span className="mt-1 flex gap-4 px-1 text-sm">
        <span className="font-semibold tabular-nums">
          {formatMiles(summary.distance_miles)}
        </span>
        <span className="font-semibold tabular-nums">
          {formatDuration(summary.duration_seconds)}
        </span>
      </span>

      <span className="mt-2.5 block px-1">
        <StripMap route={route} />
      </span>

      <span className="mt-2.5 grid grid-cols-3 gap-x-3 gap-y-2 px-1 text-sm">
        <Reading label="Severe" value={formatMiles(summary.severe_miles)} />
        <Reading label="High" value={formatMiles(summary.high_miles)} />
        <Reading
          label="Average risk"
          value={
            summary.average_risk === null
              ? 'Unavailable'
              : String(summary.average_risk)
          }
        />
        {summary.no_travel_miles > 0 ? (
          <Reading
            label="No Travel"
            value={formatMiles(summary.no_travel_miles)}
          />
        ) : null}
        {summary.unknown_miles > 0 ? (
          <Reading
            label="No weather"
            value={formatMiles(summary.unknown_miles)}
          />
        ) : null}
      </span>

      <span className="mt-2.5 block px-1 text-sm">
        Arrives {formatEta(summary.arrival_at)}
      </span>
      <span className="mt-1 mb-0.5 block px-1 text-sm opacity-85">
        {route.rationale}
      </span>
    </button>
  )
})
