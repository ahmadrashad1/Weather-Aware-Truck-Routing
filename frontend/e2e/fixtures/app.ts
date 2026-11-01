import { expect, test as base, type Page, type Route } from '@playwright/test'

import { DALLAS, DENVER, heatmap, plan } from './data.ts'

// A plain background in place of the real base map, so tests never leave this machine.
const BLANK_STYLE = {
  version: 8,
  sources: {},
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': '#f2f3f0' },
    },
  ],
}

type Responder = (route: Route) => Promise<void> | void

interface ApiStubs {
  plan?: Responder
  heatmap?: Responder
}

export function json(body: unknown, status = 200): Responder {
  return (route) =>
    route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
}

export async function stubApi(page: Page, stubs: ApiStubs = {}) {
  await page.route('**/api/v1/geocode**', (route) => {
    const query = new URL(route.request().url()).searchParams.get('q') ?? ''
    const results = query.startsWith('Dal') ? [DALLAS] : [DENVER]
    return route.fulfill({ json: { results } })
  })
  await page.route('**/api/v1/trips/plan', stubs.plan ?? json(plan))
  await page.route('**/api/v1/trips/heatmap', stubs.heatmap ?? json(heatmap))
}

export async function fillTrip(page: Page, load = '45000') {
  await page.getByRole('combobox', { name: 'Origin' }).pressSequentially('Dal')
  await page.getByRole('option', { name: 'Dallas, TX' }).click()
  await page
    .getByRole('combobox', { name: 'Destination' })
    .pressSequentially('Den')
  await page.getByRole('option', { name: 'Denver, CO' }).click()
  await page.getByLabel('Load weight (lb)').fill(load)
}

export async function planTrip(page: Page) {
  await fillTrip(page)
  await page.getByRole('button', { name: 'Plan routes' }).click()
}

/** The route list's card for a route, as opposed to its label on the map. */
export function routeCard(page: Page, name: RegExp) {
  return page.getByRole('list').getByRole('button', { name })
}

/**
 * A picture of what the map itself has drawn, once it has stopped changing.
 *
 * An element screenshot includes whatever sits on top of it, so route labels, the legend and the
 * forecast panel are hidden first. Otherwise these would make an empty map look drawn.
 */
export async function settledMap(page: Page): Promise<Buffer> {
  const hideOverlays = await page.addStyleTag({
    content: `
      main * { visibility: hidden !important; }
      main canvas.maplibregl-canvas { visibility: visible !important; }
    `,
  })
  try {
    const canvas = page.locator('canvas.maplibregl-canvas')
    let previous = await canvas.screenshot()
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await page.waitForTimeout(150)
      const next = await canvas.screenshot()
      if (next.equals(previous)) return next
      previous = next
    }
    throw new Error('The map did not settle')
  } finally {
    await hideOverlays.evaluate((element) => (element as Element).remove())
  }
}

/** How many map pixels are dark, which only No Travel shading or a dark line can be. */
export async function countDarkPixels(page: Page): Promise<number> {
  const png = await settledMap(page)
  return page.evaluate(async (base64) => {
    const response = await fetch(`data:image/png;base64,${base64}`)
    const bitmap = await createImageBitmap(await response.blob())
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height)
    const context = canvas.getContext('2d')!
    context.drawImage(bitmap, 0, 0)
    const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height)
    let dark = 0
    for (let i = 0; i < data.length; i += 4) {
      if ((data[i] + data[i + 1] + data[i + 2]) / 3 < 150) dark += 1
    }
    return dark
  }, png.toString('base64'))
}

export const test = base.extend<{ problems: string[] }>({
  problems: [
    async ({ page }, use) => {
      const problems: string[] = []
      page.on('console', (message) => {
        if (message.type() === 'error') problems.push(message.text())
      })
      page.on('pageerror', (error) => problems.push(String(error)))

      await page.route(
        (url) => url.hostname !== '127.0.0.1',
        (route) => {
          if (route.request().url().includes('/styles/')) {
            return route.fulfill({ json: BLANK_STYLE })
          }
          problems.push(`Unexpected request: ${route.request().url()}`)
          return route.abort()
        },
      )

      await use(problems)

      // A worker that fails to start only ever shows up here: the page still looks fine.
      expect(problems).toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
