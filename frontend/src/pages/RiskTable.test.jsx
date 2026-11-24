// CHURN-27: search, filters, sorting, pagination, badges, empty / loading / error states.
import { describe, it, expect } from 'vitest'
import { screen, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RiskTable, { filterAndSort } from './RiskTable'
import { mockFetch, renderAt, networkDown } from '../test/helpers'
import sample from '../test/fixtures/customers-sample.json'

const ROUTE = '/customers?limit=10000'
const rows = sample.customers
const bodyRows = () => within(screen.getAllByRole('rowgroup')[1]).getAllByRole('row')
const col = (n) => bodyRows().map(r => within(r).getAllByRole('cell')[n].textContent)

describe('RiskTable', () => {
  it('requests every customer and shows the full count', async () => {
    const f = mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    expect(await screen.findByText(`${rows.length} of ${rows.length} customers`, { exact: false })).toBeInTheDocument()
    expect(f.mock.calls[0][0]).toContain('/customers?limit=10000')
  })

  it('shows a loading state, then rows with API risk badges', async () => {
    mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    await screen.findByRole('table')
    const first = bodyRows()[0]
    expect(within(first).getByText('HIGH')).toHaveClass('badge-high')
  })

  it('searches by name or ID, case-insensitively, with surrounding spaces ignored', async () => {
    mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    await screen.findByRole('table')
    const target = rows[5]
    await userEvent.type(screen.getByRole('searchbox'), `  ${target.customer_id.toLowerCase()}  `)
    expect(col(0)).toEqual([target.customer_id])
    await userEvent.clear(screen.getByRole('searchbox'))
    await userEvent.type(screen.getByRole('searchbox'), target.name.toUpperCase())
    expect(col(1)).toContain(target.name)
  })

  it('filters by risk level and plan exactly like the backend fields', async () => {
    mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    await screen.findByRole('table')
    await userEvent.selectOptions(screen.getByLabelText('Filter by risk level'), 'MEDIUM')
    await userEvent.selectOptions(screen.getByLabelText('Filter by plan'), 'Premium')
    const expected = rows.filter(r => r.risk_level === 'MEDIUM' && r.plan_type === 'Premium').map(r => r.customer_id)
    expect(col(0).sort()).toEqual(expected.sort())
    expect(screen.getByText(`${expected.length} of ${rows.length} customers`, { exact: false })).toBeInTheDocument()
  })

  it('filters NOT_SCORED customers and shows them as NOT SCORED / N/A', async () => {
    mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    await screen.findByRole('table')
    await userEvent.selectOptions(screen.getByLabelText('Filter by risk level'), 'NOT_SCORED')
    expect(col(0)).toEqual(['CUST99990'])
    expect(col(2)).toEqual(['NOT SCORED'])                                   // churn % cell
    expect(within(bodyRows()[0]).getAllByText('NOT SCORED')[1]).toHaveClass('badge-none')
    expect(col(5)).toEqual(['N/A'])
  })

  it('sorts risk by severity (not alphabetically) and keeps unscored rows last', async () => {
    mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    await screen.findByRole('table')
    await userEvent.selectOptions(screen.getByLabelText('Rows'), '100')
    const riskHeader = screen.getByRole('button', { name: 'Risk' })
    await userEvent.click(riskHeader)                // descending
    let levels = col(3)
    const order = (l) => ({ HIGH: 3, MEDIUM: 2, LOW: 1 }[l] ?? 0)
    const desc = levels.filter(l => l !== 'NOT SCORED')
    expect(desc).toEqual([...desc].sort((a, b) => order(b) - order(a)))
    expect(levels[levels.length - 1]).toBe('NOT SCORED')
    await userEvent.click(riskHeader)                // ascending
    levels = col(3)
    const asc = levels.filter(l => l !== 'NOT SCORED')
    expect(asc).toEqual([...asc].sort((a, b) => order(a) - order(b)))
    expect(levels[levels.length - 1]).toBe('NOT SCORED')
    expect(screen.getByRole('columnheader', { name: 'Risk' })).toHaveAttribute('aria-sort', 'ascending')
  })

  it('sorts churn % numerically', async () => {
    mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    await screen.findByRole('table')
    const sorted = filterAndSort(rows, { sort: { key: 'churn_prob', dir: 'desc' } })
    expect(col(0)).toEqual(sorted.slice(0, 25).map(r => r.customer_id))
    const probs = sorted.filter(r => r.churn_prob != null).map(r => r.churn_prob)
    expect(probs).toEqual([...probs].sort((a, b) => b - a))
  })

  it('paginates: 25 per page by default, next / previous, and resets on filter change', async () => {
    mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    await screen.findByRole('table')
    expect(bodyRows()).toHaveLength(25)
    expect(screen.getByTestId('page-range')).toHaveTextContent(`Showing 1–25 of ${rows.length}`)
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(bodyRows()).toHaveLength(rows.length - 25)
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    await userEvent.selectOptions(screen.getByLabelText('Filter by plan'), 'Basic')
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument()
  })

  it('shows an empty-state message when nothing matches', async () => {
    mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    await screen.findByRole('table')
    await userEvent.type(screen.getByRole('searchbox'), 'no-such-customer-xyz')
    expect(screen.getByText('No customers match the current filters')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows an API error with Retry instead of "0 customers"', async () => {
    mockFetch({ [ROUTE]: networkDown() })
    renderAt(<RiskTable />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Customers could not be loaded')
    expect(screen.queryByText('No customers match the current filters')).not.toBeInTheDocument()
    mockFetch({ [ROUTE]: sample })
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })

  it('links each row to the customer detail page', async () => {
    mockFetch({ [ROUTE]: sample })
    renderAt(<RiskTable />)
    await screen.findByRole('table')
    const first = filterAndSort(rows, {})[0]
    expect(screen.getByRole('link', { name: `View ${first.name} (${first.customer_id})` }))
      .toHaveAttribute('href', `/risk/${first.customer_id}`)
  })
})
