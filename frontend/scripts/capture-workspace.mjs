// Capture actual product state. Model calls require the explicit opt-in below.
import { chromium, expect as baseExpect } from '@playwright/test'
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'

const baseURL = process.env.WORKBENCH_URL || 'http://127.0.0.1:8003'
const expect = baseExpect.configure({ timeout: 30000 })
const output = '../docs/screenshots'
mkdirSync(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
page.setDefaultTimeout(45000)
const errors = []
page.on('pageerror', error => errors.push(error.message))
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
const metrics = { date: new Date().toISOString(), errors, mockedResponses: false, viewports: [] }
const previous = existsSync(`${output}/workspace-metrics.json`) ? JSON.parse(readFileSync(`${output}/workspace-metrics.json`, 'utf8')) : {}
for (const key of ['managedProviderQueryMs', 'managedProviderResult']) if (previous[key]) metrics[key] = previous[key]
async function capture(name) {
  await expect(page.locator('.connection-line')).toHaveCount(0)
  await page.screenshot({ path: `${output}/${name}.png`, animations: 'disabled' })
}
try {
  await page.goto(`${baseURL}/chat`)
  await expect(page.getByRole('button', { name: '探索本地知识', exact: false })).toBeEnabled()
  await capture('workspace-chat')
  await page.goto(`${baseURL}/providers`)
  await expect(page.locator('.provider-item').first()).toBeVisible()
  if (process.env.AGENTICRAG_VERIFY_PROVIDER === '1') {
    await page.getByRole('button', { name: '检测连接 / 获取模型' }).first().click()
    await expect(page.locator('.provider-check-note').first()).toBeVisible()
    metrics.providerCheck = await page.locator('.provider-check-note').first().textContent()
  }
  metrics.providerCheck = await page.locator('.provider-check-note').first().textContent()
  await capture('workspace-providers')
  await page.getByRole('button', { name: /编辑 DeepSeek/ }).click()
  await expect(page.getByLabel('API Key', { exact: true })).toHaveValue('')
  await expect(page.locator('.el-overlay')).not.toHaveClass(/dialog-fade-enter-active/)
  await capture('workspace-provider-dialog')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  if (process.env.AGENTICRAG_REAL_SMOKE === '1') {
    await page.goto(`${baseURL}/chat`)
    await page.locator('.mode-select').click()
    await page.getByRole('option', {name:'快速回答',exact:true}).click()
    const input = page.getByRole('textbox', {name:'输入问题'})
    await input.fill('仅回复“连接正常”，不要添加其他内容。')
    const start = Date.now()
    await input.press('Enter')
    await expect(page.getByRole('button', { name: '停止生成', exact:true })).toBeVisible()
    await expect(input).toBeEnabled({timeout:120000})
    metrics.managedProviderQueryMs = Date.now()-start
    const sessionId = await page.evaluate(() => localStorage.getItem('rag-session'))
    const detail = await (await page.request.get(`${baseURL}/api/sessions/${sessionId}`)).json()
    metrics.managedProviderResult = {status:detail.runs.at(-1)?.status, profileIsManaged:detail.runs.at(-1)?.result?.model_profile?.startsWith('managed:')}
    expect(metrics.managedProviderResult.status).toBe('success')
    expect(metrics.managedProviderResult.profileIsManaged).toBe(true)
  }
  const runs = await (await page.request.get(`${baseURL}/api/runs?status=success`)).json()
  let evidenceRun
  for (const item of runs.items) {
    const detail = await (await page.request.get(`${baseURL}/api/runs/${item.id}`)).json()
    if (detail.result?.source_map?.length) { evidenceRun = detail; break }
  }
  if (evidenceRun) {
    await page.goto(`${baseURL}/runs?run=${evidenceRun.id}`)
    await expect(page.locator('.waterfall-row').first()).toBeVisible()
    await capture('workspace-runs')
    await page.getByRole('tab',{name:'证据来源'}).click()
    await expect(page.locator('.evidence-item').first()).toBeVisible()
    await capture('workspace-evidence')
    const download = page.waitForEvent('download')
    await page.getByRole('button',{name:'导出运行记录'}).click()
    metrics.exportDownloaded = !!(await download).suggestedFilename().endsWith('.json')
    await page.getByRole('button',{name:'回到会话'}).click()
    await expect(page.locator('.message.assistant .markdown').first()).toBeVisible()
    await page.getByRole('button',{name:'展开执行详情',exact:true}).click()
    await capture('workspace-answer')
    metrics.historyAnswerVisible = (await page.locator('.message.assistant .markdown').first().textContent()).length > 10
  }
  for (const path of ['tools','system']) {
    await page.goto(`${baseURL}/${path}`)
    await expect(page.locator(path === 'tools' ? '.tool-card' : '.model-table tbody tr').first()).toBeVisible()
    await capture(`workspace-${path}`)
  }
  await page.setViewportSize({width:390,height:844})
  for (const path of ['chat','providers','runs']) {
    await page.goto(`${baseURL}/${path}${path === 'runs' && evidenceRun ? `?run=${evidenceRun.id}` : ''}`)
    await expect(page.locator(path === 'chat' ? '.composer' : path === 'providers' ? '.provider-item' : '.run-question').first()).toBeVisible()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
    metrics.viewports.push({path,width:390,overflow})
    expect(overflow).toBe(false)
    await capture(`workspace-${path}-mobile`)
  }
  await page.setViewportSize({width:1440,height:1000})
  await page.goto(`${baseURL}/providers`)
  await page.getByRole('button',{name:'切换深色主题'}).click()
  await capture('workspace-dark')
  metrics.screenshots = 12
  expect(errors).toEqual([])
} finally {
  writeFileSync(`${output}/workspace-metrics.json`,JSON.stringify(metrics,null,2))
  await browser.close()
}
