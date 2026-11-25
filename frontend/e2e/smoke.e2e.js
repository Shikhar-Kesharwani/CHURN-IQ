// CHURN-55: browser smoke tests for the four main journeys, run against a real
// uvicorn backend (see playwright.config.js).
//
// Expected values are read from the same backend during the test, never
// hard-coded, so the tests stay valid when the model or data changes. No test
// calls Gemini or sends an email.
import { test, expect } from '@playwright/test'
import { API } from '../playwright.config.js'

const CUSTOMER = 'CUST00001'
const fmtInt = (n) => n.toLocaleString('en-US')

async function apiGet(request, path) {
  const r = await request.get(`${API}${path}`)
  expect(r.status(), path).toBe(200)
  return r.json()
}

// Fail any test whose page throws or logs an error.
test.beforeEach(async ({ page }, testInfo) => {
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  testInfo.errors_ = errors
})
test.afterEach(async ({}, testInfo) => {
  expect(testInfo.errors_, 'browser console / page errors').toEqual([])
})

test('Dashboard loads its KPIs from the API', async ({ page, request }) => {
  const { kpis } = await apiGet(request, '/dashboard/summary')
  await page.goto('/')
  await expect(page.getByText('API connected')).toBeVisible()
  await expect(page.getByTestId('kpi-Total Customers')).toHaveText(fmtInt(kpis.total_customers))
  await expect(page.getByTestId('kpi-High Risk Count')).toHaveText(fmtInt(kpis.high_risk_count))
  await expect(page.getByTestId('kpi-Revenue at Risk / mo')).toHaveText(kpis.revenue_at_risk_formatted)
  await expect(page.getByTestId('kpi-Avg Churn Probability')).toHaveText(kpis.avg_churn_percent)
})

test('Risk Table opens Customer Detail', async ({ page, request }) => {
  const customer = await apiGet(request, `/customer/${CUSTOMER}`)
  await page.goto('/risk')
  await page.getByRole('searchbox', { name: 'Search by customer name or ID' }).fill(CUSTOMER)
  await page.getByRole('link', { name: new RegExp(`\\(${CUSTOMER}\\)`) }).click()

  await expect(page).toHaveURL(new RegExp(`/risk/${CUSTOMER}$`))
  await expect(page.getByText(CUSTOMER, { exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: `Churn risk ${Math.round(customer.churn_prob * 100)}%` })).toBeVisible()
  await expect(page.getByTestId('profile-Plan')).toHaveText(customer.plan_type)
})

test('What-If returns a prediction', async ({ page }) => {
  await page.goto(`/risk/${CUSTOMER}`)
  await page.locator('#wi-watch_hours_per_week').fill('40')

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url() === `${API}/whatif` && r.request().method() === 'POST'),
    page.getByRole('button', { name: 'Recalculate Churn' }).click(),
  ])
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.customer_id).toBe(CUSTOMER)
  expect(JSON.parse(response.request().postData()).watch_hours_per_week).toBe(40)

  const result = page.getByTestId('whatif-result')
  await expect(result).toBeVisible()
  await expect(result).toContainText(`${Math.round(body.original_churn_prob * 100)}%`)
  await expect(result).toContainText(`${Math.round(body.new_churn_prob * 100)}%`)
  await expect(result).toContainText(body.new_risk)
})

test('Similarity returns neighbours', async ({ page }) => {
  await page.goto('/similarity')
  await page.getByRole('textbox', { name: 'Customer ID' }).fill(CUSTOMER)

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url() === `${API}/api/customer-similarity` && r.request().method() === 'POST'),
    page.getByRole('button', { name: 'Find Similar Customers' }).click(),
  ])
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.selected_customer.customer_id).toBe(CUSTOMER)
  expect(body.similar_customers.length).toBeGreaterThan(0)

  for (const n of body.similar_customers) {
    expect(n.customer_id).not.toBe(CUSTOMER)
    await expect(page.getByRole('row').filter({ hasText: n.customer_id }).first()).toBeVisible()
  }
})
