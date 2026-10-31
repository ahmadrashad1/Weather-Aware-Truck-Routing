import type { Checkpoint } from '@/api/client'
import {
  CheckpointReadings,
  RiskLabel,
} from '@/features/trip/CheckpointDetails'
import { formatEta, formatMileMarker } from '@/lib/format'

export function CheckpointPopup({ checkpoint }: { checkpoint: Checkpoint }) {
  return (
    <div className="grid min-w-52 gap-1.5 text-asphalt">
      <div className="flex items-baseline justify-between gap-4 pr-4">
        <h3 className="text-base font-bold">
          {formatMileMarker(checkpoint.mile)}
        </h3>
        <RiskLabel risk={checkpoint.risk} />
      </div>
      <p className="text-sm">Arrives {formatEta(checkpoint.eta)}</p>
      <CheckpointReadings checkpoint={checkpoint} />
    </div>
  )
}
