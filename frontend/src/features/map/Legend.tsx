import type { RiskCode } from '@/api/client'
import { RiskLabel } from '@/features/trip/CheckpointDetails'

const LEVELS: RiskCode[] = [
  'low',
  'moderate',
  'high',
  'severe',
  'no_travel',
  'unknown',
]

export function Legend() {
  return (
    <ul
      aria-label="Risk levels"
      className="absolute top-2 left-2 z-10 flex max-w-[calc(100%-4rem)] flex-wrap gap-x-3 gap-y-0.5 rounded-md bg-white/95 px-2.5 py-1.5 text-xs shadow-sm"
    >
      {LEVELS.map((risk) => (
        <li key={risk}>
          <RiskLabel risk={risk} />
        </li>
      ))}
    </ul>
  )
}
