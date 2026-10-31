import {
  countDarkPixels,
  expect,
  planTrip,
  settledMap,
  stubApi,
  test,
} from './fixtures/app.ts'

test.beforeEach(async ({ page }) => {
  await stubApi(page)
  await page.goto('/')
  await planTrip(page)
  await expect(
    page.getByRole('slider', { name: 'Forecast hour' }),
  ).toBeVisible()
})

test('the shading follows the selected hour', async ({ page }) => {
  const slider = page.getByRole('slider', { name: 'Forecast hour' })
  const calm = await settledMap(page)

  await slider.fill('12')
  const storm = await settledMap(page)
  expect(storm.equals(calm)).toBe(false)

  await slider.fill('0')
  const calmAgain = await settledMap(page)
  expect(calmAgain.equals(calm)).toBe(true)
})

test('shading colour shows the risk level, not how many points overlap', async ({
  page,
}) => {
  const slider = page.getByRole('slider', { name: 'Forecast hour' })

  // Moderate everywhere must stay light, however close together the points are.
  await slider.fill('5')
  const whenModerate = await countDarkPixels(page)

  // No Travel everywhere must look nothing like it.
  await slider.fill('6')
  const whenNoTravel = await countDarkPixels(page)

  expect(whenNoTravel - whenModerate).toBeGreaterThan(5000)
})

test('moving from hour 0 to hour 48 makes no network requests', async ({
  page,
}) => {
  const requests: string[] = []
  page.on('request', (request) => requests.push(request.url()))
  const slider = page.getByRole('slider', { name: 'Forecast hour' })

  for (let hour = 0; hour <= 48; hour += 1) {
    await slider.fill(String(hour))
  }

  expect(requests).toEqual([])
  await expect(page.getByText(/^Hour 48:/)).toBeVisible()
})

test('the label gives the clock time for each hour', async ({ page }) => {
  await expect(page.getByText(/^Hour 0:/)).toBeVisible()
  await page.getByRole('slider', { name: 'Forecast hour' }).fill('24')
  const label = await page.getByText(/^Hour 24:/).innerText()
  expect(label).toMatch(/\d{1,2}:\d{2} [AP]M/)
})

test('the keyboard can step through all 49 frames without errors', async ({
  page,
}) => {
  const slider = page.getByRole('slider', { name: 'Forecast hour' })
  await slider.focus()
  for (let step = 0; step < 48; step += 1) {
    await page.keyboard.press('ArrowRight')
  }
  await expect(slider).toHaveValue('48')
  await expect(page.getByText(/^Hour 48:/)).toBeVisible()
})

test('says when part of an hour has no forecast', async ({ page }) => {
  const slider = page.getByRole('slider', { name: 'Forecast hour' })
  await expect(page.getByText(/No forecast for/)).toHaveCount(0)
  await slider.fill('30')
  await expect(
    page.getByText(/No forecast for \d+ of \d+ points/),
  ).toBeVisible()
})

test('a new plan starts back at hour 0', async ({ page }) => {
  await page.getByRole('slider', { name: 'Forecast hour' }).fill('30')
  await page.getByRole('button', { name: 'Plan routes' }).click()
  await expect(page.getByRole('slider', { name: 'Forecast hour' })).toHaveValue(
    '0',
  )
})
