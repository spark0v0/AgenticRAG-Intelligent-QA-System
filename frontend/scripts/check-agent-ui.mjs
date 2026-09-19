// Read-only inspection of the one explicit verification question; no generation.
import { chromium, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
const base = process.env.WORKBENCH_URL || 'http://127.0.0.1:8005'
const browser = await chromium.launch({ channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = []
page.on('pageerror', () => errors.push('pageerror'))
page.on('console', message => { if (message.type() === 'error') errors.push('console.error') })
try {
  const response = await page.request.get(`${base}/api/runs?search=${encodeURIComponent('根据本地文档，用一句话说明会话如何持久化，并引用来源。')}`)
  const runs = (await response.json()).items
  const run = runs.find(item => item.status === 'success')
  if (!run) throw new Error('No matching successful verification run; no request sent')
  await page.goto(`${base}/chat`)
  await page.evaluate(id => localStorage.setItem('rag-session', id), run.session_id)
  await page.reload()
  await expect(page.locator('.answer-evidence-summary').last()).toContainText('本地 RAG')
  await page.getByRole('button', { name: '执行详情', exact: false }).last().click()
  await expect(page.locator('.assessment')).toContainText('结构检查通过')
  await page.getByText('检索决策与停止原因', { exact: true }).click()
  await expect(page.locator('.execution-panel')).toContainText('没有新增证据')
  mkdirSync('test-results/agent-live', { recursive: true })
  await page.locator('.conversation-scroll').evaluate(element => { element.scrollTop = 0 })
  await page.locator('.chat-workspace').screenshot({ path: 'test-results/agent-live/answer-desktop.png', animations: 'disabled' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('.execution-panel').getByRole('button', { name: '收起执行详情', exact: true }).click()
  await expect(page.getByRole('radio', { name: '联网搜索', exact: true })).toBeVisible()
  await expect(page.locator('.sidebar')).not.toBeInViewport()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.locator('.composer').screenshot({ path: 'test-results/agent-live/composer-mobile.png', animations: 'disabled' })
  await page.goto(`${base}/runs?run=${run.id}`)
  await page.getByRole('tab', { name: '最终回答' }).click()
  await expect(page.locator('.assessment')).toContainText('证据检查')
  expect(errors).toEqual([])
  console.log(JSON.stringify({ realHistoryRestored: true, evidenceCheckVisible: true, mobileOverflow: false, errors, modelRequests: 0 }))
} finally {
  await browser.close()
}
