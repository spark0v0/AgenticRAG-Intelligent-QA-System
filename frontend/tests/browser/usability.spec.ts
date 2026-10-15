import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'

test('text drafts, session naming, pinning, export and deletion persist through the API', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/chat')
  const input = page.getByRole('textbox', { name: '输入问题' })
  await expect(input).toBeEnabled()
  await input.fill('2+3')
  await page.waitForTimeout(300) // Browser draft persistence is intentionally debounced.
  await page.reload()
  await expect(input).toHaveValue('2+3')
  await input.press('Enter')
  await expect(page.locator('.message.assistant')).toContainText('5')
  await expect(input).toBeEnabled()
  const id = await page.evaluate(() => localStorage.getItem('rag-session'))
  const menu = () => page.locator('.session-row').filter({ has: page.locator('.session-item.selected') }).getByRole('button', { name: /^会话操作/ })
  await menu().click()
  await page.getByRole('menuitem', { name: '重命名', exact: true }).click()
  const rename = page.getByRole('dialog', { name: '重命名会话' })
  await rename.getByRole('textbox').fill('验收会话')
  await rename.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.locator('.session-item.selected')).toContainText('验收会话')
  await menu().click()
  await page.getByRole('menuitem', { name: '置顶会话', exact: true }).click()
  await expect.poll(async () => (await (await page.request.get('/api/sessions')).json()).items.find((item: { session_id: string }) => item.session_id === id)?.pinned).toBe(true)
  await menu().click()
  const download = page.waitForEvent('download')
  await page.getByRole('menuitem', { name: '导出 Markdown' }).click()
  expect((await download).suggestedFilename()).toBe('验收会话.md')
  await page.reload()
  await expect(page.locator('.session-item.selected')).toContainText('验收会话')
  await menu().click()
  await page.getByRole('menuitem', { name: '删除会话', exact: true }).click()
  await page.getByRole('dialog', { name: '删除会话' }).getByRole('button', { name: '删除', exact: true }).click()
  await expect(page.locator('.session-item').filter({ hasText: '验收会话' })).toHaveCount(0)
  expect((await page.request.get(`/api/sessions/${id}`)).status()).toBe(404)
  await expect(input).toBeEnabled()
  expect(errors).toEqual([])
})

function pdfFixture() {
  const content = ['BT /F1 16 Tf 40 740 Td (Acceptance guide: status must be verified.) Tj ET', 'BT /F1 16 Tf 40 740 Td (Installation guide: run the local launcher.) Tj ET']
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>',
    `<< /Length ${content[0]!.length} >>\nstream\n${content[0]}\nendstream`,
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>',
    `<< /Length ${content[1]!.length} >>\nstream\n${content[1]}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ]
  let pdf = '%PDF-1.4\n'
  const offsets = [0]
  objects.forEach((object, index) => { offsets.push(Buffer.byteLength(pdf)); pdf += `${index+1} 0 obj\n${object}\nendobj\n` })
  const xref = Buffer.byteLength(pdf)
  pdf += `xref\n0 8\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10,'0')} 00000 n \n`).join('')}trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`
  return Buffer.from(pdf)
}

test('knowledge deep-link and PDF evidence reader work on desktop and narrow screens', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const headers = { 'X-Workbench-Request': '1' }
  const created = await page.request.post('/api/knowledge', { headers, data: { name: 'PDF 阅读检查', mode: 'keyword' } })
  expect(created.status()).toBe(201)
  const library = await created.json()
  await page.request.post(`/api/knowledge/${library.id}/documents`, { headers, multipart: { files: { name: 'guide.pdf', mimeType: 'application/pdf', buffer: pdfFixture() } } })
  await expect.poll(async () => (await (await page.request.get(`/api/knowledge/${library.id}/documents`)).json()).items[0]?.status).toBe('completed')
  await page.goto(`/knowledge?kb=${library.id}&search=guide&status=completed`)
  await expect(page.getByRole('button', { name: /PDF 阅读检查/ })).toHaveAttribute('aria-pressed', 'true')
  await page.reload()
  expect(new URL(page.url()).searchParams.get('search')).toBe('guide')
  await page.locator('.kb-probe summary').click()
  await page.getByLabel('用一个问题检查资料是否能被找到').fill('acceptance')
  await page.getByRole('button', { name: '检索', exact: true }).click()
  await page.getByRole('button', { name: '查看证据与原文' }).first().click()
  const drawer = page.getByRole('dialog', { name: '文档证据' })
  const worker = page.waitForResponse(response => /pdf\.worker\.min-.*\.mjs/.test(response.url()))
  await drawer.getByRole('button', { name: '在此阅读 PDF' }).click()
  expect((await worker).headers()['content-type']).toContain('javascript')
  await expect(drawer.locator('.pdf-status')).toHaveText('正在阅读第 1 页')
  expect(await drawer.locator('canvas').evaluate(canvas => canvas.width)).toBeGreaterThan(200)
  await drawer.getByRole('button', { name: '下一页' }).click()
  await expect(drawer.locator('.pdf-status')).toHaveText('正在阅读第 2 页')
  await drawer.getByRole('button', { name: '引用页' }).click()
  await expect(drawer.locator('.pdf-status')).toHaveText('正在阅读第 1 页')
  mkdirSync('test-results/evidence', { recursive: true })
  await page.screenshot({ path: 'test-results/evidence/reader-desktop.png' })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(async () => (await drawer.boundingBox())!.x).toBeGreaterThanOrEqual(-1)
  await expect.poll(async () => (await drawer.boundingBox())!.width).toBeLessThanOrEqual(391)
  await drawer.getByLabel('缩放').selectOption('1.5')
  await expect.poll(async () => drawer.locator('canvas').evaluate(canvas => canvas.getBoundingClientRect().width)).toBeLessThan(600)
  await expect(drawer.locator('.pdf-status')).toHaveText('正在阅读第 1 页')
  await page.screenshot({ path: 'test-results/evidence/reader-mobile.png' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(errors).toEqual([])
})
