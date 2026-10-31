/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  build: {
    // MapLibre is a large library, but it loads in its own chunk after the form appears.
    chunkSizeWarningLimit: 1200,
  },
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test-setup.ts'],
    css: false,
    // Playwright runs these against a real browser.
    exclude: ['**/node_modules/**', 'e2e/**'],
    // Simulated typing is slow on a busy machine, and these limits only matter when a test hangs.
    testTimeout: 30_000,
  },
})
