import { defineConfig, devices } from '@playwright/test'

const PORT = 4173
const isLive = Boolean(process.env.PLAYWRIGHT_LIVE)

export default defineConfig({
  testDir: './e2e',
  // The live check spends real provider quota, so it only runs when asked for.
  testMatch: isLive
    ? /live\.spec\.ts/
    : /(trip|heatmap|errors|hero|mobile)\.spec\.ts/,
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: isLive ? 240_000 : 60_000,
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    // Map animations would make pixel comparisons depend on timing.
    contextOptions: { reducedMotion: 'reduce' },
    launchOptions: {
      // MapLibre needs WebGL, and test machines have no GPU.
      args: [
        '--use-gl=angle',
        '--use-angle=swiftshader',
        '--enable-unsafe-swiftshader',
      ],
    },
  },
  projects: [
    {
      name: 'desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
      },
    },
    {
      name: 'mobile',
      testMatch: isLive ? /^$/ : /(trip|hero|mobile)\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        // A real phone's touch input, and its smaller space under the browser's own bars.
        viewport: { width: 390, height: 664 },
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
  webServer: {
    // The production build, because the map's worker has failed there when dev mode worked.
    command: `npm run build && npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
