import { lazy, Suspense, useCallback, useState } from 'react'

import type { PlanRequest } from '@/api/client'
import { usePlanTrip } from '@/api/queries'
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
  const selectedRouteId =
    chosenRouteId ?? plan?.recommended_route_id ?? plan?.routes[0]?.id ?? null
  const selectedRoute = plan?.routes.find(
    (route) => route.id === selectedRouteId,
  )

  function submit(request: PlanRequest) {
    // Route ids repeat between plans, so a previous choice must not carry over.
    setChosenRouteId(null)
    setChosenCheckpointId(null)
    planTrip.mutate(request)
  }

  function retry() {
    if (planTrip.variables) submit(planTrip.variables)
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
      <main className="sticky top-0 z-30 order-first flex h-[42dvh] items-center justify-center bg-asphalt/5 lg:static lg:order-none lg:h-auto lg:flex-1">
        <MapErrorBoundary>
          <Suspense
            fallback={<p className="text-asphalt/70">Loading the map</p>}
          >
            <MapPanel
              plan={plan}
              selectedRouteId={selectedRouteId}
              selectedCheckpointId={chosenCheckpointId}
              onSelectRoute={selectRoute}
              onSelectCheckpoint={selectCheckpointOnMap}
            />
          </Suspense>
        </MapErrorBoundary>
        {plan ? null : (
          <p className="pointer-events-none absolute right-0 bottom-8 left-0 mx-auto w-fit max-w-[90%] rounded-md bg-white/95 px-3 py-1.5 text-center text-sm shadow-sm">
            Enter a trip to compare three routes by weather risk.
          </p>
        )}
      </main>
    </div>
  )
}

export default App
