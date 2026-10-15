import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'

test('retrieval comparison, evidence and stale requests remain scoped to the selected library', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const headers = { 'X-Workbench-Request': '1' }
  async function library(name: string, content: string) {
    const response = await page.request.post('/api/knowledge', { headers, data: { name, mode: 'keyword' } })
    expect(response.status()).toBe(201)
    const created = await response.json()
    const uploaded = await page.request.post(`/api/knowledge/${created.id}/documents`, { headers, multipart: { files: { name: `${name}.md`, mimeType: 'text/markdown', buffer: Buffer.from(content) } } })
    expect(uploaded.status()).toBe(202)
    await expect.poll(async () => (await (await page.request.get(`/api/knowledge/${created.id}/documents`)).json()).items[0]?.status).toBe('completed')
    return created
  }
  const first = await library('差旅管理', '# 差旅报销\n\n差旅报销需要提供发票，并由部门负责人审批。')
  const second = await library('设备使用', '# 设备领用\n\n设备领用请联系资产管理员，登记设备编号。')
  await page.goto(`/knowledge?kb=${first.id}`)
  await page.locator('.kb-probe > summary').click()
  const question = page.getByLabel('用一个问题检查资料是否能被找到')
  await question.fill('差旅报销')
  await page.locator('.kb-probe-controls .el-select__wrapper').click()
  await page.getByRole('option', { name: '三种模式对比' }).click()
  await page.getByRole('button', { name: '开始对比', exact: true }).click()
  const keyword = page.getByRole('region', { name: '关键词检索结果' })
  const semantic = page.getByRole('region', { name: '语义检索结果' })
  await expect(keyword.locator('.kb-hit')).toHaveCount(1)
  await expect(semantic).toContainText('仅建立了关键词索引')
  await expect(keyword.locator('.kb-hit-ranking')).toContainText('BM25')
  await keyword.getByRole('button', { name: '查看证据与原文' }).click()
  await expect(page.getByRole('heading', { name: '原文位置的完整片段' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: '文档证据' })).toBeHidden()
  mkdirSync('test-results/evidence', { recursive: true })
  await page.locator('.kb-probe').scrollIntoViewIfNeeded()
  await page.screenshot({ path: 'test-results/evidence/retrieval-desktop.png' })
  await page.setViewportSize({ width: 390, height: 844 })
  await keyword.scrollIntoViewIfNeeded()
  await page.screenshot({ path: 'test-results/evidence/retrieval-mobile.png' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.setViewportSize({ width: 1440, height: 1000 })

  // Hold an actual response in the browser proxy, then switch libraries before it is delivered.
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let received!: () => void
  const intercepted = new Promise<void>(resolve => { received = resolve })
  let delivered!: () => void
  const finished = new Promise<void>(resolve => { delivered = resolve })
  await page.route(`**/api/knowledge/${first.id}/compare`, async route => {
    const response = await route.fetch()
    received()
    await gate
    try { await route.fulfill({ response }) } finally { delivered() }
  }, { times: 1 })
  await page.getByRole('button', { name: '开始对比', exact: true }).click()
  await intercepted
  await page.getByRole('button', { name: /设备使用/ }).click()
  await expect(question).toHaveValue('')
  release()
  await finished
  await question.fill('设备领用')
  await page.getByRole('button', { name: '检索', exact: true }).click()
  await expect(keyword.locator('.kb-hit')).toContainText('资产管理员')
  await expect(page.locator('.kb-probe')).not.toContainText('差旅报销')
  await expect.poll(() => new URL(page.url()).searchParams.get('kb')).toBe(second.id)

  let releaseCancelled!: () => void
  const cancelledGate = new Promise<void>(resolve => { releaseCancelled = resolve })
  let cancelReceived!: () => void
  const cancelIntercepted = new Promise<void>(resolve => { cancelReceived = resolve })
  let cancelDelivered!: () => void
  const cancelFinished = new Promise<void>(resolve => { cancelDelivered = resolve })
  await page.route(`**/api/knowledge/${second.id}/search`, async route => {
    const response = await route.fetch()
    cancelReceived()
    await cancelledGate
    try { await route.fulfill({ response }) } finally { cancelDelivered() }
  }, { times: 1 })
  await question.fill('过期的检索问题')
  await page.getByRole('button', { name: '检索', exact: true }).click()
  await cancelIntercepted
  await page.getByRole('button', { name: '停止等待', exact: true }).click()
  await expect(question).toBeFocused()
  await question.fill('设备领用')
  await question.press('Enter')
  await expect(keyword.locator('.kb-hit')).toContainText('资产管理员')
  releaseCancelled()
  await cancelFinished
  await expect(page.locator('.kb-probe-result-heading')).toContainText('设备领用')
  await expect(page.locator('.kb-probe')).not.toContainText('过期的检索问题')
  expect(errors).toEqual([])
})
