import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'

test('知识库上传、检索引用、删除快照与窄屏核心流程', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/knowledge')
  await page.getByRole('button', { name: '创建知识库', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '创建知识库' })
  await dialog.getByLabel('知识库名称').fill('产品与交付资料')
  await dialog.getByRole('combobox', { name: '检索方式' }).press('Enter')
  await page.getByRole('option', { name: '仅关键词（无需模型）' }).click()
  await dialog.getByRole('button', { name: '创建知识库', exact: true }).click()
  await expect(dialog).toBeHidden()
  const file = {
    name: '项目交付说明.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from(
      '# 交付流程\n\n项目交付前完成类型检查、生产构建和核心冒烟验证。所有修改需要记录来源与验证结果。',
    ),
  }
  await page.locator('.kb-upload input[type=file]').setInputFiles(file)
  await expect(page.locator('.kb-table').getByText('可检索', { exact: true })).toBeVisible()
  await page.locator('.kb-upload input[type=file]').setInputFiles(file)
  await expect(page.getByRole('status').filter({ hasText: '重复文件已跳过' })).toBeVisible()
  await page.locator('.kb-probe summary').click()
  await page.getByLabel('用一个问题检查资料是否能被找到').fill('项目交付前需要哪些验证？')
  await page.getByRole('button', { name: '检索', exact: true }).click()
  await expect(page.locator('.kb-hit')).toHaveCount(1)
  await page.getByRole('button', { name: '查看证据与原文' }).click()
  await expect(page.getByRole('heading', { name: '原文位置的完整片段' })).toBeVisible()
  await expect(page.getByRole('link', { name: '打开原始文档' })).toHaveAttribute(
    'href',
    /\/original$/,
  )
  await page.screenshot({
    path: '../docs/screenshots/knowledge-evidence-1440.png',
    animations: 'disabled',
  })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('heading', { name: '原文位置的完整片段' })).toBeHidden()
  mkdirSync('../docs/screenshots', { recursive: true })
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport)
    await page.locator('.kb-page').evaluate((element) => {
      element.scrollTop = 0
    })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    await page.screenshot({
      path: `../docs/screenshots/knowledge-${viewport.width}.png`,
      fullPage: true,
      animations: 'disabled',
    })
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: '基于资料提问' }).click()
  await page.getByRole('textbox', { name: '输入问题' }).fill('项目交付前需要哪些验证？')
  await page.getByRole('button', { name: '发送问题' }).click()
  await expect(page.getByRole('button', { name: '停止生成' })).toBeHidden({ timeout: 30000 })
  const libraries = await (await page.request.get('/api/knowledge')).json()
  const kb = libraries.items.find((item: { name: string }) => item.name === '产品与交付资料')
  const docs = await (await page.request.get(`/api/knowledge/${kb.id}/documents`)).json()
  const runs = await (await page.request.get('/api/runs')).json()
  const run = runs.items.find(
    (item: { query: string }) => item.query === '项目交付前需要哪些验证？',
  )
  expect(run.status).toBe('success')
  const detail = await (await page.request.get(`/api/runs/${run.id}`)).json()
  expect(detail.result.source_map[0].document_id).toBe(docs.items[0].id)
  const response = await page.request.delete(
    `/api/knowledge/${kb.id}/documents/${docs.items[0].id}`,
    { headers: { 'X-Workbench-Request': '1' } },
  )
  expect(response.status()).toBe(202)
  const source = detail.result.source_map[0]
  const evidence = await (
    await page.request.get(
      `/api/knowledge/${kb.id}/documents/${source.document_id}/evidence/${source.chunk_id}`,
    )
  ).json()
  expect(evidence.original_available).toBe(false)
  const saved = await (await page.request.get(`/api/runs/${run.id}`)).json()
  expect(saved.result.source_map).toEqual(detail.result.source_map)
  expect(errors).toEqual([])
})
