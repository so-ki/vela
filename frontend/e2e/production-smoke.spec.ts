import { expect, test } from '@playwright/test'

test('production SPA loads, authenticates, and reaches the business workbench', async ({ page }) => {
  const pageErrors: string[] = []
  const serverFailures: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('response', (response) => {
    if (response.status() >= 500) {
      serverFailures.push(`${response.status()} ${response.url()}`)
    }
  })

  await page.goto('/')
  await expect(page).toHaveTitle('Vela 出海法务平台')
  await expect(page.getByRole('heading', { name: 'Vela 出海法务平台' })).toBeVisible()

  await page.getByLabel('邮箱').fill('biz@demo.vela')
  await page.getByLabel('密码').fill('Demo1234!')
  await page.getByRole('button', { name: '登录', exact: true }).click()

  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: '欢迎，演示业务' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '提交新协查' })).toBeVisible()
  await expect(page.getByText('页面加载出错')).toHaveCount(0)
  expect(pageErrors).toEqual([])
  expect(serverFailures).toEqual([])
})
