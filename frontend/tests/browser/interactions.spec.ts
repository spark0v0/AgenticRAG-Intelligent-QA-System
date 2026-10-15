import { test, expect } from '@playwright/test'
import type { QueryResult, Source } from '../../src/types'

test.use({ actionTimeout: 10000 })

test('reading controls keep copy feedback local, resize drafts and contain mobile details', async ({
  page,
  context,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const code = `const question = '${'用于检查横向代码滚动的文本'.repeat(12)}'\n`
  const content = `这里是一段可核对的回答 [S1]。\n\n\`\`\`typescript\n${code}\`\`\``
  const source: Source = {
    citation_id: 'S1',
    source: '交互说明.md',
    excerpt: '隔离夹具中的原文证据。',
    document_id: 'doc',
    knowledge_base_id: 'kb',
    chunk_id: 'chunk',
    version: 'v1',
  }
  const result: QueryResult = {
    answer: content,
    session_id: 'reading-fixture',
    run_id: 'reading-run',
    sources: [source.source],
    source_map: [source],
  }
  await page.addInitScript(() => localStorage.setItem('rag-session', 'reading-fixture'))
  await page.route('**/api/sessions?*', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            session_id: 'reading-fixture',
            session_title: '阅读交互检查',
            turn_count: 1,
            updated_at: 2,
            preview: '隔离夹具',
          },
        ],
      },
    }),
  )
  await page.route('**/api/sessions/reading-fixture', (route) =>
    route.fulfill({
      json: {
        session_id: result.session_id,
        session_title: '阅读交互检查',
        trace: [],
        runs: [],
        messages: [
          {
            id: 'question',
            role: 'user',
            content: '请说明代码与引用的使用方式',
            run_id: result.run_id,
            timestamp: 1,
          },
          {
            id: 'answer',
            role: 'assistant',
            content,
            run_id: result.run_id,
            timestamp: 2,
            status: 'success',
            result,
          },
        ],
      },
    }),
  )
  await page.route('**/evidence/chunk', (route) =>
    route.fulfill({ json: { original_available: false, version: 'v1' } }),
  )
  await page.goto('/chat')
  const input = page.getByRole('textbox', { name: '输入问题' })
  await expect(input).toBeEnabled()
  const initialHeight = await input.evaluate((el) => el.clientHeight)
  await input.fill(Array.from({ length: 12 }, (_, i) => `补充说明 ${i}`).join('\n'))
  await expect.poll(() => input.evaluate((el) => el.clientHeight)).toBeGreaterThan(initialHeight)
  expect(await input.evaluate((el) => el.clientHeight)).toBeLessThanOrEqual(180)
  await input.fill('简短问题')
  await expect.poll(() => input.evaluate((el) => el.clientHeight)).toBe(initialHeight)
  const block = page.locator('.code-block')
  const copy = block.getByRole('button', { name: '复制代码' })
  await copy.click()
  await expect(copy).toHaveText('已复制')
  // Windows clipboard normalizes line endings to CRLF.
  expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n')).toBe(
    code,
  )
  await block.locator('pre').evaluate((el) => {
    el.scrollLeft = el.scrollWidth
  })
  await expect(copy).toBeInViewport()
  await page.setViewportSize({ width: 390, height: 844 })
  const citation = page.getByRole('button', { name: '查看来源 S1' })
  await citation.click()
  const drawer = page.getByRole('dialog', { name: '执行详情', exact: true })
  await expect(drawer).toBeVisible()
  await expect(drawer.locator('.run-summary-question')).toHaveText('请说明代码与引用的使用方式')
  const sourcesTab = drawer.getByRole('tab', { name: /^来源/ })
  await expect(sourcesTab).toHaveAttribute('aria-selected', 'true')
  await sourcesTab.press('ArrowRight')
  await expect(drawer.getByRole('tab', { name: /^工具/ })).toBeFocused()
  await page.keyboard.press('Home')
  await expect(drawer.getByRole('tab', { name: /^执行过程/ })).toBeFocused()
  await page.keyboard.press('ArrowLeft')
  await expect(drawer.getByRole('tab', { name: /^工具/ })).toBeFocused()
  await drawer.getByRole('button', { name: '收起执行详情' }).press('Shift+Tab')
  await expect(drawer.getByRole('tabpanel')).toBeFocused()
  await sourcesTab.click()
  await drawer.getByRole('button', { name: '查看证据与原文' }).click()
  const evidence = page.getByRole('dialog', { name: '文档证据' })
  await expect(evidence).toContainText('原文已删除')
  await page.keyboard.press('Escape')
  await expect(evidence).toBeHidden()
  await expect(drawer).toBeVisible()
  await expect(drawer.getByRole('button', { name: '查看证据与原文' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(citation).toBeFocused()
  await citation.click()
  await expect(drawer).toBeVisible()
  await page.setViewportSize({ width: 1440, height: 960 })
  await expect(drawer).toHaveCount(0)
  await expect(citation).toBeFocused()
  await page.setViewportSize({ width: 320, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  expect(errors).toEqual([])
})

test('mobile navigation contains focus, closes on the current route and survives resizing', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/chat')
  await expect(page.getByRole('textbox', { name: '输入问题' })).toBeEnabled()
  await page.getByRole('button', { name: '打开导航' }).click()
  const navigation = page.locator('#workspace-navigation')
  await navigation.locator('.environment-card').press('Tab')
  await expect(navigation.getByRole('button', { name: '收起导航' })).toBeFocused({ timeout: 3000 })
  await page.keyboard.press('Shift+Tab')
  await expect(navigation.locator('.environment-card')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: '打开导航' })).toBeFocused()
  await page.getByRole('button', { name: '打开导航' }).click()
  await navigation.getByRole('link', { name: '智能问答', exact: true }).click()
  await expect(navigation).toBeHidden()
  await expect(page.locator('#workspace-content')).toBeFocused()
  await expect(page.getByRole('button', { name: '上传图片', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '打开导航' }).click()
  await navigation.getByRole('link', { name: '工具中心', exact: true }).click()
  await expect(page.locator('#workspace-content')).toBeFocused()
  await page.getByRole('button', { name: '打开导航' }).click()
  await page.setViewportSize({ width: 1440, height: 960 })
  await expect(page.locator('.app-main')).not.toHaveAttribute('inert')
  await page.setViewportSize({ width: 320, height: 844 })
  await expect(navigation).toBeHidden()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
})

test('history refresh feedback stays in the sidebar and search can be cleared', async ({
  page,
}) => {
  await page.goto('/chat')
  await expect(page.locator('.service-status')).toHaveText('服务已连接')
  await page.route('**/api/sessions?*', (route) =>
    route.fulfill({
      status: 503,
      json: { detail: '历史记录暂时不可用' },
    }),
  )
  await page.getByRole('button', { name: '刷新历史会话' }).click()
  await expect(page.locator('.sidebar [role=alert]')).toContainText('历史记录暂时不可用', {
    timeout: 3000,
  })
  await expect(page.locator('.global-error')).toHaveCount(0)
  await expect(page.locator('.service-status')).toHaveText('服务已连接')
  await page.unroute('**/api/sessions?*')
  await page.getByRole('button', { name: '刷新历史会话' }).click()
  await expect(page.locator('.sidebar [role=alert]')).toHaveCount(0)
  const search = page.getByRole('textbox', { name: '搜索历史会话' })
  await search.fill('不存在的会话')
  await expect(page.locator('.sidebar-empty')).toContainText('没有匹配的会话')
  await page.getByRole('button', { name: '清除会话搜索' }).click()
  await expect(search).toHaveValue('')
  await expect(search).toBeFocused()
})

test('knowledge creation shows errors inside the dialog and does not duplicate after a list failure', async ({
  page,
}) => {
  await page.goto('/knowledge')
  await expect(page.getByRole('button', { name: '创建知识库', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '创建知识库', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '创建知识库' })
  await page.getByLabel('知识库名称', { exact: true }).fill('交互检查资料库')
  await page.route('**/api/knowledge', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 503, json: { detail: '创建暂时不可用，请重试' } })
      : route.continue(),
  )
  await dialog.getByRole('button', { name: '创建知识库', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('创建暂时不可用', { timeout: 3000 })
  await expect(dialog.getByRole('alert')).toBeFocused()
  await expect(page.getByLabel('知识库名称', { exact: true })).toHaveValue('交互检查资料库')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog).toBeHidden()
  await page.getByRole('button', { name: '创建知识库', exact: true }).click()
  await expect(dialog.getByRole('alert')).toHaveCount(0)
  await page.getByRole('combobox', { name: '检索方式' }).press('Enter')
  await page.getByRole('option', { name: '仅关键词（无需模型）' }).click()
  await page.unroute('**/api/knowledge')
  let creates = 0
  await page.route('**/api/knowledge', async (route) => {
    if (route.request().method() === 'POST') {
      creates++
      return route.continue()
    }
    await route.fulfill({ status: 503, json: { detail: '列表读取失败' } })
  })
  await dialog.getByRole('button', { name: '创建知识库', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(page.locator('.kb-library-heading h2')).toHaveText('交互检查资料库')
  expect(creates).toBe(1)
  const search = page.getByRole('textbox', { name: '搜索文档名称' })
  await search.fill('不存在的文档')
  await expect(page.locator('.kb-empty')).toContainText('没有匹配的文档')
  await page.getByRole('button', { name: '清除筛选' }).click()
  await expect(search).toHaveValue('')
  await expect(search).toBeFocused()
  await expect(page.locator('.kb-empty')).toContainText('从第一份资料开始')
})
