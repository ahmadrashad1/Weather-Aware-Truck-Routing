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
      className="material absolute top-3 left-3 z-10 flex max-w-[calc(100%-4.5rem)] flex-wrap gap-x-3 gap-y-0.5 rounded-2xl px-3 py-1.5 text-xs lg:left-[27.5rem] lg:max-w-[calc(100%-32rem)]"
    >
      {LEVELS.map((risk) => (
        <li key={risk}>
          <RiskLabel risk={risk} />
        </li>
      ))}
    </ul>
  )
}
