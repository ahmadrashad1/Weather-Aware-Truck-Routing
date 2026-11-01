import { expect, test } from '@playwright/test'

import { stubApi } from './fixtures/app.ts'

// The config reduces motion for pixel comparisons, but these tests are about the motion.
test.use({ contextOptions: { reducedMotion: 'no-preference' } })

test.beforeEach(async ({ page }) => {
  await stubApi(page)
  await page.goto('/')
})

test('opens on the introduction, with the planner on the next page', async ({
  page,
}) => {
  await expect(
    page.getByRole('heading', { name: 'Weather-Aware Truck Routing' }),
  ).toBeInViewport()
  await expect(
    page.getByRole('heading', { name: 'Plan a trip' }),
  ).not.toBeInViewport()
})

test('the scroll control leads to the planner and back', async ({ page }) => {
  await page
    .getByRole('link', { name: 'Scroll down to the route planner' })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Plan a trip' }),
  ).toBeInViewport()
  await page.getByRole('link', { name: 'Back to the introduction' }).click()
  await expect(
    page.getByRole('heading', { name: 'Weather-Aware Truck Routing' }),
  ).toBeInViewport()
})

test('scrolling moves the film and the words at different speeds', async ({
  page,
}) => {
  const layer = (name: string) => page.locator(`[data-layer="${name}"]`)
  await page.evaluate(() => window.scrollTo({ top: 300, behavior: 'instant' }))
  await expect
    .poll(() => layer('copy').evaluate((el) => el.style.transform))
    .toContain('translate3d(0px, -')
  const media = await layer('media').evaluate((el) => el.style.transform)
  expect(media).toContain('scale(')
  expect(media).not.toContain('-')
})

test('the wheel over the map scrolls the page until the map is in view', async ({
  page,
}, info) => {
  test.skip(info.project.name === 'mobile', 'Phones have no wheel')
  await page.locator('canvas').waitFor({ state: 'attached' })
  await page.evaluate(() => window.scrollTo({ top: 200, behavior: 'instant' }))
  await page.mouse.move(900, 700)
  const before = await page.evaluate(() => window.scrollY)
  await page.mouse.wheel(0, 120)
  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(before)
})

test('people who reduce motion get a still instead of the film', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.reload()
  await expect(page.locator('video')).toHaveCount(0)
  await expect(page.locator('[data-layer="media"] img')).toBeAttached()
})

test('the title uses large, tight system type', async ({ page }) => {
  const title = page.getByRole('heading', {
    name: 'Weather-Aware Truck Routing',
  })
  const style = await title.evaluate((el) => {
    const { filter, fontFamily, fontWeight, letterSpacing } =
      getComputedStyle(el)
    return { filter, fontFamily, fontWeight, letterSpacing }
  })
  expect(style.filter).toBe('none')
  expect(style.fontFamily).toContain('system-ui')
  expect(style.fontWeight).toBe('600')
  expect(parseFloat(style.letterSpacing)).toBeLessThan(0)
})
