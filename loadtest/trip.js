// Load test for the trip workflow. Point it only at a stack that uses loadtest/stub.py.
// See docs/load-testing.md.
import { check, sleep } from 'k6'
import http from 'k6/http'
import { Counter, Trend } from 'k6/metrics'

const BASE = __ENV.BASE_URL
const SCENARIO = __ENV.SCENARIO || 'normal'
// For example "10:5m,25:5m". Each pair is a target number of users and how long to hold it.
const PLAN = __ENV.STAGES || '10:5m'
const RAMP = __ENV.RAMP || '30s'

const stages = PLAN.split(',').flatMap((stage) => {
  const [target, hold] = stage.split(':')
  return [
    { target: Number(target), duration: RAMP },
    { target: Number(target), duration: hold },
  ]
})

const latency = {
  plan: new Trend('plan_ms', true),
  heatmap: new Trend('heatmap_ms', true),
  search: new Trend('search_ms', true),
}
const refused = new Counter('busy_or_refused')

export const options = {
  scenarios: { trips: { executor: 'ramping-vus', startVUs: 1, stages, gracefulRampDown: '180s', gracefulStop: '180s' } },
  thresholds: {
    // Stop once a stage is clearly past what the server can do.
    http_req_failed: [{ threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '2m' }],
    search_ms: [{ threshold: 'p(95)<5000', abortOnFail: true, delayAbortEval: '2m' }],
  },
  noConnectionReuse: false,
  summaryTrendStats: ['count', 'med', 'p(95)', 'p(99)', 'max'],
}

// Invented coordinates near each city. None of this came from a provider.
const CITIES = [
  [32.78, -96.8], [35.47, -97.52], [39.74, -104.99], [41.88, -87.63], [33.75, -84.39],
  [29.76, -95.37], [36.16, -86.78], [39.1, -94.58], [38.63, -90.2], [35.15, -90.05],
  [39.77, -86.16], [40.44, -80.0], [42.33, -83.05], [44.98, -93.27], [41.26, -95.94],
  [35.08, -106.65], [33.45, -112.07], [36.17, -115.14], [40.76, -111.89], [45.52, -122.68],
]
const COAST = [[40.71, -74.0], [34.05, -118.24]]
const HOT_TRIPS = [[0, 1], [0, 2], [3, 6], [3, 4], [7, 2], [8, 3]]

function jitter(value) {
  return value + (Math.random() - 0.5) * 0.8
}

function chooseTrip() {
  if (SCENARIO === 'long') return { from: COAST[0], to: COAST[1], interval: 10 }
  if (SCENARIO === 'overlap') {
    const [a, b] = HOT_TRIPS[Math.floor(Math.random() * HOT_TRIPS.length)]
    return { from: CITIES[a], to: CITIES[b], interval: 25 }
  }
  // A new trip each time, so the weather cache rarely helps. This is the costly case.
  const a = Math.floor(Math.random() * CITIES.length)
  const b = (a + 1 + Math.floor(Math.random() * (CITIES.length - 1))) % CITIES.length
  return {
    from: CITIES[a].map(jitter),
    to: CITIES[b].map(jitter),
    interval: [10, 25, 25, 50][Math.floor(Math.random() * 4)],
  }
}

function postJson(path, body, name) {
  return http.post(`${BASE}${path}`, JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '180s',
    tags: { name },
  })
}

export default function () {
  const search = http.get(`${BASE}/api/v1/geocode?q=Dal${__ITER % 50}`, { tags: { name: 'search' } })
  latency.search.add(search.timings.duration)
  check(search, { 'search answered': (r) => r.status === 200 })

  const trip = chooseTrip()
  const departure = new Date(Date.now() + 3 * 3600 * 1000).toISOString()
  const plan = postJson(
    '/api/v1/trips/plan',
    {
      origin: { label: 'A', lat: trip.from[0], lon: trip.from[1] },
      destination: { label: 'B', lat: trip.to[0], lon: trip.to[1] },
      departure_at: departure,
      load_lb: 45000,
      interval_miles: trip.interval,
    },
    'plan',
  )
  latency.plan.add(plan.timings.duration)
  if ([429, 503].includes(plan.status)) refused.add(1)
  const planned = check(plan, { 'plan answered': (r) => r.status === 200 })

  if (planned) {
    const heatmap = postJson(
      '/api/v1/trips/heatmap',
      {
        routes: plan.json('routes').map((route) => route.geometry.coordinates),
        departure_at: departure,
        load_lb: 45000,
      },
      'heatmap',
    )
    latency.heatmap.add(heatmap.timings.duration)
    if ([429, 503].includes(heatmap.status)) refused.add(1)
    check(heatmap, { 'heatmap answered': (r) => r.status === 200 })
  }

  // Someone reading the results before planning another trip.
  sleep(10 + Math.random() * 20)
}
