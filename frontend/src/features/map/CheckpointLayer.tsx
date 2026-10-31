import type { ExpressionSpecification } from 'maplibre-gl'
import { memo, useMemo } from 'react'
import { Layer, Source } from 'react-map-gl/maplibre'

import type { PlanResponse } from '@/api/client'

import {
  CHECKPOINT_LAYER,
  checkpointsToPoints,
  RISK_COLOR_EXPRESSION,
  selectedValue,
} from './buildGeoJson'

const ZOOMED_OUT = 3
const ZOOMED_IN = 8

function isSelectedCheckpoint(
  checkpointId: string | null,
  whenSelected: number,
  otherwise: number,
): ExpressionSpecification {
  return [
    'case',
    ['==', ['get', 'id'], checkpointId ?? ''],
    whenSelected,
    otherwise,
  ]
}

interface CheckpointLayerProps {
  plan: PlanResponse
  selectedRouteId: string | null
  selectedCheckpointId: string | null
}

export const CheckpointLayer = memo(function CheckpointLayer({
  plan,
  selectedRouteId,
  selectedCheckpointId,
}: CheckpointLayerProps) {
  // One source and data-driven paint, so a long trip's hundreds of points stay fast.
  const data = useMemo(() => checkpointsToPoints(plan), [plan])
  return (
    <Source id="checkpoints" type="geojson" data={data}>
      <Layer
        id={CHECKPOINT_LAYER}
        type="circle"
        paint={{
          'circle-color': RISK_COLOR_EXPRESSION,
          // Shrink when zoomed out, or a long trip's dots hide the risk colours on the line.
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            ZOOMED_OUT,
            selectedValue(selectedRouteId, 2, 1),
            ZOOMED_IN,
            selectedValue(selectedRouteId, 6, 3),
          ],
          'circle-opacity': selectedValue(selectedRouteId, 1, 0.5),
          'circle-stroke-color': '#1f2529',
          'circle-stroke-opacity': selectedValue(selectedRouteId, 1, 0.5),
          'circle-stroke-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            ZOOMED_OUT,
            isSelectedCheckpoint(selectedCheckpointId, 2.5, 0),
            ZOOMED_IN,
            isSelectedCheckpoint(selectedCheckpointId, 3, 1),
          ],
        }}
      />
    </Source>
  )
})
