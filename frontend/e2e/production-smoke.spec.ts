import { expect, test, type Page } from '@playwright/test'

const scenarioId = process.env.VELA_E2E_SCENARIO_ID

function observeBrowserFailures(page: Page) {
  const pageErrors: string[] = []
  const serverFailures: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('response', (response) => {
    if (response.status() >= 500) {
      serverFailures.push(`${response.status()} ${response.url()}`)
    }
  })
  return { pageErrors, serverFailures }
}

async function login(page: Page, email: string) {
  await page.goto('/')
  await expect(page).toHaveTitle('Vela 出海法务平台')
  await expect(page.getByRole('heading', { name: 'Vela 出海法务平台' })).toBeVisible()
  await page.getByLabel('邮箱').fill(email)
  await page.getByLabel('密码').fill('Demo1234!')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
}

test('business authenticates and reaches the formal intake workbench', async ({ page }) => {
  const failures = observeBrowserFailures(page)

  await login(page, 'biz@demo.vela')
  await expect(page.getByRole('heading', { name: '欢迎，演示业务' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '提交新协查' })).toBeVisible()
  await expect(page.getByText('页面加载出错')).toHaveCount(0)
  expect(failures.pageErrors).toEqual([])
  expect(failures.serverFailures).toEqual([])
})

test('legal reads all eight finalist pages from the preserved formal scenario', async ({ page }) => {
  test.skip(!scenarioId, 'VELA_E2E_SCENARIO_ID is required')
  const failures = observeBrowserFailures(page)

  await login(page, 'legal@demo.vela')
  await expect(page.getByRole('heading', { name: '欢迎，演示法务' })).toBeVisible()
  await page.goto(`/competition/${scenarioId}/overview`)
  await expect(page.getByText('LIVE SCENARIO API')).toBeVisible()
  await expect(page.getByRole('heading', { name: /Vela 是面向中国企业法务/ })).toBeVisible()
  for (const section of [
    '项目总览',
    '材料与事实',
    '固定 30 项',
    '法律研究',
    'Claim 与缺口',
    'CoverageProof',
    '交付中心',
    '审计记录',
  ]) {
    await expect(page.getByRole('link', { name: new RegExp(section) })).toBeVisible()
  }
  await page.getByRole('link', { name: /交付中心/ }).click()
  await expect(page.getByText('blocked_external').first()).toBeVisible()
  await page.getByRole('link', { name: /审计记录/ }).click()
  await expect(page.getByText('mechanism.claim_compile').first()).toBeVisible()
  expect(failures.pageErrors).toEqual([])
  expect(failures.serverFailures).toEqual([])
})

test('admin authenticates and reaches independent release controls', async ({ page }) => {
  test.skip(!scenarioId, 'VELA_E2E_SCENARIO_ID is required')
  const failures = observeBrowserFailures(page)

  await login(page, 'admin@demo.vela')
  await expect(page.getByRole('heading', { name: '欢迎，Finalist Admin' })).toBeVisible()
  await expect(page.getByRole('banner').getByText('系统管理员')).toBeVisible()
  await page.goto(`/scenarios/${scenarioId}/delivery-assurance`)
  await expect(page.getByRole('heading', { name: '客户交付证据台' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '创建限时客户交付 release' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '当前禁止客户交付' })).toBeVisible()
  expect(failures.pageErrors).toEqual([])
  expect(failures.serverFailures).toEqual([])
})
