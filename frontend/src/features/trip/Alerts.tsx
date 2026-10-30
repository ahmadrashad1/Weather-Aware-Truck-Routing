import { ApiError, type PlanResponse } from '@/api/client'
import { Button } from '@/components/ui/button'

const FORM_HANDLED_CODES = new Set(['validation_error'])
const NOT_RETRYABLE_CODES = new Set(['no_route'])

interface AlertsProps {
  plan?: PlanResponse
  error?: ApiError | null
  isPending: boolean
  onRetry: () => void
}

function Banner({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="alert"
      className="rounded-md border-l-4 border-risk-severe bg-white px-3 py-2.5 text-sm"
    >
      {children}
    </div>
  )
}

export function Alerts({ plan, error, isPending, onRetry }: AlertsProps) {
  if (isPending) {
    return (
      <p role="status" className="text-sm">
        Checking routes and weather. A long trip can take over a minute.
      </p>
    )
  }

  if (error && !FORM_HANDLED_CODES.has(error.code)) {
    return (
      <Banner>
        <p>{error.message}</p>
        {NOT_RETRYABLE_CODES.has(error.code) ? null : (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={onRetry}
          >
            Try again
          </Button>
        )}
      </Banner>
    )
  }

  if (!plan) return null

  return (
    <>
      {plan.no_safe_route ? (
        <Banner>
          <p className="font-semibold">No safe route</p>
          <p>
            Every route has No Travel miles at this departure time and load. Try
            a different departure time.
          </p>
        </Banner>
      ) : null}
      {!plan.no_safe_route && plan.recommended_route_id === null ? (
        <Banner>
          <p className="font-semibold">No route can be recommended</p>
          <p>
            There isn&apos;t enough weather data to compare these routes. Try
            again shortly.
          </p>
        </Banner>
      ) : null}
      {plan.warnings.length > 0 ? (
        <ul className="grid gap-1.5 rounded-md border-l-4 border-amber bg-white px-3 py-2.5 text-sm">
          {plan.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </>
  )
}
