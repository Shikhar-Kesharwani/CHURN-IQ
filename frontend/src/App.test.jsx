// CHURN-29 / CHURN-30: navigation reaches every page, unknown routes, theme, API status, mobile menu.
import { describe, it, expect } from 'vitest'
import { screen, render, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App, { NAV } from './App'
import SegmentAnalysis from './pages/SegmentAnalysis'
import { mockFetch, renderAt, networkDown } from './test/helpers'
import dashboard from './test/fixtures/dashboard.json'
import segments from './test/fixtures/segments.json'
import sample from './test/fixtures/customers-sample.json'
import sim3 from './test/fixtures/similarity-CUST00001-3.json'

const ROUTES = {
  '/': dashboard,
  '/dashboard/summary': dashboard,
  '/segments': segments,
  '/customers?limit=10000': sample,
  'POST /api/customer-similarity': sim3,
}

function renderApp(path = '/') {
  window.history.pushState({}, '', path)
  return render(<App />)
}

describe('App shell', () => {
  it('has exactly one navigation entry per page, with no duplicates', () => {
    mockFetch(ROUTES)
    renderApp('/')
    const nav = screen.getByRole('complementary', { name: 'Main navigation' })
    const links = within(nav).getAllByRole('link')
    expect(links.map(l => l.getAttribute('href'))).toEqual(NAV.map(n => n.to))
    expect(new Set(links.map(l => l.getAttribute('href'))).size).toBe(links.length)
  })

  it('reaches every page from the sidebar', async () => {
    mockFetch(ROUTES)
    renderApp('/')
    const nav = screen.getByRole('complementary', { name: 'Main navigation' })
    const expectations = {
      'Risk Table': 'Customer Risk Table',
      'Segments': 'Segment Analysis',
      'Churn Predict': 'Churn Predict — What-If',
      'Similarity Finder': 'Customer Similarity Finder',
      'Dashboard': 'Dashboard',
    }
    for (const [label, heading] of Object.entries(expectations)) {
      await userEvent.click(within(nav).getByRole('link', { name: label }))
      expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
    }
  })

  it('shows "Page not found" with a way back for unknown routes', async () => {
    mockFetch(ROUTES)
    renderApp('/does-not-exist')
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to the dashboard' })).toHaveAttribute('href', '/')
  })

  it('toggles the theme, labels the button, and remembers the choice', async () => {
    mockFetch(ROUTES)
    const { unmount } = renderApp('/does-not-exist')
    expect(document.documentElement).not.toHaveClass('dark')
    await userEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
    expect(document.documentElement).toHaveClass('dark')
    expect(localStorage.getItem('churniq_theme')).toBe('dark')
    unmount()
    renderApp('/does-not-exist')
    expect(document.documentElement).toHaveClass('dark')
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('gives icon-only controls accessible names', () => {
    mockFetch(ROUTES)
    renderApp('/does-not-exist')
    expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open navigation menu' })).toHaveAttribute('aria-controls', 'app-sidebar')
  })

  it('opens and closes the mobile menu (button, Escape, navigation)', async () => {
    mockFetch(ROUTES)
    renderApp('/does-not-exist')
    const sidebar = document.getElementById('app-sidebar')
    await userEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }))
    expect(sidebar).toHaveClass('open')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(sidebar).not.toHaveClass('open')
    await userEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }))
    await userEvent.click(within(sidebar).getByRole('link', { name: 'Segments' }))
    expect(sidebar).not.toHaveClass('open')
  })

  it('shows the real API status: connected', async () => {
    mockFetch(ROUTES)
    renderApp('/does-not-exist')
    expect(await screen.findByText('● API connected')).toBeInTheDocument()
  })

  it('shows the real API status: unreachable', async () => {
    mockFetch({ '/': networkDown() })
    renderApp('/does-not-exist')
    expect(await screen.findByText('● API unreachable')).toBeInTheDocument()
    expect(screen.queryByText(/API Live/)).not.toBeInTheDocument()
  })
})

describe('Segments page (CHURN-29 only: no mock fallback)', () => {
  it('shows an error with Retry instead of mock charts when the API is down', async () => {
    mockFetch({ '/segments': networkDown() })
    renderAt(<SegmentAnalysis />)
    expect(await screen.findByText('Segment data could not be loaded')).toBeInTheDocument()
    expect(screen.queryByText('Churn Rate by Plan Type')).not.toBeInTheDocument()
    mockFetch({ '/segments': segments })
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByText('Churn Rate by Plan Type')).toBeInTheDocument()
  })
})
