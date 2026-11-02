import { ChevronUp } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'

import type { PlanRequest } from '@/api/client'
import { useHeatmap, usePlanTrip } from '@/api/queries'
import { DataCredit } from '@/components/DataCredit'
import { ForecastSlider } from '@/features/forecast/ForecastSlider'
import { forecastStore } from '@/features/forecast/forecastStore'
import { Hero } from '@/features/hero/Hero'
import { MapErrorBoundary } from '@/features/map/MapErrorBoundary'
import { useBottomSheet } from '@/features/sheet/useBottomSheet'
import { Alerts } from '@/features/trip/Alerts'
import { CheckpointDetails } from '@/features/trip/CheckpointDetails'
import { RouteList } from '@/features/trip/RouteList'
import { TripForm } from '@/features/trip/TripForm'

// MapLibre is most of the bundle, so the form appears before it finishes loading.
const MapPanel = lazy(() => import('@/features/map/MapPanel'))

function App() {
  const planTrip = usePlanTrip()
  const [chosenRouteId, setChosenRouteId] = useState<string | null>(null)
  const [chosenCheckpointId, setChosenCheckpointId] = useState<string | null>(
    null,
  )

  const plan = planTrip.data
  const request = planTrip.variables
  // Routes show as soon as they're ready. The heatmap follows, and can fail on its own.
  const heatmap = useHeatmap(plan, request)
  const selectedRouteId =
    chosenRouteId ?? plan?.recommended_route_id ?? plan?.routes[0]?.id ?? null
  const selectedRoute = plan?.routes.find(
    (route) => route.id === selectedRouteId,
  )

  const {
    sheetRef,
    contentRef,
    snapTo,
    onHandleClick,
    onContentFocus,
    onPointerDown,
    onPointerMove,
    onPointerEnd,
  } = useBottomSheet()
  const resultsRef = useRef<HTMLDivElement>(null)

  // New results take over on a phone: part of the map, and the recommendation right below it.
  useEffect(() => {
    if (!plan) return
    snapTo('half')
    const content = contentRef.current
    if (content && resultsRef.current) {
      content.scrollTop = resultsRef.current.offsetTop - content.offsetTop
    }
  }, [plan, snapTo, contentRef])

  function submit(newRequest: PlanRequest) {
    // Route ids repeat between plans, so a previous choice must not carry over.
    setChosenRouteId(null)
    setChosenCheckpointId(null)
    forecastStore.set(0)
    planTrip.mutate(newRequest)
  }

  function retry() {
    if (request) submit(request)
  }

  const selectRoute = useCallback((routeId: string) => {
    setChosenRouteId(routeId)
    setChosenCheckpointId(null)
  }, [])

  const selectCheckpointOnMap = useCallback(
    (routeId: string, checkpointId: string | null) => {
      setChosenRouteId(routeId)
      setChosenCheckpointId(checkpointId)
      // Clears the way for the popup. Pulling the sheet back up returns to the list.
      if (checkpointId) snapTo('peek')
    },
    [snapTo],
  )

  const toggleCheckpointInList = useCallback(
    (checkpointId: string) => {
      const opening = checkpointId !== chosenCheckpointId
      setChosenCheckpointId(opening ? checkpointId : null)
      if (opening) snapTo('peek')
    },
    [chosenCheckpointId, snapTo],
  )

  return (
    <>
      <Hero />
      <section
        id="plan"
        aria-label="Route planner"
        className="relative z-10 h-dvh snap-start overflow-hidden bg-concrete shadow-[0_-24px_60px_rgb(0_0_0/0.45)]"
      >
        {/* On a phone this is a sheet over a full-screen map. On a wide screen, a floating panel. */}
        <aside
          ref={sheetRef}
          className="material absolute inset-x-0 top-0 z-20 flex h-full flex-col rounded-t-3xl will-change-transform max-lg:bg-white/95 lg:inset-x-auto lg:inset-y-3 lg:left-3 lg:h-auto lg:w-[26rem] lg:rounded-3xl lg:will-change-auto"
        >
          <div
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerEnd}
            onPointerCancel={onPointerEnd}
            className="shrink-0 touch-none px-4 pb-2 lg:touch-auto lg:px-5 lg:pt-5 lg:pb-0"
          >
            <button
              type="button"
              aria-label="Resize the panel"
              onClick={onHandleClick}
              className="mx-auto flex h-6 w-full items-center justify-center focus-visible:outline-2 focus-visible:outline-action lg:hidden"
            >
              <span
                aria-hidden
                className="h-1.5 w-10 rounded-full bg-asphalt/25"
              />
            </button>
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-2xl leading-tight font-semibold">
                Plan a trip
              </h2>
              <a
                href="#top"
                aria-label="Back to the introduction"
                className="pressable flex size-11 items-center justify-center rounded-full bg-asphalt/5 hover:bg-asphalt/10 focus-visible:outline-2 focus-visible:outline-action lg:size-8"
              >
                <ChevronUp aria-hidden className="size-4" />
              </a>
            </div>
          </div>
          <div
            ref={contentRef}
            onFocus={onContentFocus}
            className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-4 pt-2 pb-4 lg:px-5 lg:pb-5"
          >
            <DataCredit />
            <TripForm
              onSubmit={submit}
              isPending={planTrip.isPending}
              error={planTrip.error}
            />
            <Alerts
              plan={plan}
              error={planTrip.error}
              isPending={planTrip.isPending}
              onRetry={retry}
            />
            {plan ? (
              <div ref={resultsRef} className="scroll-mt-2">
                <RouteList
                  plan={plan}
                  selectedRouteId={selectedRouteId}
                  onSelect={selectRoute}
                />
              </div>
            ) : null}
            {selectedRoute ? (
              <section>
                <h2 className="mb-1.5 px-2 text-base font-semibold">
                  Checkpoints on route {selectedRoute.rank}
                </h2>
                <CheckpointDetails
                  route={selectedRoute}
                  selectedCheckpointId={chosenCheckpointId}
                  onSelect={toggleCheckpointInList}
                />
              </section>
            ) : null}
          </div>
        </aside>
        <main className="absolute inset-0 z-0 flex flex-col bg-white">
          <div className="relative flex min-h-0 flex-1 items-center justify-center bg-asphalt/5">
            <MapErrorBoundary>
              <Suspense
                fallback={<p className="text-asphalt/70">Loading the map</p>}
              >
                <MapPanel
                  plan={plan}
                  heatmap={heatmap.data}
                  selectedRouteId={selectedRouteId}
                  selectedCheckpointId={chosenCheckpointId}
                  onSelectRoute={selectRoute}
                  onSelectCheckpoint={selectCheckpointOnMap}
                />
              </Suspense>
            </MapErrorBoundary>
            {plan ? null : (
              <p className="pointer-events-none material absolute right-0 bottom-10 left-[27.5rem] mx-auto hidden w-fit max-w-[90%] rounded-full px-4 py-2 text-center text-sm lg:block">
                Enter a trip to compare three routes by weather risk.
              </p>
            )}
          </div>
          {plan && request ? (
            <ForecastSlider
              departureAt={request.departure_at}
              data={heatmap.data}
              isLoading={heatmap.isLoading}
              error={heatmap.error}
              onRetry={() => void heatmap.refetch()}
            />
          ) : null}
        </main>
      </section>
    </>
  )
}

export default App
