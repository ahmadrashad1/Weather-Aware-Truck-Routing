import type { PlanResponse } from '@/api/client'

import { RouteCard } from './RouteCard'

interface RouteListProps {
  plan: PlanResponse
  selectedRouteId: string | null
  onSelect: (routeId: string) => void
}

export function RouteList({ plan, selectedRouteId, onSelect }: RouteListProps) {
  return (
    <ol className="grid gap-1.5">
      {plan.routes.map((route) => (
        <li key={route.id}>
          <RouteCard
            route={route}
            isRecommended={route.id === plan.recommended_route_id}
            isSelected={route.id === selectedRouteId}
            onSelect={onSelect}
          />
        </li>
      ))}
    </ol>
  )
}
