import type { Checkpoint, RiskCode, Route } from '@/api/client'
import { formatEta, formatMileMarker } from '@/lib/format'
import { RISK_DISPLAY } from '@/lib/risk'
import { cn } from '@/lib/utils'

export function RiskLabel({ risk }: { risk: RiskCode }) {
  const { label, color } = RISK_DISPLAY[risk]
  return (
    <span className="inline-flex items-center gap-1.5 font-medium">
      <span
        aria-hidden
        className="size-2.5 shrink-0 rounded-[2px]"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  )
}

function ConditionRow({
  label,
  reading,
  risk,
}: {
  label: string
  reading: string
  risk: RiskCode | null
}) {
  return (
    <>
      <dt className="text-asphalt/70">{label}</dt>
      <dd className="font-semibold tabular-nums">{reading}</dd>
      <dd>{risk ? <RiskLabel risk={risk} /> : null}</dd>
    </>
  )
}

export function CheckpointReadings({ checkpoint }: { checkpoint: Checkpoint }) {
  const { weather } = checkpoint
  if (!weather) {
    return (
      <p className="text-sm">Weather is unavailable for this checkpoint.</p>
    )
  }
  return (
    <>
      <dl className="grid grid-cols-[auto_auto_1fr] items-center gap-x-4 gap-y-1 text-sm">
        <ConditionRow
          label="Wind"
          reading={`${weather.wind_mph} mph`}
          risk={checkpoint.wind_risk}
        />
        <ConditionRow
          label="Rain"
          reading={`${weather.rain_in_hr} in/hr`}
          risk={checkpoint.rain_risk}
        />
        <ConditionRow
          label="Snow"
          reading={`${weather.snow_in_hr} in/hr`}
          risk={checkpoint.snow_risk}
        />
      </dl>
      {checkpoint.load_adjusted ? (
        <p className="mt-1.5 text-sm">
          Wind risk raised because of the load weight.
        </p>
      ) : null}
    </>
  )
}

interface CheckpointDetailsProps {
  route: Route
  selectedCheckpointId: string | null
  onSelect: (checkpointId: string) => void
}

export function CheckpointDetails({
  route,
  selectedCheckpointId,
  onSelect,
}: CheckpointDetailsProps) {
  return (
    <ul aria-label="Checkpoints" className="divide-y divide-asphalt/10">
      {route.checkpoints.map((checkpoint) => {
        const isSelected = checkpoint.id === selectedCheckpointId
        return (
          // Long trips list hundreds of rows, so skip rendering the ones out of view.
          <li
            key={checkpoint.id}
            className="[contain-intrinsic-size:auto_44px] [content-visibility:auto]"
          >
            <button
              type="button"
              aria-expanded={isSelected}
              onClick={() => onSelect(checkpoint.id)}
              className={cn(
                'flex w-full items-baseline justify-between gap-3 px-2 py-2 text-left text-sm hover:bg-white focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-action',
                isSelected && 'bg-white',
              )}
            >
              <span>
                <span className="block font-semibold">
                  {formatMileMarker(checkpoint.mile)}
                </span>
                <span className="block text-asphalt/70">
                  {formatEta(checkpoint.eta)}
                </span>
              </span>
              <RiskLabel risk={checkpoint.risk} />
            </button>
            {isSelected ? (
              <div className="bg-white px-2 pb-3">
                <CheckpointReadings checkpoint={checkpoint} />
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}
