// CHURN-29: API client — base URL, error classification, timeouts, no silent fallback.
import { describe, it, expect, vi } from 'vitest'
import { api, request, BASE_URL, validateWhatIfField, CUSTOMER_ID_RE } from './churniq'
import { mockFetch, jsonResponse, networkDown, API } from '../test/helpers'

describe('API base URL', () => {
  it('comes from VITE_API_URL (pinned to the test API)', () => {
    expect(BASE_URL).toBe(API)
  })

  it('has no hard-coded production fallback: one request per call, to the configured URL only', async () => {
    const f = mockFetch({ '/dashboard/summary': networkDown() })
    const { data, error } = await api.getDashboard()
    expect(data).toBeNull()
    expect(error.kind).toBe('network')
    expect(f).toHaveBeenCalledTimes(1)
    expect(f.mock.calls[0][0]).toBe(`${API}/dashboard/summary`)
  })
})

describe('request()', () => {
  it('returns parsed JSON on success', async () => {
    mockFetch({ '/x': { ok: 1 } })
    expect(await request('/x')).toEqual({ data: { ok: 1 }, error: null })
  })

  it('classifies HTTP errors and keeps the backend detail, code and field errors', async () => {
    mockFetch({
      'POST /whatif': jsonResponse({
        detail: 'Invalid request — watch_hours_per_week: Input should be greater than or equal to 0',
        error: 'validation_error', status_code: 422,
        errors: [{ field: 'watch_hours_per_week', message: 'Input should be greater than or equal to 0' }],
      }, 422),
    })
    const { data, error } = await api.whatIf({ customer_id: 'CUST00001', watch_hours_per_week: -1 })
    expect(data).toBeNull()
    expect(error).toMatchObject({ kind: 'http', status: 422, code: 'validation_error' })
    expect(error.message).toMatch(/greater than or equal to 0/)
    expect(error.fieldErrors).toHaveLength(1)
  })

  it('treats 404 as an error (not as "no data")', async () => {
    mockFetch({ '/customer/CUST99998': jsonResponse({ detail: "Customer 'CUST99998' not found.", error: 'customer_not_found' }, 404) })
    const { error } = await api.getCustomer('CUST99998')
    expect(error).toMatchObject({ kind: 'http', status: 404, code: 'customer_not_found' })
  })

  it('gives a generic message for a 5xx without a JSON body', async () => {
    mockFetch({ '/segments': new Response('Internal Server Error', { status: 500 }) })
    const { error } = await api.getSegments()
    expect(error).toMatchObject({ kind: 'http', status: 500 })
    expect(error.message).toMatch(/HTTP 500/)
  })

  it('flags a 2xx with a non-JSON body as an invalid response', async () => {
    mockFetch({ '/segments': new Response('<html>proxy page</html>', { status: 200 }) })
    const { error } = await api.getSegments()
    expect(error.kind).toBe('invalid')
  })

  it('flags a 2xx with a non-object JSON body as invalid', async () => {
    mockFetch({ '/segments': jsonResponse('just a string') })
    expect((await api.getSegments()).error.kind).toBe('invalid')
  })

  it('times out a request that never answers', async () => {
    vi.useFakeTimers()
    globalThis.fetch = vi.fn((url, { signal }) => new Promise((_, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    const p = request('/slow', { timeoutMs: 1000 })
    await vi.advanceTimersByTimeAsync(1001)
    const { error } = await p
    vi.useRealTimers()
    expect(error.kind).toBe('timeout')
    expect(error.message).toMatch(/1 s/)
  })

  it('encodes customer IDs in the path', async () => {
    const f = mockFetch({ '/customer/A%2FB': { customer_id: 'A/B' } })
    await api.getCustomer('A/B')
    expect(f.mock.calls[0][0]).toBe(`${API}/customer/A%2FB`)
  })

  it('requests all customers, not the backend default of 500', async () => {
    const f = mockFetch({ '/customers?limit=10000': { customers: [] } })
    await api.getCustomers()
    expect(f.mock.calls[0][0]).toBe(`${API}/customers?limit=10000`)
  })
})

describe('sendEmail (CHURN-44 behaviour preserved)', () => {
  it('sends the bearer token once, to the configured API only', async () => {
    const f = mockFetch({ 'POST /send-email': { success: true, sent_to: 'd****x@example.com' } })
    const res = await api.sendEmail({ customer_id: 'CUST00001', subject: 's', body: 'b' }, 'tok-1234567890abcdef')
    expect(res.success).toBe(true)
    expect(f).toHaveBeenCalledTimes(1)
    expect(f.mock.calls[0][1].headers.Authorization).toBe('Bearer tok-1234567890abcdef')
  })

  it('returns { error, status } for 401 / 429 so the page can react', async () => {
    mockFetch({ 'POST /send-email': jsonResponse({ detail: 'Invalid or missing email API token.' }, 401) })
    expect(await api.sendEmail({}, 'bad')).toEqual({ error: 'Invalid or missing email API token.', status: 401 })
  })

  it('returns the original connection message when the API is down', async () => {
    mockFetch({ 'POST /send-email': networkDown() })
    expect((await api.sendEmail({}, 't')).error).toMatch(/Unable to connect/)
  })
})

describe('validation helpers mirror the backend', () => {
  it('validates What-If bounds (CHURN-20 WHATIF_BOUNDS)', () => {
    expect(validateWhatIfField('watch_hours_per_week', '0')).toBeNull()
    expect(validateWhatIfField('watch_hours_per_week', '168')).toBeNull()
    expect(validateWhatIfField('watch_hours_per_week', '168.5')).toMatch(/between 0 and 168/)
    expect(validateWhatIfField('tenure_months', '0')).toMatch(/between 1 and 240/)
    expect(validateWhatIfField('tenure_months', '2.5')).toMatch(/whole number/)
    expect(validateWhatIfField('payment_failures_3m', '')).toBe('Required')
    expect(validateWhatIfField('support_tickets', 'abc')).toBe('Must be a number')
    expect(validateWhatIfField('monthly_charge', '5001')).toMatch(/between 1 and 5000/)
  })

  it('validates customer IDs like the backend pattern', () => {
    expect(CUSTOMER_ID_RE.test('CUST00001')).toBe(true)
    expect(CUSTOMER_ID_RE.test('bad id')).toBe(false)
    expect(CUSTOMER_ID_RE.test('x'.repeat(33))).toBe(false)
  })
})
