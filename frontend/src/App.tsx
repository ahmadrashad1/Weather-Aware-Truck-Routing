import { lazy, Suspense, useCallback, useState } from 'react'

import type { PlanRequest } from '@/api/client'
import { useHeatmap, usePlanTrip } from '@/api/queries'
import { DataCredit } from '@/components/DataCredit'
import { ForecastSlider } from '@/features/forecast/ForecastSlider'
import { forecastStore } from '@/features/forecast/forecastStore'
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
    <div className="flex min-h-dvh flex-col lg:h-dvh lg:flex-row">
      <aside className="flex flex-col gap-4 bg-concrete p-4 lg:w-[26rem] lg:shrink-0 lg:overflow-y-auto">
        <h1 className="text-2xl leading-tight font-bold">
          Weather-Aware Truck Routing
        </h1>
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
            <h2 className="mb-1.5 px-2 text-base font-bold">
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
      <main className="sticky top-0 z-30 order-first flex flex-col bg-white lg:relative lg:top-auto lg:order-none lg:h-auto lg:min-h-0 lg:flex-1">
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
            <p className="pointer-events-none absolute right-0 bottom-20 left-0 lg:bottom-8 mx-auto w-fit max-w-[90%] rounded-md bg-white/95 px-3 py-1.5 text-center text-sm shadow-sm">
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
    </div>
  )
}

export default App
