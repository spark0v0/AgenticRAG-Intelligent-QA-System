// Manual opt-in: this script can consume the configured provider's quota.
import { chromium, expect } from '@playwright/test'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
if (process.env.AGENTICRAG_REAL_SMOKE !== '1' && process.env.AGENTICRAG_CAPTURE_ONLY !== '1')
  throw new Error('Set AGENTICRAG_REAL_SMOKE=1 to authorize real calls.')
const baseURL = process.env.WORKBENCH_URL || 'http://127.0.0.1:8002'
const modelLabel = process.env.WORKBENCH_MODEL_LABEL
const output = 'test-results/real-service'
mkdirSync(output, { recursive: true })
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
page.setDefaultTimeout(30000)
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (message) => {
  if (message.type() === 'error') errors.push(message.text())
})
const metrics = {
  date: new Date().toISOString(),
  realProvider: true,
  historyIsolated: true,
  errors,
}
try {
  await page.goto(`${baseURL}/chat`)
  await expect(page.getByRole('button', { name: '探索本地知识', exact: false })).toBeEnabled()
  await page.screenshot({ path: `${output}/real-welcome.png` })
  metrics.retiredModeHttpStatus = (
    await page.request.get(`${baseURL}/api/status?mode=demo`)
  ).status()
  if (
    process.env.AGENTICRAG_CAPTURE_EXISTING === '1' ||
    process.env.AGENTICRAG_CAPTURE_ONLY === '1'
  ) {
    const prior = JSON.parse(readFileSync(`${output}/real-service-metrics.json`, 'utf8'))
    delete prior.scriptError
    Object.assign(metrics, prior, { errors })
    const sessions = await (await page.request.get(`${baseURL}/api/sessions`)).json()
    await page.evaluate(
      (id) => localStorage.setItem('rag-session', id),
      sessions.items.find((item) => item.turn_count > 0).session_id,
    )
    await page.reload()
    await expect(page.locator('.message.assistant').last()).toBeVisible()
  } else {
    if (modelLabel) {
      await page.locator('.model-select').click()
      await page.getByRole('option', { name: modelLabel, exact: true }).click()
    }
    await page.locator('.mode-select').click()
    await page.getByRole('option', { name: '知识检索', exact: true }).click()
    const input = page.getByRole('textbox', { name: '输入问题' })
    await input.fill('用三点概括本地资料中 AgenticRAG 的核心模块，标注来源，回答不超过150字。')
    const started = Date.now()
    const responsePromise = page.waitForResponse(
      (r) => r.url().endsWith('/api/query/stream') && r.request().method() === 'POST',
    )
    await input.press('Enter')
    const response = await responsePromise
    metrics.queryHttpStatus = response.status()
    try {
      await expect(page.getByText('生成草稿', { exact: true })).toBeVisible({ timeout: 90000 })
      metrics.firstVisibleDeltaMs = Date.now() - started
    } catch {
      metrics.firstVisibleDeltaMs = null
    }
    await expect(input).toBeEnabled({ timeout: 120000 })
    metrics.totalRequestMs = Date.now() - started
  }
  const input = page.getByRole('textbox', { name: '输入问题' })
  const sessionId = await page.evaluate(() => localStorage.getItem('rag-session'))
  const detail = await (await page.request.get(`${baseURL}/api/sessions/${sessionId}`)).json()
  const run = detail.runs.at(-1)
  const events = detail.trace.filter((e) => e.run_id === run.id)
  const terminal = {
    type: run.status === 'success' ? 'completed' : run.status,
    data: { result: run.result, message: run.error },
  }
  metrics.terminal = terminal?.type
  metrics.nodes = [...new Set(events.filter((e) => e.type === 'stage').map((e) => e.data.node))]
  metrics.generationRounds = events.filter((e) => e.type === 'answer_start').length
  metrics.sourceCount = terminal?.data.result?.source_map?.length ?? 0
  metrics.model = terminal?.data.result?.model
  metrics.error = terminal?.data.message
  await page.getByRole('button', { name: '展开执行详情', exact: true }).click()
  await page.screenshot({ path: `${output}/real-workbench-desktop.png` })
  if (terminal?.type === 'completed') {
    metrics.finalMatchesDatabase = detail.messages.at(-1).content === terminal.data.result.answer
    const answer = await page.locator('.message.assistant .markdown').last().textContent()
    await page.getByRole('tab', { name: /^来源/ }).click()
    await page.screenshot({ path: `${output}/real-sources.png` })
    await page.reload()
    await expect(page.locator('.message.assistant .markdown').last()).toHaveText(answer)
    metrics.historyRestored = true
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.sidebar')).not.toBeInViewport()
  await page.screenshot({ path: `${output}/real-workbench-mobile.png` })
  metrics.mobileNoOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= innerWidth,
  )
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('link', { name: '工具中心' }).click()
  await expect(page.locator('.tool-card').first()).toBeVisible()
  await page.screenshot({ path: `${output}/real-tools.png`, fullPage: true })
  await page.getByRole('link', { name: '系统概览' }).click()
  await page.getByRole('button', { name: '刷新状态' }).click()
  await expect(page.getByText('调用成功', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '刷新状态' })).toBeEnabled()
  await page.screenshot({ path: `${output}/real-system.png`, fullPage: true })
  // One optional second request checks cancellation; no retry or provider switching.
  if (terminal?.type === 'completed' && process.env.AGENTICRAG_CAPTURE_ONLY !== '1') {
    await page.getByRole('button', { name: '新建会话', exact: true }).click()
    if (modelLabel) {
      await page.locator('.model-select').click()
      await page.getByRole('option', { name: modelLabel, exact: true }).click()
    }
    await page.locator('.mode-select').click()
    await page.getByRole('option', { name: '快速回答', exact: true }).click()
    await input.fill('请详细解释 Vue 3 Composition API 的职责拆分，给出三个例子。')
    await input.press('Enter')
    await expect(page.getByText('生成草稿', { exact: true })).toBeVisible({ timeout: 90000 })
    await page.getByRole('button', { name: '停止生成', exact: true }).click()
    await expect(input).toBeEnabled()
    const cancelSession = await page.evaluate(() => localStorage.getItem('rag-session'))
    const detail = await (await page.request.get(`${baseURL}/api/sessions/${cancelSession}`)).json()
    metrics.cancelStatus = detail.runs.at(-1)?.status
    metrics.cancelInputRestored = (await input.inputValue()).startsWith('请详细解释')
    await page.screenshot({ path: `${output}/real-cancelled.png` })
  }
} catch (error) {
  metrics.scriptError = error.message
} finally {
  writeFileSync(`${output}/real-service-metrics.json`, JSON.stringify(metrics, null, 2))
  console.log(JSON.stringify(metrics, null, 2))
  await browser.close()
}
