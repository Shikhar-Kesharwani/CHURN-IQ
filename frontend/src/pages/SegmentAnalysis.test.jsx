// CHURN-53: every figure and claim on the Segments page comes from GET /segments.
import { describe, it, expect } from 'vitest'
import { screen, within, fireEvent } from '@testing-library/react'
import SegmentAnalysis, { buildInsights, revenueByPlan, fmtRupees, tenureLabel, TENURE_LABELS, METRIC_LABEL } from './SegmentAnalysis'
import { mockFetch, renderAt, networkDown, jsonResponse } from '../test/helpers'
import segments from '../test/fixtures/segments.json'

// The constants that used to be hard-coded on this page (before CHURN-53).
const OLD_HARD_CODED = [
  '₹285K', '₹456K', '₹178K',
  'Mobile users show 15% higher churn than Smart TV users.',
  'New users (0–3 months) have the highest churn rate at 72%.',
  'Users with payment issues churn 2× more than those without.',
  'Romance and Drama genre viewers show highest churn rates.',
  'Premium plan users churn 3.7% less than Basic plan users.',
]

describe('Segments page: loading and error states', () => {
  it('shows a loading indicator while the request is pending', async () => {
    let release
    mockFetch({ '/segments': () => new Promise(r => { release = () => r(jsonResponse(segments)) }) })
    renderAt(<SegmentAnalysis />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading segments…')
    release()
    expect(await screen.findByText('Segment Analysis')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows an error with Retry and no figures when the backend is down, then recovers', async () => {
    mockFetch({ '/segments': networkDown() })
    const { container } = renderAt(<SegmentAnalysis />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Segment data could not be loaded')
    expect(screen.getByRole('alert')).toHaveTextContent('Cannot reach the ChurnIQ API')
    expect(screen.queryByText('Insights from the data')).not.toBeInTheDocument()
    expect(container.textContent).not.toMatch(/₹\d/)

    mockFetch({ '/segments': segments })
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByText('Insights from the data')).toBeInTheDocument()
  })

  it('shows the API error message for an HTTP failure', async () => {
    mockFetch({ '/segments': jsonResponse({ detail: 'Segments are temporarily unavailable.' }, 503) })
    renderAt(<SegmentAnalysis />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Segments are temporarily unavailable.')
  })
})

describe('Segments page: data state', () => {
  it('never shows the old hard-coded revenue figures or insight claims', async () => {
    mockFetch({ '/segments': segments })
    const { container } = renderAt(<SegmentAnalysis />)
    await screen.findByText('Insights from the data')
    for (const fake of OLD_HARD_CODED) expect(container.textContent).not.toContain(fake)
  })

  it('shows per-plan revenue at risk exactly as the API reports it', async () => {
    mockFetch({ '/segments': segments })
    renderAt(<SegmentAnalysis />)
    await screen.findByText('Monthly Revenue at Risk by Plan')
    for (const p of segments.by_plan) {
      const tile = screen.getByTestId(`revenue-${p.plan_type}`)
      expect(tile).toHaveTextContent(p.plan_type)
      expect(tile).toHaveTextContent(fmtRupees(p.revenue_at_risk))
    }
    expect(screen.getByTestId('revenue-Standard')).toHaveTextContent('₹407,730')
    expect(screen.getByTestId('revenue-total')).toHaveTextContent('₹941,958')
  })

  it('says revenue by plan is unavailable instead of inventing it', async () => {
    const noRevenue = { ...segments, by_plan: segments.by_plan.map(({ revenue_at_risk, ...p }) => p) }
    mockFetch({ '/segments': noRevenue })
    renderAt(<SegmentAnalysis />)
    expect(await screen.findByTestId('revenue-unavailable')).toBeInTheDocument()
    expect(screen.queryByTestId('revenue-Basic')).not.toBeInTheDocument()
    expect(screen.getByTestId('revenue-total')).toHaveTextContent('₹941,958')
  })

  it('lists the insights computed from the response', async () => {
    mockFetch({ '/segments': segments })
    renderAt(<SegmentAnalysis />)
    const list = await screen.findByTestId('insights')
    const items = within(list).getAllByRole('listitem').map(li => li.textContent)
    expect(items).toHaveLength(5)
    expect(items.join(' ')).toContain('customers with tenure 1–3 months have the highest average predicted churn probability (73.2%)')
    expect(items.join(' ')).toContain('Average predicted churn probability across 5,001 scored customers: 44.8%.')
  })

  it('compares each genre with the API average instead of a fixed threshold', async () => {
    mockFetch({ '/segments': segments })
    renderAt(<SegmentAnalysis />)
    await screen.findByText(`vs Average (${segments.overall.avg_churn_rate_pct}%)`)
    for (const g of segments.by_genre) {
      const row = screen.getByText(g.preferred_genre).closest('tr')
      const expected = g.churn_rate_pct > segments.overall.avg_churn_rate_pct ? 'Above' : 'At or below'
      expect(within(row).getByText(expected)).toBeInTheDocument()
      expect(within(row).getByText(`${g.churn_rate_pct}%`)).toBeInTheDocument()
    }
  })
})

describe('buildInsights / revenueByPlan', () => {
  it('derives highest and lowest per grouping from the fixture', () => {
    const ins = buildInsights(segments)
    expect(ins[0]).toBe('Tenure: customers with tenure 1–3 months have the highest average predicted churn probability (73.2%), 38.4 points above customers with tenure 25+ months (34.8%).')
    expect(ins[1]).toBe('Device: Tablet users have the highest average predicted churn probability (46.9%), 6.9 points above Laptop users (40%).')
    expect(ins[2]).toBe('Plan: Standard plan customers have the highest average predicted churn probability (45.5%), 2.9 points above Premium plan customers (42.6%).')
    expect(ins[3]).toMatch(/^Preferred genre: Documentary viewers have the highest average predicted churn probability \(48\.8%\)/)
  })

  it('follows the data when it changes', () => {
    const flipped = { by_device: [
      { device_type: 'Mobile', churn_rate_pct: 70 },
      { device_type: 'Laptop', churn_rate_pct: 10 },
    ] }
    expect(buildInsights(flipped)).toEqual([
      'Device: Mobile users have the highest average predicted churn probability (70%), 60 points above Laptop users (10%).',
    ])
  })

  it('skips groups without at least two usable rates and ignores null rates', () => {
    const sparse = {
      by_plan: [{ plan_type: 'Basic', churn_rate_pct: 40 }],
      by_device: [
        { device_type: 'Mobile', churn_rate_pct: null },
        { device_type: 'Tablet', churn_rate_pct: 50 },
        { device_type: 'Laptop', churn_rate_pct: 30 },
      ],
      overall: { avg_churn_rate_pct: null, scored_customers: 0 },
    }
    expect(buildInsights(sparse)).toEqual([
      'Device: Tablet users have the highest average predicted churn probability (50%), 20 points above Laptop users (30%).',
    ])
    expect(buildInsights(null)).toEqual([])
  })

  it('keeps only plans with a numeric revenue_at_risk', () => {
    expect(revenueByPlan([
      { plan_type: 'Basic', revenue_at_risk: 10.5 },
      { plan_type: 'Premium', revenue_at_risk: null },
      { plan_type: 'Standard' },
    ])).toEqual([{ segment: 'Basic', risk: 10.5 }])
    expect(revenueByPlan(undefined)).toEqual([])
  })
})

// CHURN-70: the page shows mean *predicted* probabilities, so it must not call them "churn rate".
describe('Segments page: terminology (CHURN-70)', () => {
  it('titles every chart and the genre table as average predicted churn probability', async () => {
    mockFetch({ '/segments': segments })
    const { container } = renderAt(<SegmentAnalysis />)
    await screen.findByText('Insights from the data')
    for (const dim of ['Plan Type', 'Device Type', 'Tenure Bucket', 'Preferred Genre']) {
      expect(screen.getByText(`Average Predicted Churn Probability by ${dim}`)).toBeInTheDocument()
    }
    expect(screen.getByRole('columnheader', { name: METRIC_LABEL })).toBeInTheDocument()
    expect(METRIC_LABEL).toBe('Avg predicted churn probability')
    expect(container.textContent).not.toMatch(/Churn Rate/)
    expect(container.textContent).not.toMatch(/predicted churn rate/)
  })

  it('maps the right-closed API tenure buckets to non-overlapping month ranges', () => {
    expect(segments.by_tenure.map(r => tenureLabel(r.tenure_bucket))).toEqual([
      '1–3 months', '4–6 months', '7–12 months', '13–24 months', '25+ months',
    ])
    expect(Object.keys(TENURE_LABELS)).toEqual(segments.by_tenure.map(r => r.tenure_bucket))
    expect(tenureLabel('unexpected')).toBe('unexpected')   // unknown buckets are shown as-is
  })

  it('leaves every number from the API unchanged', async () => {
    mockFetch({ '/segments': segments })
    renderAt(<SegmentAnalysis />)
    await screen.findByText('Insights from the data')
    for (const g of segments.by_genre) {
      const row = screen.getByText(g.preferred_genre).closest('tr')
      expect(within(row).getByText(`${g.churn_rate_pct}%`)).toBeInTheDocument()
    }
    expect(buildInsights(segments)[0]).toContain('(73.2%)')
  })
})
