import { defineConfig } from '@playwright/test'

const throughVite = process.env.WORKBENCH_VITE === '1'
export default defineConfig({
  testDir: './tests/browser',
  outputDir: throughVite ? 'test-results/vite' : 'test-results/production',
  fullyParallel: false,
  workers: 1,
  timeout: 120000,
  retries: 0,
  ...(throughVite ? { testMatch: '**/regressions.spec.ts' } : {}),
  expect: { timeout: 30000 },
  use: {
    baseURL: throughVite ? 'http://127.0.0.1:5179' : 'http://127.0.0.1:8010',
    viewport: { width: 1440, height: 1000 },
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `${process.env.WORKBENCH_PYTHON || 'python'} tests/browser_server.py`,
      cwd: '..',
      url: 'http://127.0.0.1:8010/chat',
      timeout: 120000,
      env: { PYTHONDONTWRITEBYTECODE: '1' },
      reuseExistingServer: false,
    },
    ...(throughVite
      ? [
          {
            command: 'npm run dev -- --port 5179',
            url: 'http://127.0.0.1:5179',
            env: { VITE_API_TARGET: 'http://127.0.0.1:8010' },
            reuseExistingServer: false,
          },
        ]
      : []),
  ],
})
