import type { CircleLayerSpecification } from 'maplibre-gl'
import { memo, useEffect, useMemo } from 'react'
import { Layer, Source, useMap } from 'react-map-gl/maplibre'

import type { HeatmapResponse } from '@/api/client'
import { forecastStore } from '@/features/forecast/forecastStore'

import { heatmapColor, heatmapToGeoJson } from './heatmapExpression'

const HEAT_LAYER = 'corridor-heat'
const UNDER_ROUTES = 'route-casing'

export const HeatmapLayer = memo(function HeatmapLayer({
  data,
}: {
  data: HeatmapResponse
}) {
  const { current: map } = useMap()

  // All 49 hours are in the data once, so a slider move never sends anything to the map again.
  const geojson = useMemo(() => heatmapToGeoJson(data), [data])
  const paint = useMemo(
    () => ({
      'circle-color': heatmapColor(forecastStore.get()),
      'circle-blur': 1,
      // Roughly a constant distance on the ground, so shading doesn't change as you zoom.
      'circle-radius': [
        'interpolate',
        ['exponential', 2],
        ['zoom'],
        3,
        10,
        5,
        24,
        9,
        260,
      ],
    }),
    // Later hours go straight to the map below, so this keeps the hour it first drew with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data],
  ) as CircleLayerSpecification['paint']

  useEffect(() => {
    let frame: number | null = null
    const unsubscribe = forecastStore.subscribe(() => {
      if (frame !== null) return
      // A drag can fire many changes per frame, and only the latest can be seen.
      frame = requestAnimationFrame(() => {
        frame = null
        const instance = map?.getMap()
        if (instance?.getLayer(HEAT_LAYER)) {
          instance.setPaintProperty(
            HEAT_LAYER,
            'circle-color',
            heatmapColor(forecastStore.get()),
          )
        }
      })
    })
    return () => {
      unsubscribe()
      if (frame !== null) cancelAnimationFrame(frame)
    }
  }, [map])

  return (
    <Source id="corridor" type="geojson" data={geojson}>
      <Layer
        id={HEAT_LAYER}
        type="circle"
        paint={paint}
        beforeId={UNDER_ROUTES}
      />
    </Source>
  )
})
