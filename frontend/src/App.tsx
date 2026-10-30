import { useState } from 'react'

import type { PlanRequest } from '@/api/client'
import { usePlanTrip } from '@/api/queries'
import { Alerts } from '@/features/trip/Alerts'
import { CheckpointDetails } from '@/features/trip/CheckpointDetails'
import { RouteList } from '@/features/trip/RouteList'
import { TripForm } from '@/features/trip/TripForm'

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
            onSelect={(routeId) => {
              setChosenRouteId(routeId)
              setChosenCheckpointId(null)
            }}
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
              onSelect={setChosenCheckpointId}
            />
          </section>
        ) : null}
      </aside>
      <main className="flex min-h-[50dvh] flex-1 items-center justify-center bg-asphalt/5 p-6 text-center">
        {plan ? null : (
          <p className="max-w-sm text-asphalt/70">
            Enter a trip to compare three routes by weather risk.
          </p>
        )}
      </main>
    </div>
  )
}

export default App
