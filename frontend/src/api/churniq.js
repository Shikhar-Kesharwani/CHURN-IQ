// ── ChurnIQ Pro — API layer ─────────────────────────────────
//
// CHURN-29: one request helper for every endpoint.
//
// * The API base URL comes only from VITE_API_URL. Development falls back to
//   http://localhost:8000. Production builds read it from frontend/.env.production
//   (build configuration, overridable by the hosting provider's environment).
// * There is no silent fallback to a second server: if the configured API is
//   down, the page says so instead of quietly showing another environment's data.
// * Every call resolves to { data, error }. Exactly one of them is non-null.
//   error = { kind, status, message, code, fieldErrors }
//     kind: 'network'  — server unreachable / CORS / DNS
//           'timeout'  — no response within the timeout
//           'http'     — non-2xx response (status set; message = backend `detail`)
//           'invalid'  — 2xx response whose body is not the expected JSON object
// * No call ever throws, so a failed request can never crash a page.

const trimSlash = (u) => String(u).replace(/\/+$/, '')

export const BASE_URL = trimSlash(import.meta.env.VITE_API_URL || 'http://localhost:8000')

export const DEFAULT_TIMEOUT_MS = 20000
// /retention calls Gemini server-side with a 20 s upstream timeout, so allow more.
export const RETENTION_TIMEOUT_MS = 35000

const NETWORK_MESSAGE =
  `Cannot reach the ChurnIQ API at ${BASE_URL}. Make sure the backend is running and try again.`

function makeError(kind, { status = null, message, code = null, fieldErrors = [] } = {}) {
  return { kind, status, code, fieldErrors, message: message || NETWORK_MESSAGE }
}

function httpMessage(status, body) {
  if (body && typeof body.detail === 'string' && body.detail.trim()) return body.detail
  if (status === 404) return 'Not found.'
  if (status >= 500) return `The API returned an error (HTTP ${status}). Please try again later.`
  return `Request failed (HTTP ${status}).`
}

/**
 * Low-level request. Resolves to { data, error }; never throws.
 * `fetchImpl` and `baseUrl` are injectable for tests.
 */
export async function request(path, {
  method = 'GET',
  body,
  headers = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
  signal,
  baseUrl = BASE_URL,
  fetchImpl = (...a) => globalThis.fetch(...a),
} = {}) {
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)
  const onAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }

  try {
    let response
    try {
      response = await fetchImpl(`${trimSlash(baseUrl)}${path}`, {
        method,
        headers: body !== undefined ? { 'Content-Type': 'application/json', ...headers } : headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })
    } catch {
      if (timedOut) {
        return { data: null, error: makeError('timeout', {
          message: `The ChurnIQ API did not respond within ${Math.round(timeoutMs / 1000)} s. Please try again.`,
        }) }
      }
      if (signal?.aborted) return { data: null, error: makeError('aborted', { message: 'Request cancelled.' }) }
      return { data: null, error: makeError('network') }
    }

    let parsed = null
    let parseOk = true
    try {
      const text = await response.text()
      parsed = text ? JSON.parse(text) : null
    } catch {
      parseOk = false
    }

    if (!response.ok) {
      return { data: null, error: makeError('http', {
        status: response.status,
        code: parsed?.error || null,
        message: httpMessage(response.status, parsed),
        fieldErrors: Array.isArray(parsed?.errors) ? parsed.errors : [],
      }) }
    }

    if (!parseOk || parsed === null || typeof parsed !== 'object') {
      return { data: null, error: makeError('invalid', {
        status: response.status,
        message: 'The API returned an unexpected response. Please try again or check the backend version.',
      }) }
    }
    return { data: parsed, error: null }
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onAbort)
  }
}

const enc = encodeURIComponent

export const api = {
  health:       (opts)       => request('/', opts),
  getDashboard: (opts)       => request('/dashboard/summary', opts),
  // CHURN-27: request every customer (the backend default is limit=500).
  getCustomers: (opts)       => request('/customers?limit=10000', opts),
  getCustomer:  (id, opts)   => request(`/customer/${enc(id)}`, opts),
  getSegments:  (opts)       => request('/segments', opts),
  getRetention: (id, opts)   => request(`/retention/${enc(id)}`, { timeoutMs: RETENTION_TIMEOUT_MS, ...opts }),
  emailStatus:  (opts)       => request('/email-status', opts),
  whatIf:       (body, opts) => request('/whatif', { method: 'POST', body, ...opts }),
  getCustomerSimilarity: (body, opts) =>
    request('/api/customer-similarity', { method: 'POST', body, ...opts }),

  // CHURN-44: /send-email needs `Authorization: Bearer <EMAIL_API_TOKEN>`.
  // Behaviour kept from CHURN-44: returns the success body, or { error, status }
  // so the UI can show 401/429. The only change (CHURN-29) is that it is sent to
  // the configured API alone, so the token is never re-sent to a second server.
  sendEmail: async (body, token) => {
    const { data, error } = await request('/send-email', {
      method: 'POST',
      body,
      headers: { Authorization: `Bearer ${token}` },
    })
    if (error) {
      if (error.kind === 'http') return { error: error.message, status: error.status }
      if (error.kind === 'network') {
        return { error: 'Unable to connect to ChurnIQ backend. Please ensure the backend server is running.' }
      }
      return { error: error.message }
    }
    return data
  },
}

// ── Customer ID format (mirrors backend CUSTOMER_ID_PATTERN) ──
export const CUSTOMER_ID_RE = /^[A-Za-z0-9_-]{1,32}$/

// ── What-If bounds (mirrors backend WHATIF_BOUNDS, CHURN-20) ──
export const WHATIF_BOUNDS = {
  watch_hours_per_week: { min: 0,  max: 168,  step: 0.5, int: false, label: 'Watch hours / week' },
  tenure_months:        { min: 1,  max: 240,  step: 1,   int: true,  label: 'Tenure (months)' },
  payment_failures_3m:  { min: 0,  max: 20,   step: 1,   int: true,  label: 'Payment failures (3 months)' },
  support_tickets:      { min: 0,  max: 100,  step: 1,   int: true,  label: 'Support tickets' },
  logins_last_30_days:  { min: 0,  max: 300,  step: 1,   int: true,  label: 'Logins (last 30 days)' },
  monthly_charge:       { min: 1,  max: 5000, step: 1,   int: true,  label: 'Monthly charge (₹)' },
}

/** Returns an error message for a What-If field value, or null when valid. */
export function validateWhatIfField(field, raw) {
  const b = WHATIF_BOUNDS[field]
  if (!b) return null
  if (raw === '' || raw === null || raw === undefined) return 'Required'
  const n = Number(raw)
  if (!Number.isFinite(n)) return 'Must be a number'
  if (b.int && !Number.isInteger(n)) return 'Must be a whole number'
  if (n < b.min || n > b.max) return `Must be between ${b.min} and ${b.max}`
  return null
}

// ── Email API token (CHURN-44) ──────────────────────────────
// The token is typed in by the operator when they first send an email and is
// kept in sessionStorage only (cleared when the tab closes). It is deliberately
// NOT read from a VITE_* variable: anything in a Vite env var is compiled into
// the public JavaScript bundle, where anyone could read it.
const EMAIL_TOKEN_KEY = 'churniq_email_api_token'

export function getEmailToken() {
  try { return sessionStorage.getItem(EMAIL_TOKEN_KEY) || '' } catch { return '' }
}

export function setEmailToken(token) {
  try { sessionStorage.setItem(EMAIL_TOKEN_KEY, token) } catch { /* storage unavailable */ }
}

export function clearEmailToken() {
  try { sessionStorage.removeItem(EMAIL_TOKEN_KEY) } catch { /* storage unavailable */ }
}
