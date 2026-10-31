import { memo, useMemo } from 'react'
import { Layer, Source } from 'react-map-gl/maplibre'

import type { PlanResponse } from '@/api/client'

import {
  RISK_COLOR_EXPRESSION,
  ROUTE_HIT_LAYER,
  routesToSegments,
  selectedValue,
} from './buildGeoJson'

const LINE_LAYOUT = { 'line-cap': 'round', 'line-join': 'round' } as const

interface RouteLayersProps {
  plan: PlanResponse
  selectedRouteId: string | null
}

export const RouteLayers = memo(function RouteLayers({
  plan,
  selectedRouteId,
}: RouteLayersProps) {
  // Selection only changes paint values below, so this data is never re-sent to the map.
  const data = useMemo(() => routesToSegments(plan), [plan])
  const sortKey = selectedValue(selectedRouteId, 1, 0)
  return (
    <Source id="routes" type="geojson" data={data}>
      <Layer
        id="route-casing"
        type="line"
        layout={{ ...LINE_LAYOUT, 'line-sort-key': sortKey }}
        paint={{
          'line-color': '#ffffff',
          'line-width': selectedValue(selectedRouteId, 9, 5),
          'line-opacity': selectedValue(selectedRouteId, 1, 0.45),
        }}
      />
      <Layer
        id="route-lines"
        type="line"
        layout={{ ...LINE_LAYOUT, 'line-sort-key': sortKey }}
        paint={{
          'line-color': RISK_COLOR_EXPRESSION,
          'line-width': selectedValue(selectedRouteId, 6, 3),
          'line-opacity': selectedValue(selectedRouteId, 1, 0.45),
        }}
      />
      {/* An invisible, wider line makes a thin route easy to click. */}
      <Layer
        id={ROUTE_HIT_LAYER}
        type="line"
        paint={{ 'line-color': '#000000', 'line-width': 16, 'line-opacity': 0 }}
      />
    </Source>
  )
})
