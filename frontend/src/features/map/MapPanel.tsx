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
import { formatDuration, formatMiles } from '@/lib/format'
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
import { HALF_TOP_SHARE } from '@/features/sheet/sheetPhysics'

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
// Room for the legend and forecast above, and the half-open sheet below.
const PHONE_POPUP_OFFSET_SHARE = 0.2
const PHONE_FIT_SIDE = 40
const PHONE_FIT_TOP = 175
const PHONE_FIT_ABOVE_SHEET = 24
// Room for the planner and forecast panels, which float over the map on a wide screen.
const WIDE_SCREEN_FIT_PADDING = { top: 70, left: 480, right: 60, bottom: 190 }
const FIT_MAX_ZOOM = 11
const ANIMATION_MS = 700
const FULLY_IN_VIEW = 0.95
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
  if (!isNarrowScreen()) return WIDE_SCREEN_FIT_PADDING
  return {
    top: PHONE_FIT_TOP,
    left: PHONE_FIT_SIDE,
    right: PHONE_FIT_SIDE,
    bottom:
      Math.round(window.innerHeight * (1 - HALF_TOP_SHARE)) +
      PHONE_FIT_ABOVE_SHEET,
  }
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
      // The sheet lowers for a selection, so put the point low enough for its popup to clear the
      // forecast panel above it.
      const offset: [number, number] = [
        0,
        map.getContainer().clientHeight * PHONE_POPUP_OFFSET_SHARE,
      ]
      map.easeTo({ center, offset, duration: animationMs() })
    } else if (!map.getBounds().contains(center)) {
      map.easeTo({ center, duration: animationMs() })
    }
  }, [selectedCheckpoint, isLoaded])

  // Until the map is fully in view, the wheel scrolls the page, or a map rising under the pointer
  // would capture the scroll and start zooming halfway up the screen.
  useEffect(() => {
    const map = mapRef.current
    if (!isLoaded || !map || typeof IntersectionObserver !== 'function') return
    const { scrollZoom } = map.getMap()
    scrollZoom.disable()
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.intersectionRatio >= FULLY_IN_VIEW) scrollZoom.enable()
        else scrollZoom.disable()
      },
      { threshold: [FULLY_IN_VIEW] },
    )
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [isLoaded])

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
        // Off from the start, or a map that's still loading would capture the page's scroll.
        scrollZoom={false}
        interactiveLayerIds={plan ? INTERACTIVE_LAYERS : []}
        onLoad={(event) => {
          setIsLoaded(true)
          // The credit starts open, and on a phone that would cover much of the map.
          if (isNarrowScreen()) {
            event.target
              .getContainer()
              .querySelector('.maplibregl-ctrl-attrib')
              ?.classList.remove('maplibregl-compact-show')
          }
        }}
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
          const isSelected = route.id === selectedRouteId
          const { summary } = route
          const distanceAndTime = `${formatMiles(summary.distance_miles)}, ${formatDuration(summary.duration_seconds)}`
          return (
            <Marker
              key={route.id}
              longitude={lon}
              latitude={lat}
              anchor="bottom"
              style={{ zIndex: isSelected ? 1 : 0 }}
            >
              <button
                type="button"
                aria-label={`Select route ${route.rank}: ${distanceAndTime}`}
                onClick={() => onSelectRoute(route.id)}
                className={cn(
                  'pressable rounded-xl px-2.5 py-1 text-left text-xs whitespace-nowrap shadow-sm focus-visible:outline-3 focus-visible:outline-action',
                  isRecommended
                    ? 'bg-action text-white'
                    : 'bg-white text-asphalt',
                  isSelected && 'ring-2 ring-asphalt',
                )}
              >
                <span className="block font-semibold">Route {route.rank}</span>
                <span className="block tabular-nums">{distanceAndTime}</span>
                {isSelected ? (
                  // On a phone these numbers are right below, in the sheet, and the map has less room.
                  <span className="hidden tabular-nums lg:block">
                    Severe {formatMiles(summary.severe_miles)}, High{' '}
                    {formatMiles(summary.high_miles)}
                    <br />
                    Average risk{' '}
                    {summary.average_risk === null
                      ? 'unavailable'
                      : summary.average_risk}
                    {summary.no_travel_miles > 0 ? (
                      <>
                        <br />
                        No Travel {formatMiles(summary.no_travel_miles)}
                      </>
                    ) : null}
                    {summary.unknown_miles > 0 ? (
                      <>
                        <br />
                        No weather {formatMiles(summary.unknown_miles)}
                      </>
                    ) : null}
                  </span>
                ) : null}
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
          className="material absolute top-14 left-3 z-10 rounded-2xl px-3 py-1.5 text-xs lg:top-auto lg:bottom-3 lg:left-[27.5rem]"
        >
          The background map could not load. Routes and checkpoints still show.
        </p>
      ) : null}
    </div>
  )
}

export default memo(MapPanel)
