import { test, expect } from '@playwright/test'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'

test('pages long history, keeps the reading anchor and exports all rounds', async ({ page }) => {
  test.skip(process.env.WORKBENCH_HISTORY_FIXTURE !== '1', 'Run with the isolated long-history fixture')
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => localStorage.setItem('rag-session', 'history-fixture'))
  await page.goto('/chat')
  await expect(page.locator('.message')).toHaveCount(40)
  await expect(page.locator('.message').first()).toContainText('历史样本问题 025')
  await expect(page.locator('.message').last()).toContainText('历史阅读样本')
  const initial = await (await page.request.get('/api/sessions/history-fixture?limit=20')).json()
  const full = await (await page.request.get('/api/sessions/history-fixture')).json()
  expect(initial.runs).toHaveLength(20)
  expect(initial.trace).toHaveLength(160)
  expect(full.runs).toHaveLength(45)
  expect((await page.request.get('/api/sessions/history-fixture?limit=20&before=invalid')).status()).toBe(422)
  await page.locator('.session-row').filter({ has: page.locator('.session-item.selected') }).getByRole('button', { name: /^会话操作/ }).click()
  const download = page.waitForEvent('download')
  await page.getByRole('menuitem', { name: '导出 Markdown' }).click()
  const exported = readFileSync((await (await download).path())!, 'utf8')
  expect(exported).toContain('历史样本问题 000')
  expect(exported).toContain('历史样本问题 044')
  expect(exported.match(/^## 提问$/gm)).toHaveLength(45)
  // Delay this page so the reader can keep scrolling while it loads.
  await page.route('**/api/sessions/history-fixture?*before=*', async route => {
    await new Promise(resolve => setTimeout(resolve, 250))
    await route.continue()
  })
  await page.locator('.conversation-scroll').evaluate(el => { el.scrollTop = 0 })
  await page.getByRole('button', { name: '加载更早消息', exact: true }).click()
  const position = await page.locator('.conversation-scroll').evaluate(el => {
    el.scrollTop = 200
    el.dispatchEvent(new Event('scroll'))
    const edge = el.getBoundingClientRect().top
    const anchor = [...el.querySelectorAll<HTMLElement>('[data-message-id]')].find(item => item.getBoundingClientRect().bottom > edge)!
    return { id: anchor.dataset.messageId!, top: anchor.getBoundingClientRect().top }
  })
  await expect(page.locator('.message')).toHaveCount(80)
  const anchor = page.locator(`[data-message-id="${position.id}"]`)
  await expect.poll(async () => Math.abs((await anchor.boundingBox())!.y - position.top)).toBeLessThan(4)
  await expect(page.getByRole('textbox', { name: '输入问题' })).toBeEditable()
  await page.getByRole('textbox', { name: '输入问题' }).fill('分页不影响草稿')
  await page.locator('.conversation-scroll').evaluate(el => { el.scrollTop = 0 })
  await page.getByRole('button', { name: '加载更早消息', exact: true }).click()
  await expect(page.locator('.message')).toHaveCount(90)
  await expect(page.getByRole('button', { name: '已加载全部历史' })).toHaveAttribute('aria-disabled', 'true')
  expect(await page.locator('[data-message-id]').evaluateAll(items => new Set(items.map(item => item.getAttribute('data-message-id'))).size)).toBe(90)
  await expect(page.getByRole('textbox', { name: '输入问题' })).toHaveValue('分页不影响草稿')
  await expect(page.locator('.message').filter({ hasText: '已取消的历史草稿' })).toHaveCount(3)
  await page.locator('.conversation-scroll').evaluate(el => { el.scrollTop = 0 })
  mkdirSync('test-results/evidence', { recursive: true })
  await page.screenshot({ path: 'test-results/evidence/history-page-desktop.png' })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/evidence/history-page-mobile.png' })
  writeFileSync('test-results/evidence/history-pagination.json', JSON.stringify({
    fixture: true, rounds: 45, initialRounds: initial.runs.length,
    initialBytes: Buffer.byteLength(JSON.stringify(initial)), fullBytes: Buffer.byteLength(JSON.stringify(full)),
    messagesAfterAllPages: 90, anchorTolerancePx: 4,
  }, null, 2))
  expect(errors).toEqual([])
})
