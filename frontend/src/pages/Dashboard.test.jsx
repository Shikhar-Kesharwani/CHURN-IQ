// CHURN-26: every dashboard value comes from the API; no invented fallbacks.
import { describe, it, expect } from 'vitest'
import { screen, within, fireEvent } from '@testing-library/react'
import Dashboard, { weightedAvgClv, fmtInt } from './Dashboard'
import { mockFetch, renderAt, networkDown } from '../test/helpers'
import dashboard from '../test/fixtures/dashboard.json'
import segments from '../test/fixtures/segments.json'

const kpi = (label) => screen.getByTestId(`kpi-${label}`).textContent

describe('Dashboard KPIs match GET /dashboard/summary', () => {
  it('shows each KPI exactly as the API reports it', async () => {
    mockFetch({ '/dashboard/summary': dashboard, '/segments': segments })
    renderAt(<Dashboard />)
    await screen.findByText('Total Customers')
    const k = dashboard.kpis
    expect(kpi('Total Customers')).toBe(k.total_customers.toLocaleString('en-US'))          // "5,001"
    expect(kpi('High Risk Count')).toBe(k.high_risk_count.toLocaleString('en-US'))          // "1,201"
    expect(kpi('Revenue at Risk / mo')).toBe(k.revenue_at_risk_formatted)                   // "₹941,958"
    expect(kpi('Avg Churn Probability')).toBe(k.avg_churn_percent)                          // "44.8%"
    expect(screen.getByText(`${k.high_risk_pct}% of scored · ≥70% churn probability`)).toBeInTheDocument()
  })

  it('shows CLV from /segments: plan-weighted average and tier counts', async () => {
    mockFetch({ '/dashboard/summary': dashboard, '/segments': segments })
    renderAt(<Dashboard />)
    const avg = weightedAvgClv(segments.by_plan)
    expect(await screen.findByTestId('clv-Avg CLV')).toHaveTextContent(`₹${Math.round(avg).toLocaleString('en-US')}`)
    for (const tier of segments.by_clv) {
      expect(screen.getByTestId(`clv-${tier.clv_segment} CLV tier`)).toHaveTextContent(fmtInt(tier.count))
    }
  })

  it('never shows the old hard-coded numbers', async () => {
    mockFetch({ '/dashboard/summary': dashboard, '/segments': segments })
    const { container } = renderAt(<Dashboard />)
    await screen.findByText('Total Customers')
    for (const fake of ['₹1,91,150', '43.1%', '₹6,322', '₹3,844', '₹8,132']) {
      expect(container.textContent).not.toContain(fake)
    }
  })

  it('labels the API trend as simulated', async () => {
    mockFetch({ '/dashboard/summary': dashboard, '/segments': segments })
    renderAt(<Dashboard />)
    expect(await screen.findByText('Monthly Churn Trend (simulated)')).toBeInTheDocument()
    expect(screen.getByText(/not observed data/)).toBeInTheDocument()
  })

  it('shows a genuine 0 as 0 and missing values as "—" (no made-up defaults)', async () => {
    const zero = {
      ...dashboard,
      kpis: { ...dashboard.kpis, high_risk_count: 0, high_risk_pct: 0, avg_churn_percent: null, revenue_at_risk_formatted: undefined },
      priority_customers: [],
    }
    mockFetch({ '/dashboard/summary': zero, '/segments': segments })
    renderAt(<Dashboard />)
    await screen.findByText('Total Customers')
    expect(kpi('High Risk Count')).toBe('0')
    expect(kpi('Avg Churn Probability')).toBe('—')
    expect(kpi('Revenue at Risk / mo')).toBe('—')
  })

  it('links priority customers to their detail page with the API risk level', async () => {
    mockFetch({ '/dashboard/summary': dashboard, '/segments': segments })
    renderAt(<Dashboard />)
    const first = dashboard.priority_customers[0]
    const link = await screen.findByRole('link', { name: first.customer_id })
    expect(link).toHaveAttribute('href', `/risk/${first.customer_id}`)
    const row = link.closest('tr')
    expect(within(row).getByText(first.churn_pct)).toBeInTheDocument()
    expect(within(row).getByText(first.risk_level)).toBeInTheDocument()
  })
})

describe('Dashboard failure states', () => {
  it('shows an error with Retry, and no figures, when the backend is down', async () => {
    const f = mockFetch({ '/dashboard/summary': networkDown(), '/segments': networkDown() })
    renderAt(<Dashboard />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the ChurnIQ API')
    expect(screen.queryByText('Total Customers')).not.toBeInTheDocument()
    expect(screen.queryByText('5,000')).not.toBeInTheDocument()

    // Retry re-requests the summary
    const before = f.mock.calls.length
    mockFetch({ '/dashboard/summary': dashboard, '/segments': segments })
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByText('Total Customers')).toBeInTheDocument()
    expect(before).toBeGreaterThan(0)
  })

  it('keeps the KPIs when only /segments fails, and marks the segment charts as failed', async () => {
    mockFetch({ '/dashboard/summary': dashboard, '/segments': new Response('err', { status: 500 }) })
    renderAt(<Dashboard />)
    await screen.findByText('Total Customers')
    expect(kpi('Total Customers')).toBe('5,001')
    expect((await screen.findAllByText('Segment data could not be loaded')).length).toBeGreaterThan(0)
  })
})

describe('weightedAvgClv', () => {
  it('weights each plan average by its customer count', () => {
    expect(weightedAvgClv([{ avg_clv: 100, count: 1 }, { avg_clv: 400, count: 3 }])).toBe(325)
    expect(weightedAvgClv([])).toBeNull()
    expect(weightedAvgClv([{ avg_clv: null, count: 2 }])).toBeNull()
  })
})
