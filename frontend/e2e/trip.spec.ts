import {
  expect,
  fillTrip,
  planTrip,
  routeCard,
  settledMap,
  stubApi,
  test,
} from './fixtures/app.ts'
import { DALLAS, DENVER } from './fixtures/data.ts'

test.beforeEach(async ({ page }) => {
  await stubApi(page)
  await page.goto('/')
})

test('submits the trip the user entered', async ({ page }) => {
  await fillTrip(page, '62000')
  await page.getByText('10 mi', { exact: true }).click()
  const request = page.waitForRequest('**/api/v1/trips/plan')
  await page.getByRole('button', { name: 'Plan routes' }).click()

  const body = (await request).postDataJSON()
  expect(body.origin).toEqual(DALLAS)
  expect(body.destination).toEqual(DENVER)
  expect(body.load_lb).toBe(62000)
  expect(body.interval_miles).toBe(10)
  expect(body.departure_at).toMatch(/[+-]\d{2}:\d{2}$/)
})

test('will not submit without a load weight', async ({ page }) => {
  await page.getByRole('combobox', { name: 'Origin' }).pressSequentially('Dal')
  await page.getByRole('option', { name: 'Dallas, TX' }).click()
  await page.getByRole('button', { name: 'Plan routes' }).click()
  await expect(page.getByText('Enter the load weight.')).toBeVisible()
  await expect(page.getByRole('slider')).toHaveCount(0)
})

test('shows three ranked routes with one recommended', async ({ page }) => {
  await planTrip(page)

  const cards = page.locator('ol button')
  await expect(cards).toHaveCount(3)
  await expect(cards.nth(0)).toContainText('Route 1')
  await expect(cards.nth(1)).toContainText('Route 2')
  await expect(cards.nth(2)).toContainText('Route 3')
  await expect(
    page.locator('ol').getByText('Recommended', { exact: true }),
  ).toHaveCount(1)
  await expect(cards.nth(0)).toContainText('Recommended')
  await expect(cards.nth(0)).toHaveAttribute('aria-pressed', 'true')
  await expect(cards.nth(1)).toContainText('Severe')
  await expect(cards.nth(2)).toContainText('No Travel')
})

test('draws the routes on the map', async ({ page }) => {
  const empty = await settledMap(page)
  await planTrip(page)
  await expect(page.getByRole('slider')).toBeVisible()
  const withRoutes = await settledMap(page)
  expect(withRoutes.equals(empty)).toBe(false)

  await expect(
    page.getByRole('button', { name: 'Select route 3' }),
  ).toBeVisible()
})

test('choosing a route redraws the map and lists its checkpoints', async ({
  page,
}) => {
  await planTrip(page)
  await expect(page.getByRole('slider')).toBeVisible()
  const before = await settledMap(page)

  await routeCard(page, /Route 2/).click()

  await expect(routeCard(page, /Route 2/)).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(
    page.getByRole('heading', { name: 'Checkpoints on route 2' }),
  ).toBeVisible()
  expect((await settledMap(page)).equals(before)).toBe(false)
})

test('a route label on the map selects its route', async ({ page }) => {
  await planTrip(page)
  await page.getByRole('button', { name: 'Select route 2' }).click()
  await expect(routeCard(page, /Route 2/)).toHaveAttribute(
    'aria-pressed',
    'true',
  )
})

test('a checkpoint opens from the list and from the map itself', async ({
  page,
}) => {
  await planTrip(page)
  await routeCard(page, /Route 2/).click()

  const rows = page
    .getByRole('list', { name: 'Checkpoints' })
    .getByRole('button')
  await rows.nth(1).click()
  const popup = page.locator('.maplibregl-popup')
  await expect(popup).toContainText('Mile 200')
  await expect(popup).toContainText('Arrives')
  await expect(popup).toContainText('38.2 mph')
  await expect(popup).toContainText('Severe')
  await expect(popup).toContainText('raised because of the load')

  // Close it, then click the map where it was. Only a real hit on the point reopens it.
  const tip = await page.locator('.maplibregl-popup-tip').boundingBox()
  await page.locator('.maplibregl-popup-close-button').click()
  await expect(popup).toHaveCount(0)
  await page.mouse.click(tip!.x + tip!.width / 2, tip!.y + tip!.height + 10)
  await expect(popup).toContainText('Mile 200')
})

test('an unknown checkpoint says so instead of showing zeros', async ({
  page,
}) => {
  await planTrip(page)
  await routeCard(page, /Route 3/).click()
  await page
    .getByRole('list', { name: 'Checkpoints' })
    .getByRole('button')
    .nth(2)
    .click()
  const popup = page.locator('.maplibregl-popup')
  await expect(popup).toContainText('Weather is unavailable')
  await expect(popup).not.toContainText('mph')
})
