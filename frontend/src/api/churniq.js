// ── ChurnIQ Pro — API layer ─────────────────────────────────

export const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
export const FALLBACK_URL = 'https://churniq-32r3.onrender.com'

async function tryFetch(path, options = {}) {
  // Try local / primary URL first, fall back to remote URL if connection fails
  const urls = [BASE_URL, FALLBACK_URL].filter((v, i, a) => v && a.indexOf(v) === i)
  for (const url of urls) {
    try {
      const r = await fetch(`${url}${path}`, options)
      if (r.ok) return await r.json()
      if (r.status === 404) return null
    } catch {
      // Network error (e.g. server down) -> try next URL
      continue
    }
  }
  return null
}

async function get(path) {
  try {
    return await tryFetch(path)
  } catch (e) {
    console.warn('[API GET]', path, e.message)
    return null
  }
}

async function post(path, body) {
  try {
    return await tryFetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (e) {
    console.warn('[API POST]', path, e.message)
    return null
  }
}

export const api = {
  getDashboard:          ()     => get('/dashboard/summary'),
  getCustomers:          (params = '') => get(`/customers${params}`),
  getCustomer:           (id)   => get(`/customer/${id}`),
  getSegments:           ()     => get('/segments'),
  getRetention:          (id)   => get(`/retention/${id}`),
  emailStatus:           ()     => get('/email-status'),
  whatIf:                (body) => post('/whatif', body),
  // CHURN-44: /send-email needs `Authorization: Bearer <EMAIL_API_TOKEN>`.
  // Returns the success body, or { error, status } so the UI can show 401/429.
  // Unlike tryFetch, only network failures fall through to FALLBACK_URL: a
  // 401/429/5xx is returned as-is and the token is not re-sent elsewhere.
  sendEmail: async (body, token) => {
    const urls = [BASE_URL, FALLBACK_URL].filter((v, i, a) => v && a.indexOf(v) === i)
    for (const url of urls) {
      try {
        const r = await fetch(`${url}/send-email`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify(body),
        })
        const data = await r.json().catch(() => null)
        if (!r.ok) return { error: data?.detail || `HTTP Error ${r.status}`, status: r.status }
        return data
      } catch {
        continue
      }
    }
    return { error: 'Unable to connect to ChurnIQ backend. Please ensure the backend server is running.' }
  },
  getCustomerSimilarity: async (body) => {
    const urls = [BASE_URL, FALLBACK_URL].filter((v, i, a) => v && a.indexOf(v) === i)
    for (const url of urls) {
      try {
        const r = await fetch(`${url}/api/customer-similarity`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        const data = await r.json().catch(() => null)
        if (!r.ok) {
          return { error: data?.detail || `HTTP Error ${r.status}` }
        }
        return data
      } catch {
        continue
      }
    }
    return { error: 'Unable to connect to ChurnIQ backend. Please ensure the backend server is running.' }
  },
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
