import { vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

export const API = 'http://api.test'

export function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/**
 * Replace global fetch. `routes` maps "METHOD /path" (or "/path" for GET) to a
 * body, a Response, a function (req) => body|Response, or an Error to throw.
 * Unmatched requests fail the test loudly. Returns the vi mock (calls = requests).
 */
export function mockFetch(routes) {
  const fn = vi.fn(async (url, init = {}) => {
    const u = new URL(url)
    const method = (init.method || 'GET').toUpperCase()
    const keyFull = `${method} ${u.pathname}${u.search}`
    const keyPath = `${method} ${u.pathname}`
    const plain = method === 'GET' ? [`${u.pathname}${u.search}`, u.pathname] : []
    const key = [keyFull, keyPath, ...plain].find(k => k in routes)
    if (!key) throw new Error(`Unmocked request: ${keyFull}`)
    let r = routes[key]
    if (typeof r === 'function') r = await r({ url: u, method, body: init.body ? JSON.parse(init.body) : undefined, init })
    if (r instanceof Error) throw r
    if (r instanceof Response) return r
    return jsonResponse(r)
  })
  globalThis.fetch = fn
  return fn
}

export const networkDown = () => new TypeError('Failed to fetch')

export function renderAt(ui, { path = '/', route = '/' } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path={path} element={ui} />
        <Route path="*" element={<div data-testid="other-route" />} />
      </Routes>
    </MemoryRouter>
  )
}
