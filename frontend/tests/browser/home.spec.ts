import { test, expect } from '@playwright/test'

test('home visual controls, responsive entry and retained running conversation', async ({
  page,
}) => {
  const errors: string[] = []
  const apiRequests: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url())
  })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('AgenticRAG')
  await page.evaluate(() => document.fonts.ready)
  expect(apiRequests).toEqual([])
  expect(
    await page.evaluate(() =>
      performance
        .getEntriesByType('resource')
        .some((entry) => /\/assets\/(?:WorkbenchLayout|workbench)-.*\.js/.test(entry.name)),
    ),
  ).toBe(false)
  await expect(page.locator('.knowledge-field')).toHaveAttribute('data-renderer', 'webgl')
  await expect(page.getByRole('button', { name: '继续动效', exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/home-desktop.png', fullPage: true })
  await page.getByRole('button', { name: '展开光流', exact: true }).click()
  await expect(page.getByRole('button', { name: '聚合光流', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('button', { name: '继续动效', exact: true }).click()
  await expect(page.getByRole('button', { name: '暂停动效', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '暂停动效', exact: true }).click()
  await page.screenshot({ path: 'test-results/home-expanded.png', fullPage: true })
  await page.getByRole('button', { name: '聚合光流', exact: true }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: 'test-results/home-mobile.png', fullPage: true })
  await page.setViewportSize({ width: 320, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  await expect(page.getByRole('link', { name: '进入工作台', exact: true })).toBeInViewport()
  expect(apiRequests).toEqual([])

  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('link', { name: '进入工作台', exact: true }).click()
  const input = page.getByRole('textbox', { name: '输入问题' })
  await expect(page.getByRole('button', { name: '探索本地知识', exact: false })).toBeEnabled()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.screenshot({ path: 'test-results/workbench-dark-default.png', fullPage: true })
  // Exercise the actual wheel path, including navigation outside the history list.
  await page.setViewportSize({ width: 1440, height: 560 })
  const sidebar = page.locator('.sidebar-scroll')
  const newChat = page.locator('.new-chat-button')
  const navigation = page.getByRole('navigation', { name: '主导航', exact: true })
  const pinnedTop = await newChat.evaluate((element) => element.getBoundingClientRect().top)
  const navigationTop = await navigation.evaluate((element) => element.getBoundingClientRect().top)
  await sidebar.hover()
  await page.mouse.wheel(0, 460)
  await expect.poll(() => sidebar.evaluate((element) => element.scrollTop)).toBeGreaterThan(100)
  expect(await newChat.evaluate((element) => element.getBoundingClientRect().top)).toBe(pinnedTop)
  expect(await navigation.evaluate((element) => element.getBoundingClientRect().top)).toBeLessThan(
    navigationTop - 100,
  )
  await page.screenshot({ path: 'test-results/sidebar-scroll.png', fullPage: true })
  await newChat.focus()
  await expect(newChat).toBeInViewport()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: '切换浅色主题', exact: true }).click()
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: '切换深色主题', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await input.fill('保留这份未发送草稿')
  await page.getByRole('link', { name: '产品主页', exact: true }).click()
  await page.getByRole('link', { name: '进入工作台', exact: true }).click()
  await expect(input).toHaveValue('保留这份未发送草稿')
  await page.getByRole('radio', { name: '本地知识', exact: true }).check()
  await input.fill('请介绍智能问答系统的核心组成')
  await input.press('Enter')
  await expect(page.getByText('生成草稿', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: '产品主页', exact: true }).click()
  await page.getByRole('link', { name: '进入工作台', exact: true }).click()
  await expect(input).toBeEnabled()
  await expect(page.locator('.message.assistant .markdown').last()).toContainText('夹具回答')
  expect(apiRequests.filter((url) => url.includes('/cancel'))).toEqual([])
  expect(errors).toEqual([])
})
