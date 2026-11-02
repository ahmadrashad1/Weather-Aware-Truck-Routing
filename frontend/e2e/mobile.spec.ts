import { expect, test } from '@playwright/test'
import type { CDPSession, Page } from '@playwright/test'

import { stubApi } from './fixtures/app.ts'

test.skip(({ isMobile }) => !isMobile, 'Phone gestures only')

async function touch(page: Page) {
  return page.context().newCDPSession(page)
}

/** A real finger: the browser decides what it means, as it would on a phone. */
async function swipe(
  cdp: CDPSession,
  from: { x: number; y: number },
  toY: number,
) {
  const steps = 12
  await cdp.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [from],
  })
  for (let step = 1; step <= steps; step++) {
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: from.x, y: from.y + ((toY - from.y) * step) / steps }],
    })
    await new Promise((done) => setTimeout(done, 16))
  }
  await cdp.send('Input.dispatchTouchEvent', {
    type: 'touchEnd',
    touchPoints: [],
  })
}

const sheet = (page: Page) => page.getByRole('complementary')
const sheetTop = async (page: Page) =>
  Math.round((await sheet(page).boundingBox())!.y)

/** A spring has no fixed duration, so wait until the sheet has actually stopped. */
async function sheetAtRest(page: Page) {
  let previous = -1
  await expect
    .poll(
      async () => {
        const current = await sheetTop(page)
        const still = current === previous
        previous = current
        return still
      },
      { intervals: [150], timeout: 5000 },
    )
    .toBe(true)
}

async function enterPlanner(page: Page) {
  await page.getByRole('link', { name: 'Plan a trip' }).tap()
  await expect(
    page.getByRole('heading', { name: 'Plan a trip' }),
  ).toBeInViewport()
  await page.waitForTimeout(800)
}

async function planTrip(page: Page) {
  await page.getByRole('combobox', { name: 'Origin' }).pressSequentially('Dal')
  await page.getByRole('option', { name: 'Dallas, TX' }).tap()
  await page
    .getByRole('combobox', { name: 'Destination' })
    .pressSequentially('Den')
  await page.getByRole('option', { name: 'Denver, CO' }).tap()
  await page.getByLabel('Load weight (lb)').fill('45000')
  await page.getByRole('button', { name: 'Plan routes' }).tap()
  await page.getByRole('slider', { name: 'Forecast hour' }).waitFor()
  await sheetAtRest(page)
}

test.use({ contextOptions: { reducedMotion: 'no-preference' } })

test.beforeEach(async ({ page }) => {
  await stubApi(page)
  await page.goto('/')
})

test('a swipe on the hero lands exactly on the planner', async ({ page }) => {
  const cdp = await touch(page)
  await swipe(cdp, { x: 195, y: 650 }, 150)
  await expect
    .poll(() => page.evaluate(() => Math.round(scrollY)), { timeout: 4000 })
    .toBe(await page.evaluate(() => innerHeight))
})

test('nothing runs off the side of the screen', async ({ page }) => {
  await enterPlanner(page)
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
})

test('after planning, the map and the recommended route both show', async ({
  page,
}) => {
  await enterPlanner(page)
  await planTrip(page)
  const viewport = page.viewportSize()!
  const top = await sheetTop(page)
  expect(top).toBeGreaterThan(viewport.height * 0.4)
  expect(top).toBeLessThan(viewport.height * 0.7)
  await expect(page.getByText('Recommended').first()).toBeInViewport()
  await expect(page.locator('canvas.maplibregl-canvas')).toBeInViewport()
})

test('the sheet follows a finger and settles on a stop', async ({ page }) => {
  await enterPlanner(page)
  await planTrip(page)
  const cdp = await touch(page)
  const half = await sheetTop(page)
  await swipe(cdp, { x: 195, y: half + 10 }, half + 280)
  await sheetAtRest(page)
  const peek = await sheetTop(page)
  expect(peek).toBeGreaterThan(half + 100)
  await swipe(cdp, { x: 195, y: peek + 10 }, 80)
  await sheetAtRest(page)
  expect(await sheetTop(page)).toBeLessThan(half - 100)
})

test('a finger on the map moves the map, not the page', async ({ page }) => {
  await enterPlanner(page)
  await planTrip(page)
  const cdp = await touch(page)
  const before = await page.evaluate(() => scrollY)
  await swipe(cdp, { x: 195, y: 200 }, 80)
  await page.waitForTimeout(500)
  expect(await page.evaluate(() => scrollY)).toBe(before)
})

test('scrolling the sheet leaves the page and the map alone', async ({
  page,
}) => {
  await enterPlanner(page)
  await planTrip(page)
  const cdp = await touch(page)
  const before = await page.evaluate(() => scrollY)
  // The half-open stop, which a busy machine's spring can take a while to reach.
  const top = Math.round(page.viewportSize()!.height * 0.54)
  await expect.poll(() => sheetTop(page)).toBe(top)
  await swipe(cdp, { x: 195, y: top + 200 }, top + 90)
  await page.waitForTimeout(500)
  expect(await page.evaluate(() => scrollY)).toBe(before)
  expect(await sheetTop(page)).toBe(top)
})

test('typing opens the sheet fully, so the field stays in view', async ({
  page,
}) => {
  await enterPlanner(page)
  await planTrip(page)
  const half = await sheetTop(page)
  await page.getByLabel('Load weight (lb)').focus()
  await sheetAtRest(page)
  expect(await sheetTop(page)).toBeLessThan(half)
})

test('the controls are large enough to tap', async ({ page }) => {
  await enterPlanner(page)
  const small = await page.evaluate(() =>
    Array.from(
      document.querySelectorAll(
        '[aria-label="Back to the introduction"], fieldset label, button[type="submit"]',
      ),
    )
      .filter((el) => el.getBoundingClientRect().height < 44)
      .map((el) => el.textContent),
  )
  expect(small).toEqual([])
})

test('the forecast slider stays usable above the sheet', async ({ page }) => {
  await enterPlanner(page)
  await planTrip(page)
  const slider = page.getByRole('slider', { name: 'Forecast hour' })
  await expect(slider).toBeInViewport()
  await slider.fill('24')
  await expect(page.getByText(/^Hour 24:/)).toBeVisible()
})

test('the planner can always get back to the introduction', async ({
  page,
}) => {
  await enterPlanner(page)
  await page.getByRole('link', { name: 'Back to the introduction' }).tap()
  await expect(
    page.getByRole('heading', { name: 'Weather-Aware Truck Routing' }),
  ).toBeInViewport()
})

test('opening a checkpoint lowers the sheet and keeps the popup reachable', async ({
  page,
}) => {
  await enterPlanner(page)
  await planTrip(page)
  const half = await sheetTop(page)
  await page
    .getByRole('list', { name: 'Checkpoints' })
    .getByRole('button')
    .nth(1)
    .tap()
  await sheetAtRest(page)
  expect(await sheetTop(page)).toBeGreaterThan(half)
  const popup = (await page.locator('.maplibregl-popup-content').boundingBox())!
  const panel = (await page
    .getByText(/^Hour \d+:/)
    .locator('..')
    .boundingBox())!
  expect(popup.y).toBeGreaterThanOrEqual(panel.y + panel.height)
  expect(popup.y + popup.height).toBeLessThanOrEqual(await sheetTop(page))
  await page.locator('.maplibregl-popup-close-button').tap()
  await expect(page.locator('.maplibregl-popup')).toHaveCount(0)
})
