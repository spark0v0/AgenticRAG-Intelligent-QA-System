// Only capture a clean workspace; never publish existing credentials or history.
import { chromium, expect } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'

const baseURL = process.env.WORKBENCH_URL || 'http://127.0.0.1:8005'
const output = process.env.WORKBENCH_SCREENSHOT_DIR || 'test-results/screenshots'
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = []
page.on('pageerror', () => errors.push('pageerror'))
page.on('console', (message) => {
  if (message.type() === 'error') errors.push('console.error')
})
const metrics = { date: new Date().toISOString(), newModelRequest: false, errors, viewports: [] }
try {
  for (const path of ['settings/providers', 'sessions', 'runs']) {
    const response = await page.request.get(`${baseURL}/api/${path}`)
    expect(response.ok()).toBe(true)
    expect((await response.json()).items.length, 'Capture requires an empty workspace').toBe(0)
  }
  const status = await (await page.request.get(`${baseURL}/api/status`)).json()
  expect(status.model_profiles.every((profile) => !profile.configured)).toBe(true)
  mkdirSync(output, { recursive: true })
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)
    for (const path of ['chat', 'providers', 'runs']) {
      await page.goto(`${baseURL}/${path}`)
      await expect(page.locator('.connection-line')).toHaveCount(0)
      if (path === 'chat') await expect(page.getByRole('link', { name: '配置可用模型' })).toBeVisible()
      if (path === 'providers') {
        await expect(page.getByRole('heading', { name: '连接第一个模型供应商' })).toBeVisible()
        await page.getByRole('button', { name: '添加供应商' }).first().click()
        await expect(page.getByLabel('API Key', { exact: true })).toHaveValue('')
        await page.getByRole('button', { name: '取消', exact: true }).click()
        await expect(page.getByRole('dialog')).toBeHidden()
      }
      if (path === 'runs') await expect(page.getByRole('heading', { name: '运行分析' })).toBeVisible()
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
      expect(overflow).toBe(false)
      metrics.viewports.push({ path, width: viewport.width, overflow })
      await page.screenshot({ path: `${output}/clean-${path}-${viewport.width}.png`, animations: 'disabled' })
    }
  }
  expect(errors).toEqual([])
  writeFileSync(`${output}/clean-metrics.json`, JSON.stringify(metrics, null, 2))
  console.log(JSON.stringify(metrics, null, 2))
} finally {
  await browser.close()
}
