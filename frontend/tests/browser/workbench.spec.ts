import { test, expect } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'

test('question, cancellation, retry, history, sources and responsive pages', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  await page.goto('/chat')
  const input = page.getByRole('textbox', { name: '输入问题' })
  await expect(page.getByRole('button', { name: '探索本地知识', exact: false })).toBeEnabled()
  await page.getByRole('radio', { name: '本地知识', exact: true }).check()
  await input.fill('请介绍智能问答系统的核心组成')
  await input.press('Enter')
  await expect(page.getByText('生成草稿', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '停止生成', exact: true }).click()
  await expect(input).toBeEnabled()
  await expect(input).toHaveValue('请介绍智能问答系统的核心组成')
  const started = Date.now()
  await input.press('Enter')
  await expect(page.getByText('生成草稿', { exact: true })).toBeVisible()
  const firstDeltaMs = Date.now() - started
  await expect(input).toBeEnabled({ timeout: 30000 })
  const sessionId = await page.evaluate(() => localStorage.getItem('rag-session'))
  const answer = page.locator('.message.assistant .markdown').last()
  const finalText = (await answer.textContent())!
  expect(finalText).toContain('夹具回答')
  await expect(page.locator('.answer-evidence-summary').last()).toContainText('本地 RAG')
  const savedResult = await (await page.request.get(`/api/sessions/${sessionId}`)).json()
  expect(savedResult.runs.at(-1).result.retrieval_plan.search_scope).toBe('local')
  expect(savedResult.runs.at(-1).result.timing.first_delta_ms).toBeGreaterThan(0)
  await page.getByRole('button', { name: '执行详情', exact: false }).last().click()
  await page.getByRole('tab', { name: /^来源/ }).click()
  await expect(page.locator('.source-card').first()).toBeVisible()
  await page.getByRole('tab', { name: /^执行过程/ }).click()
  await expect(page.locator('.timeline-item.success').first()).toBeVisible()
  mkdirSync('test-results/evidence', { recursive: true })
  await page.screenshot({ path: 'test-results/evidence/fixture-desktop.png', fullPage: true })
  await page.reload()
  await expect(page.locator('.message.assistant .markdown').last()).toHaveText(finalText)
  await page.getByRole('radio', { name: '自动', exact: true }).check()
  await input.fill('2+3')
  await input.press('Enter')
  await expect(input).toBeEnabled()
  await expect(page.locator('.message.assistant .markdown').last()).toContainText('5')
  await page.getByRole('link', { name: '运行分析', exact: true }).click()
  await expect(page.locator('.waterfall-row').first()).toBeVisible()
  await page.getByRole('tab', { name: '最终回答' }).click()
  await expect(page.locator('.run-answer .markdown')).toContainText('5')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.runs-index')).toBeHidden()
  await page.getByRole('button', { name: '返回运行列表' }).click()
  await expect(page.locator('.run-detail')).toBeHidden()
  await page.getByRole('textbox', { name: '搜索运行' }).fill('2+3')
  await expect(page.locator('.run-index-item')).toHaveCount(1)
  await page.locator('.run-index-item').click()
  await expect(page.getByRole('tab', { name: '最终回答' })).toBeVisible()
  await page.getByRole('button', { name: '返回运行列表' }).click()
  await expect(page.getByRole('textbox', { name: '搜索运行' })).toHaveValue('2+3')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('link', { name: '工具中心' }).click()
  await page.waitForURL('**/tools')
  await page.reload()
  await expect(page.locator('.tool-card').first()).toBeVisible()
  await page.getByRole('textbox', { name: '搜索工具', exact: true }).fill('calculator')
  await expect(page.locator('.tool-card')).toHaveCount(1)
  await page.getByRole('link', { name: '系统概览' }).click()
  await page.waitForURL('**/system')
  await page.reload()
  await expect(page.locator('.model-table tbody tr')).toHaveCount(1)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/chat')
  await expect(input).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('rag-session'))).toBe(sessionId)
  await expect(page.locator('.message.assistant')).toHaveCount(3)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  await page.screenshot({ path: 'test-results/evidence/fixture-mobile.png', fullPage: true })
  // Empty pages must not inherit message auto-follow, even when the welcome list overflows.
  await page.setViewportSize({ width: 320, height: 844 })
  await page.getByRole('link', { name: 'AgenticRAG', exact: true }).click()
  await expect(page.locator('.welcome h1')).toBeInViewport()
  await expect.poll(() => page.locator('.conversation-scroll').evaluate((el) => el.scrollTop)).toBe(0)
  await expect(input).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: 'test-results/evidence/fixture-welcome-320.png' })
  writeFileSync(
    'test-results/evidence/fixture-metrics.json',
    JSON.stringify({ fixture: true, firstDeltaMs, errors }, null, 2),
  )
  expect(errors).toEqual([])
})

test('provider form persists models without returning or caching credentials', async ({ page }) => {
  await page.goto('/providers')
  await page.getByRole('button', { name: '添加供应商', exact: true }).first().click()
  await page.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(page.locator('.form-error-summary')).toContainText('请修正')
  await page.getByLabel('供应商名称', { exact: true }).fill('隔离测试供应商')
  await page.getByLabel('服务基础地址', { exact: true }).fill('https://example.invalid/v1')
  await page.getByLabel('API Key', { exact: true }).fill('browser-fixture-not-a-real-key')
  await page.getByRole('textbox', { name: '模型 ID 1', exact: true }).fill('isolated-model')
  await page.getByRole('textbox', { name: '显示名称 1', exact: true }).fill('隔离模型')
  await page.route('**/api/settings/providers', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    await route.fulfill({ status: 422, json: { detail: [{ loc: ['body', 'models', 0, 'model_name'], type: 'string_pattern_mismatch', msg: 'invalid model' }] } })
  })
  await page.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(page.locator('.form-error-summary')).toContainText('格式不正确')
  await expect(page.getByLabel('API Key', { exact: true })).toHaveValue('browser-fixture-not-a-real-key')
  await page.unroute('**/api/settings/providers')
  await page.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(page.locator('.provider-item')).toContainText('隔离模型')
  await page.route('**/api/settings/providers/*/check', (route) => route.fulfill({ json: { ok: false, message: '模型列表访问失败，请检查凭据', models: [] } }))
  await page.getByRole('button', { name: '检测连接 / 获取模型' }).click()
  await expect(page.locator('.providers-page > .inline-error')).toContainText('模型列表访问失败')
  await expect(page.locator('.feedback-line')).toHaveCount(0)
  const response = await page.request.get('/api/settings/providers')
  expect(await response.text()).not.toContain('browser-fixture-not-a-real-key')
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('browser-fixture-not-a-real-key')
  await page.reload()
  await expect(page.locator('.provider-item')).toContainText('凭据已保存')
  await page.getByRole('button', { name: '编辑 隔离测试供应商' }).click()
  await expect(page.getByLabel('API Key', { exact: true })).toHaveValue('')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('button', { name: '移除 隔离测试供应商' }).click()
  await page.getByRole('button', { name: '移除', exact: true }).click()
  await expect(page.locator('.provider-item')).toHaveCount(0)
})

test('long history fixture: restore, scroll and type without automatic submission', async ({
  page,
}) => {
  const content =
    '## 历史长回答\n\n' +
    '这是用于测量浏览器渲染的本地长消息样本。'.repeat(120) +
    '\n```typescript\n' + Array.from({ length: 60 }, (_, i) => `const item${i}: string = 'isolated-code-line-${i}'`).join('\n') + '\n```'
  await page.addInitScript(() => {
    localStorage.setItem('rag-session', 'performance-fixture')
    const originalFetch = window.fetch
    window.fetch = async (...args) => {
      const response = await originalFetch(...args)
      if (response.url.endsWith('/api/sessions/performance-fixture')) {
        const parse = response.json.bind(response)
        response.json = async () => {
          const value = await parse()
          performance.mark('fixture-data-ready')
          return value
        }
      }
      return response
    }
    new PerformanceObserver((list) => {
      for (const task of list.getEntries())
        performance.mark('fixture-long-task', { startTime: task.startTime, detail: { duration: task.duration } })
    }).observe({ type: 'longtask', buffered: true })
    const observer = new MutationObserver(() => {
      if (document.querySelectorAll('.message.assistant .markdown').length !== 30) return
      observer.disconnect()
      performance.mark('fixture-dom-committed')
      requestAnimationFrame(() => requestAnimationFrame(() => {
        performance.mark('fixture-render-ready')
        performance.measure('fixture-render-window', 'fixture-data-ready', 'fixture-render-ready')
        performance.measure('fixture-vue-dom', 'fixture-data-ready', 'fixture-dom-committed')
      }))
    })
    observer.observe(document, { childList: true, subtree: true })
  })
  await page.route('**/api/sessions', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            session_id: 'performance-fixture',
            session_title: '长会话测量样本',
            preview: 'fixture',
            updated_at: 1,
            turn_count: 30,
          },
        ],
      },
    }),
  )
  await page.route('**/api/sessions/performance-fixture', (route) =>
    route.fulfill({
      json: {
        session_id: 'performance-fixture',
        session_title: '长会话测量样本',
        trace: [],
        runs: [],
        messages: Array.from({ length: 60 }, (_, i) => ({
          id: String(i),
          role: i % 2 ? 'assistant' : 'user',
          content: i % 2 ? content : `问题 ${i}`,
          timestamp: i,
          status: 'success',
        })),
      },
    }),
  )
  const start = Date.now()
  await page.goto('/chat')
  await expect(page.locator('.message')).toHaveCount(60)
  const historyReadyMs = Date.now() - start
  await page.waitForFunction(() => performance.getEntriesByName('fixture-render-window').length > 0)
  const rendering = await page.evaluate(() => ({
    vueDomMs: performance.getEntriesByName('fixture-vue-dom')[0]!.duration,
    renderWindowMs: performance.getEntriesByName('fixture-render-window')[0]!.duration,
    longTasks: performance.getEntriesByName('fixture-long-task').map((entry) => ({
      start: entry.startTime, duration: (entry as PerformanceMark).detail.duration,
    })),
  }))
  const input = page.getByRole('textbox', { name: '输入问题' })
  const typingStart = Date.now()
  await input.fill('长会话仍可编辑')
  await expect(input).toHaveValue('长会话仍可编辑')
  const inputMs = Date.now() - typingStart
  await page.locator('.conversation-scroll').evaluate((el) => {
    el.scrollTop = 0
    el.dispatchEvent(new Event('scroll'))
  })
  await expect(page.getByRole('button', { name: '回到底部' })).toBeVisible()
  await page.getByRole('button', { name: '回到底部' }).click()
  const scrollFrameMs = await page.locator('.conversation-scroll').evaluate(async (el) => {
    const started = performance.now()
    el.scrollTop = el.scrollHeight
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
    return performance.now() - started
  })
  expect(await page.locator('.conversation-scroll').evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(100)
  mkdirSync('test-results/evidence', { recursive: true })
  writeFileSync(
    'test-results/evidence/history-metrics.json',
    JSON.stringify(
      { fixture: true, messages: 60, codeLinesPerAnswer: 60, answerCharacters: content.length, historyReadyMs, inputMs, scrollFrameMs, ...rendering, browser: await page.evaluate(() => navigator.userAgent) },
      null,
      2,
    ),
  )
})
