// CHURN-28: customer detail — correct per-customer data, no stale data, clear errors, no auto-send.
import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent, waitFor, render } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useNavigate } from 'react-router-dom'
import CustomerDetail from './CustomerDetail'
import { mockFetch, jsonResponse, networkDown } from '../test/helpers'
import c1 from '../test/fixtures/customer-CUST00001.json'
import c2 from '../test/fixtures/customer-CUST02261.json'
import whatif from '../test/fixtures/whatif-CUST00001.json'
import retention from '../test/fixtures/retention-CUST02261.json'

function renderDetail(id) {
  return render(
    <MemoryRouter initialEntries={[`/risk/${id}`]}>
      <Routes><Route path="/risk/:id" element={<CustomerDetail />} /><Route path="*" element={<p>elsewhere</p>} /></Routes>
    </MemoryRouter>
  )
}

describe('CustomerDetail', () => {
  it('shows the profile, CLV tier and SHAP reasons from GET /customer/{id}', async () => {
    mockFetch({ '/customer/CUST02261': c2 })
    renderDetail('CUST02261')
    expect(await screen.findByRole('heading', { name: c2.name })).toBeInTheDocument()
    expect(screen.getByText(c2.customer_id)).toBeInTheDocument()
    expect(screen.getByTestId('profile-Plan')).toHaveTextContent(c2.plan_type)
    expect(screen.getByTestId('profile-CLV')).toHaveTextContent(c2.clv_formatted)
    expect(screen.getByTestId('profile-CLV Tier')).toHaveTextContent(c2.clv_segment)
    expect(screen.getByRole('img', { name: `Churn risk ${Math.round(c2.churn_prob * 100)}%` })).toBeInTheDocument()
    const reasons = screen.getAllByTestId('shap-reason').map(e => e.textContent)
    expect(reasons).toEqual([c2.top_reason_1, c2.top_reason_2, c2.top_reason_3].map(r => r.split('[')[0].trim()))
  })

  it('pre-fills the What-If sliders with the customer\'s own values', async () => {
    mockFetch({ '/customer/CUST00001': c1 })
    renderDetail('CUST00001')
    await screen.findByRole('heading', { name: c1.name })
    expect(screen.getByLabelText('Watch Hours / Week')).toHaveValue(String(c1.watch_hours_per_week))
    expect(screen.getByLabelText('Tenure (months)')).toHaveValue(String(c1.tenure_months))
    expect(screen.getByLabelText('Payment Failures')).toHaveValue(String(c1.payment_failures_3m))
  })

  it('posts the slider values to /whatif and shows before / after from the API', async () => {
    const f = mockFetch({ '/customer/CUST00001': c1, 'POST /whatif': whatif })
    renderDetail('CUST00001')
    await screen.findByRole('heading', { name: c1.name })
    fireEvent.change(screen.getByLabelText('Payment Failures'), { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Recalculate Churn' }))
    const result = await screen.findByTestId('whatif-result')
    expect(result).toHaveTextContent(`${Math.round(whatif.original_churn_prob * 100)}%`)
    expect(result).toHaveTextContent(`${Math.round(whatif.new_churn_prob * 100)}%`)
    expect(result).toHaveTextContent(whatif.change_percent)
    const body = JSON.parse(f.mock.calls.find(c => c[0].endsWith('/whatif'))[1].body)
    expect(body).toMatchObject({ customer_id: 'CUST00001', payment_failures_3m: 4, tenure_months: c1.tenure_months })
  })

  it('shows What-If API errors instead of silently doing nothing', async () => {
    mockFetch({
      '/customer/CUST00001': c1,
      'POST /whatif': jsonResponse({ detail: 'Fold model unavailable for this customer.', error: 'fold_model_unavailable' }, 409),
    })
    renderDetail('CUST00001')
    await screen.findByRole('heading', { name: c1.name })
    fireEvent.click(screen.getByRole('button', { name: 'Recalculate Churn' }))
    expect(await screen.findByText('What-If calculation failed')).toBeInTheDocument()
    expect(screen.getByText('Fold model unavailable for this customer.')).toBeInTheDocument()
  })

  it('generates a retention email, labels a rule-based fallback, and never sends on its own', async () => {
    const f = mockFetch({ '/customer/CUST02261': c2, '/retention/CUST02261': retention })
    renderDetail('CUST02261')
    await screen.findByRole('heading', { name: c2.name })
    fireEvent.click(screen.getByRole('button', { name: 'Generate Retention Email' }))
    expect(await screen.findByText(retention.subject)).toBeInTheDocument()
    expect(screen.getByTestId('retention-source')).toHaveTextContent('Rule-based template (AI unavailable: gemini not configured)')
    expect(f.mock.calls.some(c => c[0].includes('/send-email'))).toBe(false)
  })

  it('shows a retention API failure', async () => {
    mockFetch({ '/customer/CUST02261': c2, '/retention/CUST02261': networkDown() })
    renderDetail('CUST02261')
    await screen.findByRole('heading', { name: c2.name })
    fireEvent.click(screen.getByRole('button', { name: 'Generate Retention Email' }))
    expect(await screen.findByText('Retention email could not be generated')).toBeInTheDocument()
  })

  it('distinguishes "not found" (404) from "API unreachable" (network)', async () => {
    mockFetch({ '/customer/CUST99998': jsonResponse({ detail: "Customer 'CUST99998' not found.", error: 'customer_not_found' }, 404) })
    const { unmount } = renderDetail('CUST99998')
    expect(await screen.findByText('Customer not found: CUST99998')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
    unmount()

    mockFetch({ '/customer/CUST00001': networkDown() })
    renderDetail('CUST00001')
    expect(await screen.findByText('Customer could not be loaded')).toBeInTheDocument()
    expect(screen.getByText(/Cannot reach the ChurnIQ API/)).toBeInTheDocument()
    expect(screen.queryByText(/Customer not found/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('reports an invalid ID (422) as invalid, not as not-found', async () => {
    mockFetch({ '/customer/bad%20id': jsonResponse({ detail: 'customer_id must be 1-32 characters', error: 'validation_error' }, 422) })
    renderDetail('bad id')
    expect(await screen.findByText('Invalid customer ID: bad id')).toBeInTheDocument()
  })

  it('never shows the previous customer\'s data after switching customers', async () => {
    // Customer 1 has a What-If result on screen; then the route changes to customer 2,
    // whose response arrives later. Nothing from customer 1 may remain.
    let release
    const slow = new Promise(r => { release = r })
    mockFetch({
      '/customer/CUST00001': c1,
      'POST /whatif': whatif,
      '/customer/CUST02261': () => slow.then(() => c2),
    })
    let go
    function Nav() { go = useNavigate(); return null }
    render(
      <MemoryRouter initialEntries={['/risk/CUST00001']}>
        <Nav />
        <Routes><Route path="/risk/:id" element={<CustomerDetail />} /></Routes>
      </MemoryRouter>
    )
    await screen.findByRole('heading', { name: c1.name })
    fireEvent.click(screen.getByRole('button', { name: 'Recalculate Churn' }))
    await screen.findByTestId('whatif-result')

    go('/risk/CUST02261')
    await waitFor(() => expect(screen.queryByRole('heading', { name: c1.name })).not.toBeInTheDocument())
    expect(screen.queryByTestId('whatif-result')).not.toBeInTheDocument()
    release()
    expect(await screen.findByRole('heading', { name: c2.name })).toBeInTheDocument()
    expect(screen.queryByTestId('whatif-result')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Watch Hours / Week')).toHaveValue(String(c2.watch_hours_per_week))
  })

  it('ignores a slow response for a customer the user has already left', async () => {
    let releaseOld
    const old = new Promise(r => { releaseOld = r })
    mockFetch({ '/customer/CUST00001': () => old.then(() => c1), '/customer/CUST02261': c2 })
    let go
    function Nav() { go = useNavigate(); return null }
    render(
      <MemoryRouter initialEntries={['/risk/CUST00001']}>
        <Nav />
        <Routes><Route path="/risk/:id" element={<CustomerDetail />} /></Routes>
      </MemoryRouter>
    )
    go('/risk/CUST02261')
    expect(await screen.findByRole('heading', { name: c2.name })).toBeInTheDocument()
    releaseOld()
    await new Promise(r => setTimeout(r, 20))
    expect(screen.getByRole('heading', { name: c2.name })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: c1.name })).not.toBeInTheDocument()
  })

  it('keeps the CHURN-44 send flow: asks for the token, clears it after a 401', async () => {
    mockFetch({
      '/customer/CUST02261': c2, '/retention/CUST02261': retention,
      'POST /send-email': jsonResponse({ detail: 'Invalid or missing email API token.' }, 401),
    })
    const prompt = vi.spyOn(window, 'prompt').mockReturnValue('wrong-token-123456')
    renderDetail('CUST02261')
    await screen.findByRole('heading', { name: c2.name })
    fireEvent.click(screen.getByRole('button', { name: 'Generate Retention Email' }))
    await screen.findByText(retention.subject)
    fireEvent.click(screen.getByRole('button', { name: /Send Email/ }))
    expect(await screen.findByText('Invalid or missing email API token.')).toBeInTheDocument()
    expect(prompt).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem('churniq_email_api_token')).toBeNull()
  })
})
