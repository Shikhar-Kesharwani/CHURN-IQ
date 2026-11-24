// CHURN-31 (similarity page): neighbours, ordering, count, invalid input, empty and error responses.
import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CustomerSimilarity from './CustomerSimilarity'
import { mockFetch, renderAt, jsonResponse, networkDown } from '../test/helpers'
import sim3 from '../test/fixtures/similarity-CUST00001-3.json'

const ROUTE = 'POST /api/customer-similarity'

describe('CustomerSimilarity', () => {
  it('loads the customer from ?customer=, requests the chosen count and lists neighbours in API order', async () => {
    const f = mockFetch({ [ROUTE]: ({ body }) => ({ ...sim3, count: sim3.similar_customers.length, _req: body }) })
    renderAt(<CustomerSimilarity />, { path: '/similarity', route: '/similarity?customer=cust00001' })
    expect(await screen.findByText(`Returned ${sim3.similar_customers.length} neighbours`)).toBeInTheDocument()
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ customer_id: 'CUST00001', n_neighbors: 5 })
    const table = screen.getAllByRole('table')[0]
    const ids = within(table).getAllByRole('row').slice(1).map(r => r.textContent)
    sim3.similar_customers.forEach((n, i) => expect(ids[i]).toContain(n.customer_id))
    // ordering as returned by the API: similarity descending
    const scores = sim3.similar_customers.map(n => n.similarity_score)
    expect(scores).toEqual([...scores].sort((a, b) => b - a))
  })

  it('changing "Neighbours" re-queries with that count', async () => {
    const f = mockFetch({ [ROUTE]: sim3 })
    renderAt(<CustomerSimilarity />, { path: '/similarity', route: '/similarity' })
    await screen.findByText(/Returned \d+ neighbours/)
    await userEvent.selectOptions(screen.getByLabelText('Number of similar customers'), '10')
    expect(JSON.parse(f.mock.calls.at(-1)[1].body).n_neighbors).toBe(10)
  })

  it('rejects a malformed ID without calling the API', async () => {
    const f = mockFetch({ [ROUTE]: sim3 })
    renderAt(<CustomerSimilarity />, { path: '/similarity', route: '/similarity' })
    await screen.findByText(/Returned \d+ neighbours/)
    const calls = f.mock.calls.length
    const input = screen.getByLabelText('Customer ID')
    await userEvent.clear(input)
    await userEvent.type(input, 'BAD ID!{Enter}')
    expect(await screen.findByText('Invalid customer ID')).toBeInTheDocument()
    expect(f.mock.calls.length).toBe(calls)
  })

  it('shows "not found" for an unknown customer (404 from the API)', async () => {
    mockFetch({ [ROUTE]: jsonResponse({ detail: "Customer 'CUST99998' not found.", error: 'customer_not_found' }, 404) })
    renderAt(<CustomerSimilarity />, { path: '/similarity', route: '/similarity?customer=CUST99998' })
    expect(await screen.findByText('Customer not found')).toBeInTheDocument()
  })

  it('handles an empty neighbour list', async () => {
    mockFetch({ [ROUTE]: { ...sim3, similar_customers: [], count: 0, insights: [] } })
    renderAt(<CustomerSimilarity />, { path: '/similarity', route: '/similarity' })
    expect(await screen.findByText('No similar customers were returned for this customer.')).toBeInTheDocument()
  })

  it('shows a network error with Retry', async () => {
    mockFetch({ [ROUTE]: networkDown() })
    renderAt(<CustomerSimilarity />, { path: '/similarity', route: '/similarity' })
    expect(await screen.findByText('Cannot reach the API')).toBeInTheDocument()
    mockFetch({ [ROUTE]: sim3 })
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByText(/Returned \d+ neighbours/)).toBeInTheDocument()
  })

  it('treats a response without neighbours as invalid instead of crashing', async () => {
    mockFetch({ [ROUTE]: { unexpected: true } })
    renderAt(<CustomerSimilarity />, { path: '/similarity', route: '/similarity' })
    expect(await screen.findByText('Unexpected response from the similarity service.')).toBeInTheDocument()
  })
})
