import { ChevronUp } from 'lucide-react'
import { lazy, Suspense, useCallback, useState } from 'react'

import type { PlanRequest } from '@/api/client'
import { useHeatmap, usePlanTrip } from '@/api/queries'
import { DataCredit } from '@/components/DataCredit'
import { ForecastSlider } from '@/features/forecast/ForecastSlider'
import { forecastStore } from '@/features/forecast/forecastStore'
import { Hero } from '@/features/hero/Hero'
import { MapErrorBoundary } from '@/features/map/MapErrorBoundary'
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
    },
    [],
  )

  const toggleCheckpointInList = useCallback((checkpointId: string) => {
    setChosenCheckpointId((current) =>
      current === checkpointId ? null : checkpointId,
    )
  }, [])

  return (
    <>
      <Hero />
      <section
        id="plan"
        aria-label="Route planner"
        className="relative z-10 flex min-h-dvh snap-start flex-col bg-concrete shadow-[0_-24px_60px_rgb(0_0_0/0.45)] lg:block lg:h-dvh lg:overflow-hidden"
      >
        <aside className="flex flex-col gap-4 p-4 lg:absolute lg:inset-y-3 lg:left-3 lg:z-20 lg:w-[26rem] lg:overflow-y-auto lg:rounded-3xl lg:p-5 lg:material">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-2xl leading-tight font-semibold">
              Plan a trip
            </h2>
            <a
              href="#top"
              aria-label="Back to the introduction"
              className="pressable flex size-8 items-center justify-center rounded-full bg-asphalt/5 hover:bg-asphalt/10 focus-visible:outline-2 focus-visible:outline-action"
            >
              <ChevronUp aria-hidden className="size-4" />
            </a>
          </div>
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
            <RouteList
              plan={plan}
              selectedRouteId={selectedRouteId}
              onSelect={selectRoute}
            />
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
        </aside>
        {/* On a phone the map stays in view above the lists, so a selection shows straight away. */}
        <main className="sticky top-0 z-30 order-first flex flex-col bg-white lg:absolute lg:inset-0 lg:z-0">
          <div className="relative flex h-[36dvh] items-center justify-center bg-asphalt/5 lg:h-auto lg:min-h-0 lg:flex-1">
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
