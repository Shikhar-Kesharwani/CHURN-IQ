// CHURN-31 (What-If simulator): real customer, validated inputs, model result, no invented fallback.
import { describe, it, expect } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ChurnPredict from './ChurnPredict'
import { mockFetch, renderAt, jsonResponse, networkDown } from '../test/helpers'
import c1 from '../test/fixtures/customer-CUST00001.json'
import whatif from '../test/fixtures/whatif-CUST00001.json'

async function loadCustomer(id = 'CUST00001') {
  await userEvent.type(screen.getByLabelText('Customer ID'), id)
  await userEvent.click(screen.getByRole('button', { name: 'Load customer' }))
}

describe('ChurnPredict (What-If)', () => {
  it('loads the chosen customer and pre-fills the six What-If fields', async () => {
    mockFetch({ '/customer/CUST00001': c1 })
    renderAt(<ChurnPredict />)
    await loadCustomer()
    expect(await screen.findByText(c1.name)).toBeInTheDocument()
    expect(screen.getByLabelText(/Watch hours \/ week/)).toHaveValue(c1.watch_hours_per_week)
    expect(screen.getByLabelText(/Monthly charge/)).toHaveValue(c1.monthly_charge)
    expect(screen.getByText(c1.churn_percent)).toBeInTheDocument()
  })

  it('sends the loaded customer\'s ID (not a fixed one) with the edited values', async () => {
    const f = mockFetch({ '/customer/CUST00001': c1, 'POST /whatif': whatif })
    renderAt(<ChurnPredict />)
    await loadCustomer()
    await screen.findByText(c1.name)
    const pf = screen.getByLabelText(/Payment failures/)
    await userEvent.clear(pf)
    await userEvent.type(pf, '4')
    await userEvent.click(screen.getByRole('button', { name: /Predict Churn/ }))
    const result = await screen.findByTestId('predict-result')
    const body = JSON.parse(f.mock.calls.find(c => c[0].endsWith('/whatif'))[1].body)
    expect(body.customer_id).toBe('CUST00001')
    expect(body.payment_failures_3m).toBe(4)
    expect(Object.keys(body).sort()).toEqual(
      ['customer_id', 'logins_last_30_days', 'monthly_charge', 'payment_failures_3m', 'support_tickets', 'tenure_months', 'watch_hours_per_week'])
    expect(result).toHaveTextContent(`${(whatif.original_churn_prob * 100).toFixed(1)}%`)
    expect(result).toHaveTextContent(`${(whatif.new_churn_prob * 100).toFixed(1)}%`)
    expect(result).toHaveTextContent(whatif.change_percent)
    expect(result).toHaveTextContent('Changed: Payment failures (3 months).')
  })

  it('blocks out-of-range and non-integer input before calling the API (backend bounds)', async () => {
    const f = mockFetch({ '/customer/CUST00001': c1 })
    renderAt(<ChurnPredict />)
    await loadCustomer()
    await screen.findByText(c1.name)
    const tenure = screen.getByLabelText(/Tenure/)
    fireEvent.change(tenure, { target: { value: '0' } })
    expect(screen.getByText('Must be between 1 and 240')).toBeInTheDocument()
    fireEvent.change(tenure, { target: { value: '12.5' } })
    expect(screen.getByText('Must be a whole number')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Watch hours/), { target: { value: '168.5' } })
    expect(screen.getByText('Must be between 0 and 168')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Predict Churn/ }))
    expect(f.mock.calls.some(c => c[0].endsWith('/whatif'))).toBe(false)
  })

  it('accepts the exact boundary values', async () => {
    const f = mockFetch({ '/customer/CUST00001': c1, 'POST /whatif': whatif })
    renderAt(<ChurnPredict />)
    await loadCustomer()
    await screen.findByText(c1.name)
    fireEvent.change(screen.getByLabelText(/Watch hours/), { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText(/Tenure/), { target: { value: '240' } })
    await userEvent.click(screen.getByRole('button', { name: /Predict Churn/ }))
    await screen.findByTestId('predict-result')
    const body = JSON.parse(f.mock.calls.find(c => c[0].endsWith('/whatif'))[1].body)
    expect(body).toMatchObject({ watch_hours_per_week: 0, tenure_months: 240 })
  })

  it('shows the backend validation message if the API still rejects the request', async () => {
    mockFetch({
      '/customer/CUST00001': c1,
      'POST /whatif': jsonResponse({ detail: 'Invalid request — tenure_months: bad', error: 'validation_error', errors: [{ field: 'tenure_months', message: 'bad' }] }, 422),
    })
    renderAt(<ChurnPredict />)
    await loadCustomer()
    await screen.findByText(c1.name)
    await userEvent.click(screen.getByRole('button', { name: /Predict Churn/ }))
    expect(await screen.findByText('Prediction failed')).toBeInTheDocument()
    expect(screen.getByText('tenure_months: bad')).toBeInTheDocument()
  })

  it('shows an error — and no made-up prediction — when the backend is down', async () => {
    mockFetch({ '/customer/CUST00001': c1, 'POST /whatif': networkDown() })
    renderAt(<ChurnPredict />)
    await loadCustomer()
    await screen.findByText(c1.name)
    await userEvent.click(screen.getByRole('button', { name: /Predict Churn/ }))
    expect(await screen.findByText('Prediction failed')).toBeInTheDocument()
    expect(screen.queryByTestId('predict-result')).not.toBeInTheDocument()
    expect(screen.queryByText(/estimated prediction/i)).not.toBeInTheDocument()
  })

  it('validates the customer ID format and reports unknown customers', async () => {
    const f = mockFetch({ '/customer/CUST99998': jsonResponse({ detail: "Customer 'CUST99998' not found.", error: 'customer_not_found' }, 404) })
    renderAt(<ChurnPredict />)
    await loadCustomer('BAD ID!')
    expect(screen.getByText(/Enter a customer ID/)).toBeInTheDocument()
    expect(f).not.toHaveBeenCalled()
    await userEvent.clear(screen.getByLabelText('Customer ID'))
    await loadCustomer('CUST99998')
    expect(await screen.findByText('Customer not found')).toBeInTheDocument()
  })
})
