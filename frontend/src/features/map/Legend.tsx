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
      className="material absolute inset-x-3 top-3 z-10 flex [scrollbar-width:none] gap-x-3 gap-y-0.5 overflow-x-auto rounded-2xl px-3 py-2 text-xs whitespace-nowrap lg:right-auto lg:left-[27.5rem] lg:max-w-[calc(100%-32rem)] lg:flex-wrap lg:overflow-visible lg:py-1.5"
    >
      {LEVELS.map((risk) => (
        <li key={risk}>
          <RiskLabel risk={risk} />
        </li>
      ))}
    </ul>
  )
}
