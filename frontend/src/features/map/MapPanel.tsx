import 'maplibre-gl/dist/maplibre-gl.css'

import {
  setWorkerUrl,
  type MapGeoJSONFeature,
  type StyleSpecification,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import {
  Map as MapView,
  Marker,
  NavigationControl,
  Popup,
  type MapLayerMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre'

import type { HeatmapResponse, PlanResponse } from '@/api/client'
import { cn } from '@/lib/utils'

import {
  CHECKPOINT_LAYER,
  planBounds,
  ROUTE_HIT_LAYER,
  routeLabelPositions,
} from './buildGeoJson'
import { CheckpointLayer } from './CheckpointLayer'
import { CheckpointPopup } from './CheckpointPopup'
import { HeatmapLayer } from './HeatmapLayer'
import { Legend } from './Legend'
import { RouteLayers } from './RouteLayers'

// MapLibre looks for its worker beside its own script, where the bundler doesn't put it.
setWorkerUrl(workerUrl)

const BASE_MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'
// Routes can only be drawn once a style has loaded, so this stands in if the base map's style fails.
const BLANK_MAP_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': '#eef0ec' },
    },
  ],
}
const CONTINENTAL_US = { longitude: -98, latitude: 39, zoom: 3.4 }
const MAP_STYLE = { width: '100%', height: '100%' }
const ATTRIBUTION = {
  compact: true,
  customAttribution:
    '<a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Weather data by Open-Meteo.com</a> (<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>)',
}
const FIT_PADDING = 60
// Room for the forecast panel, which floats over the bottom of the map on a wide screen.
const WIDE_SCREEN_FIT_PADDING = { top: 60, left: 60, right: 60, bottom: 190 }
const FIT_MAX_ZOOM = 11
const PHONE_POPUP_OFFSET_SHARE = 0.35
const ANIMATION_MS = 700
const INTERACTIVE_LAYERS = [CHECKPOINT_LAYER, ROUTE_HIT_LAYER]

function animationMs(): number {
  const reduceMotion =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  return reduceMotion ? 0 : ANIMATION_MS
}

function isNarrowScreen(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    !window.matchMedia('(min-width: 1024px)').matches
  )
}

function fitPadding() {
  return isNarrowScreen() ? FIT_PADDING : WIDE_SCREEN_FIT_PADDING
}

function layerOf(feature: MapGeoJSONFeature, layerId: string): boolean {
  return feature.layer.id === layerId
}

interface MapPanelProps {
  plan: PlanResponse | undefined
  heatmap?: HeatmapResponse
  selectedRouteId: string | null
  selectedCheckpointId: string | null
  onSelectRoute: (routeId: string) => void
  onSelectCheckpoint: (routeId: string, checkpointId: string | null) => void
}

function MapPanel({
  plan,
  heatmap,
  selectedRouteId,
  selectedCheckpointId,
  onSelectRoute,
  onSelectCheckpoint,
}: MapPanelProps) {
  const mapRef = useRef<MapRef>(null)
  const [isLoaded, setIsLoaded] = useState(false)
  const [baseMapFailed, setBaseMapFailed] = useState(false)

  const labels = useMemo(() => (plan ? routeLabelPositions(plan) : []), [plan])
  const selectedCheckpoint = useMemo(
    () =>
      plan?.routes
        .find((route) => route.id === selectedRouteId)
        ?.checkpoints.find(
          (checkpoint) => checkpoint.id === selectedCheckpointId,
        ) ?? null,
    [plan, selectedRouteId, selectedCheckpointId],
  )

  useEffect(() => {
    const bounds = plan ? planBounds(plan) : null
    if (!isLoaded || !bounds) return
    mapRef.current?.fitBounds(bounds, {
      padding: fitPadding(),
      maxZoom: FIT_MAX_ZOOM,
      duration: animationMs(),
    })
  }, [plan, isLoaded])

  useEffect(() => {
    const map = mapRef.current
    if (!isLoaded || !map || !selectedCheckpoint) return
    const center: [number, number] = [
      selectedCheckpoint.lon,
      selectedCheckpoint.lat,
    ]
    if (isNarrowScreen()) {
      // The map is short on a phone, so put the point low enough for its popup to fit above it.
      const offset: [number, number] = [
        0,
        map.getContainer().clientHeight * PHONE_POPUP_OFFSET_SHARE,
      ]
      map.easeTo({ center, offset, duration: animationMs() })
    } else if (!map.getBounds().contains(center)) {
      map.easeTo({ center, duration: animationMs() })
    }
  }, [selectedCheckpoint, isLoaded])

  function handleClick(event: MapLayerMouseEvent) {
    const features = event.features ?? []
    const checkpoint = features.find((f) => layerOf(f, CHECKPOINT_LAYER))
    if (checkpoint) {
      const { route_id: routeId, id } = checkpoint.properties
      onSelectCheckpoint(routeId, id)
      return
    }
    const route = features.find((f) => layerOf(f, ROUTE_HIT_LAYER))
    if (route) onSelectRoute(route.properties.route_id)
  }

  return (
    <div className="relative size-full">
      <MapView
        ref={mapRef}
        initialViewState={CONTINENTAL_US}
        mapStyle={baseMapFailed ? BLANK_MAP_STYLE : BASE_MAP_STYLE}
        style={MAP_STYLE}
        attributionControl={ATTRIBUTION}
        interactiveLayerIds={plan ? INTERACTIVE_LAYERS : []}
        onLoad={() => setIsLoaded(true)}
        onError={(event) => {
          // A failed tile only leaves a gap. With no style, nothing can be drawn at all.
          if (!event.target.getStyle()?.layers?.length) setBaseMapFailed(true)
        }}
        onClick={handleClick}
        onMouseEnter={(event) => {
          event.target.getCanvas().style.cursor = 'pointer'
        }}
        onMouseLeave={(event) => {
          event.target.getCanvas().style.cursor = ''
        }}
      >
        <NavigationControl position="top-right" showCompass={false} />
        {plan ? (
          <>
            <RouteLayers plan={plan} selectedRouteId={selectedRouteId} />
            <CheckpointLayer
              plan={plan}
              selectedRouteId={selectedRouteId}
              selectedCheckpointId={selectedCheckpointId}
            />
            {heatmap ? <HeatmapLayer data={heatmap} /> : null}
          </>
        ) : null}
        {labels.map(({ route, lon, lat }) => {
          const isRecommended = route.id === plan?.recommended_route_id
          return (
            <Marker
              key={route.id}
              longitude={lon}
              latitude={lat}
              anchor="bottom"
            >
              <button
                type="button"
                aria-label={`Select route ${route.rank}`}
                onClick={() => onSelectRoute(route.id)}
                className={cn(
                  'rounded-sm px-1.5 py-0.5 text-xs font-bold whitespace-nowrap shadow-sm focus-visible:outline-3 focus-visible:outline-amber',
                  isRecommended
                    ? 'bg-sign-green text-white'
                    : 'bg-white text-asphalt',
                  route.id === selectedRouteId && 'ring-2 ring-amber',
                )}
              >
                Route {route.rank}
              </button>
            </Marker>
          )
        })}
        {selectedCheckpoint && selectedRouteId ? (
          <Popup
            longitude={selectedCheckpoint.lon}
            latitude={selectedCheckpoint.lat}
            anchor="bottom"
            offset={10}
            closeOnClick={false}
            maxWidth="20rem"
            onClose={() => onSelectCheckpoint(selectedRouteId, null)}
          >
            <CheckpointPopup checkpoint={selectedCheckpoint} />
          </Popup>
        ) : null}
      </MapView>
      <Legend />
      {baseMapFailed ? (
        <p
          role="status"
          className="absolute bottom-2 left-2 z-10 rounded-md bg-white/95 px-2.5 py-1.5 text-xs shadow-sm"
        >
          The background map could not load. Routes and checkpoints still show.
        </p>
      ) : null}
    </div>
  )
}

export default memo(MapPanel)
