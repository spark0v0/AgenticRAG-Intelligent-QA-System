import { test, expect } from '@playwright/test'

test('API prefix, first cancellation refresh, scoped retry and original document through the served origin', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  for (const path of [
    '/api/status',
    '/api/knowledge',
    '/api/settings/providers',
    '/api/sessions',
    '/api/runs',
  ]) {
    const response = await page.request.get(path)
    expect(response.ok(), path).toBe(true)
    expect(response.headers()['content-type'], path).toContain('application/json')
  }
  const headers = { 'X-Workbench-Request': '1' }
  const a = await (
    await page.request.post('/api/knowledge', {
      headers,
      data: { name: '范围回归 A', mode: 'keyword' },
    })
  ).json()
  const b = await (
    await page.request.post('/api/knowledge', {
      headers,
      data: { name: '范围回归 B', mode: 'keyword' },
    })
  ).json()
  const upload = await (
    await page.request.post(`/api/knowledge/${a.id}/documents`, {
      headers,
      multipart: {
        files: {
          name: '流程.md',
          mimeType: 'text/markdown',
          buffer: Buffer.from('# 流程\n\n资料审核需要填写申请单，负责人批准后归档。'),
        },
      },
    })
  ).json()
  const doc = upload.items[0].document
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/knowledge/${a.id}/documents`)).json()).items[0].status,
    )
    .toBe('completed')
  const original = await page.request.get(`/api/knowledge/${a.id}/documents/${doc.id}/original`)
  expect(original.ok()).toBe(true)
  expect(await original.text()).toContain('申请单')

  await page.goto('/chat')
  const input = page.getByRole('textbox', { name: '输入问题' })
  await page.getByRole('combobox', { name: '选择知识库' }).press('Enter')
  await page.getByRole('option', { name: '范围回归 A', exact: true }).click()
  await input.fill('资料审核需要哪些步骤？')
  const stream = page.waitForResponse((response) => response.url().endsWith('/api/query/stream'))
  await input.press('Enter')
  expect((await stream).headers()['content-type']).toContain('text/event-stream')
  await page.getByRole('button', { name: '停止生成', exact: true }).click()
  await expect(input).toBeEnabled()
  const session = await page.evaluate(() => localStorage.getItem('rag-session'))
  const saved = await (await page.request.get(`/api/sessions/${session}`)).json()
  expect(saved.runs.at(-1).status).toBe('cancelled')
  expect(saved.runs.at(-1).request).toMatchObject({
    knowledge_base_id: a.id,
    search_scope: 'local',
    model_profile: 'default',
  })

  await page.reload()
  await expect(input).toHaveValue('资料审核需要哪些步骤？')
  await expect(page.getByRole('radio', { name: '本地知识', exact: true })).toBeChecked()
  await expect(page.locator('.kb-chat-select')).toContainText('范围回归 A')
  // A manual change is intentional: the retry must use the visible B selection.
  await page.getByRole('combobox', { name: '选择知识库' }).press('Enter')
  await page.getByRole('option', { name: '范围回归 B', exact: true }).click()
  const nextRequest = page.waitForRequest((request) => request.url().endsWith('/api/query/stream'))
  await input.press('Enter')
  expect((await nextRequest).postDataJSON().context.knowledge_base_id).toBe(b.id)
  await expect(input).toBeEnabled()
  const final = await (await page.request.get(`/api/sessions/${session}`)).json()
  const last = final.runs.at(-1)
  expect(last.status).toBe('success')
  expect(last.request.knowledge_base_id).toBe(b.id)
  expect(last.result.retrieval_plan.knowledge_base_id).toBe(b.id)
  const run = await (await page.request.get(`/api/runs/${last.id}`)).json()
  expect(run.result.answer).toBe(final.messages.at(-1).content)
  expect(run.result.source_map).toEqual(final.messages.at(-1).result.source_map)
  // Removing B preserves the unavailable ID; it must not become built-in project search.
  await page.request.delete(`/api/knowledge/${b.id}`, { headers })
  await page.reload()
  await expect(page.locator('.kb-chat-select')).toContainText('所选知识库不可用')
  expect(errors).toEqual([])
})

test('upload feedback stays with its library and document actions restore focus', async ({
  page,
}) => {
  const headers = { 'X-Workbench-Request': '1' }
  for (const name of ['上传回归 A', '上传回归 B'])
    await page.request.post('/api/knowledge', { headers, data: { name, mode: 'keyword' } })
  await page.goto('/knowledge')
  const libraryA = page.getByRole('button', { name: /上传回归 A/ })
  await libraryA.click()
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/knowledge/*/documents', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    const response = await route.fetch()
    await gate
    await route.fulfill({ response })
  })
  await page
    .locator('.kb-upload input[type=file]')
    .setInputFiles({
      name: '上传反馈.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('资料审批流程说明。'),
    })
  await expect(page.locator('.kb-upload')).toContainText('正在上传')
  await page.getByRole('button', { name: /上传回归 B/ }).click()
  await expect(page.locator('.kb-upload')).not.toContainText('正在上传')
  release()
  await expect(page.locator('.kb-upload button')).toBeEnabled()
  await expect(page.locator('.kb-feedback')).toHaveCount(0)
  await libraryA.click()
  await expect(page.locator('.kb-feedback')).toContainText(
    '知识库“上传回归 A”：已接收 上传反馈.txt',
  )
  const row = page.locator('.kb-table tbody tr').filter({ hasText: '上传反馈.txt' })
  await expect(row.locator('.kb-status')).toHaveText('可检索')
  await row.getByRole('button', { name: '重建', exact: true }).click()
  await expect(page.locator('.kb-feedback')).toContainText('后台任务')
  await expect(page.locator('.kb-upload')).not.toContainText('正在上传')
  await expect(page.locator('.kb-upload button')).toBeEnabled()
  await row.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '删除', exact: true }).last().click()
  await expect(row).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: '搜索文档名称' })).toBeFocused()
})
