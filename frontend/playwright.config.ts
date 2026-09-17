import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  timeout: 120000,
  retries: 0,
  expect: { timeout: 30000 },
  use: {
    baseURL: 'http://127.0.0.1:8010',
    viewport: { width: 1440, height: 1000 },
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `${process.env.WORKBENCH_PYTHON || 'python'} tests/browser_server.py`,
    cwd: '..',
    url: 'http://127.0.0.1:8010/chat',
    timeout: 120000,
    env: { PYTHONDONTWRITEBYTECODE: '1' },
    reuseExistingServer: false,
  },
})
