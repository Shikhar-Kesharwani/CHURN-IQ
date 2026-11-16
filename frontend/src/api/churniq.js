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
  sendEmail:             (body) => post('/send-email', body),
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
