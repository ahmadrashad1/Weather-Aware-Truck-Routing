import { expect, test } from '@playwright/test'

// Runs against the real Django API and real providers, and spends their quota. It only runs
// when PLAYWRIGHT_LIVE is set, which CI does only on a manual run of the live smoke workflow.
test('plans a real trip end to end', async ({ page }) => {
  const problems: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(message.text())
  })
  page.on('pageerror', (error) => problems.push(String(error)))

  await page.goto('/')
  await page.getByRole('combobox', { name: 'Origin' }).pressSequentially('Dall')
  await page.getByRole('option', { name: 'Dallas, TX' }).first().click()
  await page
    .getByRole('combobox', { name: 'Destination' })
    .pressSequentially('Denv')
  await page.getByRole('option', { name: 'Denver, CO' }).first().click()
  await page.getByLabel('Load weight (lb)').fill('45000')
  await page.getByRole('button', { name: 'Plan routes' }).click()

  await expect(page.locator('ol button').first()).toBeVisible({
    timeout: 180_000,
  })
  await expect(page.getByRole('slider', { name: 'Forecast hour' })).toBeVisible(
    { timeout: 180_000 },
  )
  await page.getByRole('slider', { name: 'Forecast hour' }).fill('48')
  await expect(page.getByText(/^Hour 48:/)).toBeVisible()

  // Tiles can be cancelled mid-zoom, which is normal. Anything else is a real problem.
  expect(problems.filter((p) => !p.includes('AbortError'))).toEqual([])
})
