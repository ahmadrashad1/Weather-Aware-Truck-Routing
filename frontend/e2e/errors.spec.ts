import {
  expect,
  json,
  planTrip,
  routeCard,
  settledMap,
  stubApi,
  test,
} from './fixtures/app.ts'
import { heatmap, noSafeRoutePlan, plan } from './fixtures/data.ts'

// The browser logs every failed response as a console error, and these tests cause them on
// purpose. Only that expected message is removed: any other console error still fails the test.
function ignoreExpectedFailures(problems: string[]) {
  const expected =
    /Failed to load resource: the server responded with a status of/
  for (let index = problems.length - 1; index >= 0; index -= 1) {
    if (expected.test(problems[index])) problems.splice(index, 1)
  }
}

test('an outage explains itself and retries the same trip', async ({
  page,
  problems,
}) => {
  let attempts = 0
  await stubApi(page, {
    plan: (route) => {
      attempts += 1
      return attempts === 1
        ? json(
            {
              code: 'provider_unavailable',
              message: 'The routing or weather service is unavailable.',
            },
            503,
          )(route)
        : json(plan)(route)
    },
  })
  await page.goto('/')
  await planTrip(page)

  await expect(page.getByRole('alert')).toContainText('service is unavailable')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(routeCard(page, /Route 1/)).toBeVisible()
  expect(attempts).toBe(2)
  ignoreExpectedFailures(problems)
})

test('no road between two places is explained, with no pointless retry', async ({
  page,
  problems,
}) => {
  await stubApi(page, {
    plan: json(
      { code: 'no_route', message: 'No truck route connects these locations.' },
      422,
    ),
  })
  await page.goto('/')
  await planTrip(page)

  await expect(page.getByRole('alert')).toContainText('No truck route')
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(0)
  ignoreExpectedFailures(problems)
})

test('the API’s field errors appear beside the fields', async ({
  page,
  problems,
}) => {
  await stubApi(page, {
    plan: json(
      {
        code: 'validation_error',
        message: 'Please check the highlighted fields.',
        fields: { load_lb: ['Ensure this value is at most 80000.'] },
      },
      400,
    ),
  })
  await page.goto('/')
  await planTrip(page)

  await expect(
    page.getByText('Ensure this value is at most 80000.'),
  ).toBeVisible()
  ignoreExpectedFailures(problems)
})

test('every route blocked shows no recommendation, but still shows the routes', async ({
  page,
}) => {
  await stubApi(page, { plan: json(noSafeRoutePlan) })
  await page.goto('/')
  await planTrip(page)

  await expect(page.getByRole('alert')).toContainText('No safe route')
  await expect(page.locator('ol button')).toHaveCount(3)
  await expect(
    page.locator('ol').getByText('Recommended', { exact: true }),
  ).toHaveCount(0)
})

test('a partial weather outage shows its warning', async ({ page }) => {
  await stubApi(page, {
    plan: json({
      ...plan,
      warnings: ['Weather is unavailable for 200 of 800 miles on route 3.'],
    }),
  })
  await page.goto('/')
  await planTrip(page)
  await expect(
    page.getByText('Weather is unavailable for 200 of 800 miles on route 3.'),
  ).toBeVisible()
})

test('routes stay usable when only the heatmap fails, and it can retry', async ({
  page,
  problems,
}) => {
  let attempts = 0
  await stubApi(page, {
    heatmap: (route) => {
      attempts += 1
      return attempts === 1
        ? json(
            { code: 'rate_limited', message: 'Too many requests right now.' },
            429,
          )(route)
        : json(heatmap)(route)
    },
  })
  await page.goto('/')
  await planTrip(page)

  await expect(routeCard(page, /Route 1/)).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('Too many requests')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(
    page.getByRole('slider', { name: 'Forecast hour' }),
  ).toBeVisible()
  ignoreExpectedFailures(problems)
})

test('the corridor shows on a calm day, when every hour is Low', async ({
  page,
}) => {
  let release = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  await stubApi(page, {
    heatmap: async (route) => {
      await held
      await json({
        ...heatmap,
        risk: heatmap.risk.map((frames) => frames.map(() => 0)),
      })(route)
    },
  })
  await page.goto('/')
  await planTrip(page)
  await expect(routeCard(page, /Route 1/)).toBeVisible()
  const routesOnly = await settledMap(page)

  release()
  await expect(
    page.getByRole('slider', { name: 'Forecast hour' }),
  ).toBeVisible()
  const withHeatmap = await settledMap(page)
  expect(withHeatmap.equals(routesOnly)).toBe(false)
})

test('routes still draw when the base map fails to load', async ({
  page,
  problems,
}) => {
  await stubApi(page)
  await page.route('**/styles/**', (route) => route.abort())
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText(
    'background map could not load',
  )
  const empty = await settledMap(page)

  await planTrip(page)
  await expect(
    page.getByRole('slider', { name: 'Forecast hour' }),
  ).toBeVisible()
  const withRoutes = await settledMap(page)
  expect(withRoutes.equals(empty)).toBe(false)

  // The aborted request itself is logged, and that's expected here.
  const expected = /Failed to load resource|Failed to fetch/
  problems.splice(
    0,
    problems.length,
    ...problems.filter((problem) => !expected.test(problem)),
  )
})

test('routes appear before a slow heatmap finishes', async ({ page }) => {
  let release = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  await stubApi(page, {
    heatmap: async (route) => {
      await held
      await json(heatmap)(route)
    },
  })
  await page.goto('/')
  await planTrip(page)

  await expect(routeCard(page, /Route 1/)).toBeVisible()
  await expect(page.getByRole('status')).toContainText('Loading the forecast')
  release()
  await expect(
    page.getByRole('slider', { name: 'Forecast hour' }),
  ).toBeVisible()
})
