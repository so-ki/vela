import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  reporter: process.env.CI
    ? [['line'], ['html', { outputFolder: 'playwright-report', open: 'never' }]]
    : 'line',
  use: {
    baseURL: process.env.VELA_E2E_BASE_URL || 'http://127.0.0.1:8089',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
})
