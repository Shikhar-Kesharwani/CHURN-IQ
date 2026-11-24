import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Users, BarChart3, TrendingUp, UserCheck,
  Sun, Moon, ChevronLeft, ChevronRight, Zap, Menu, X
} from 'lucide-react'
import Dashboard      from './pages/Dashboard'
import RiskTable      from './pages/RiskTable'
import CustomerDetail from './pages/CustomerDetail'
import SegmentAnalysis from './pages/SegmentAnalysis'
import ChurnPredict   from './pages/ChurnPredict'
import CustomerSimilarity from './pages/CustomerSimilarity'
import { api } from './api/churniq'

export const NAV = [
  { to: '/',           icon: LayoutDashboard, label: 'Dashboard'         },
  { to: '/risk',       icon: Users,           label: 'Risk Table'        },
  { to: '/segments',   icon: BarChart3,       label: 'Segments'          },
  { to: '/predict',    icon: TrendingUp,      label: 'Churn Predict'     },
  { to: '/similarity', icon: UserCheck,       label: 'Similarity Finder' },
]

const THEME_KEY = 'churniq_theme'

// Light by default (as before); the user's last choice is remembered.
function initialDark() {
  try { return localStorage.getItem(THEME_KEY) === 'dark' } catch { return false }
}

function Sidebar({ collapsed, setCollapsed, open, onNavigate }) {
  return (
    <aside
      id="app-sidebar"
      className={`sidebar${open ? ' open' : ''}`}
      aria-label="Main navigation"
      style={{
        width: collapsed ? 60 : 220,
        background: 'var(--sidebar)',
        borderRight: '1px solid rgba(255,255,255,0.06)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.25s cubic-bezier(.4,0,.2,1)',
        flexShrink: 0,
        position: 'relative',
        zIndex: 10,
      }}
    >
      {/* Logo */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: collapsed ? '18px 0' : '18px 18px',
        justifyContent: collapsed ? 'center' : 'flex-start',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
      }}>
        <div style={{
          width: 30, height: 30, borderRadius: 8,
          background: 'white', display: 'flex', alignItems: 'center',
          justifyContent: 'center', flexShrink: 0,
        }}>
          <Zap size={15} color="#0f0f0f" aria-hidden="true" />
        </div>
        {!collapsed && (
          <span style={{ color: 'var(--sid-text)', fontWeight: 700, fontSize: 14, letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>
            ChurnIQ Pro
          </span>
        )}
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to} to={to} end={to === '/'}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            aria-label={collapsed ? label : undefined}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center',
              gap: collapsed ? 0 : 10,
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? '10px 0' : '9px 12px',
              borderRadius: 8,
              fontWeight: 500, fontSize: 13,
              textDecoration: 'none',
              color: isActive ? 'var(--sid-act-t)' : 'var(--sid-muted)',
              background: isActive ? 'var(--sid-active)' : 'transparent',
              transition: 'all 0.15s',
            })}
            className="nav-item"
          >
            <Icon size={16} style={{ flexShrink: 0 }} aria-hidden="true" />
            {!collapsed && <span style={{ whiteSpace: 'nowrap' }}>{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Collapse button (desktop only) */}
      <button
        type="button"
        className="collapse-btn"
        onClick={() => setCollapsed(!collapsed)}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-expanded={!collapsed}
        style={{
          margin: '0 auto 16px',
          width: 28, height: 28, borderRadius: '50%',
          border: '1px solid rgba(255,255,255,0.1)',
          background: 'transparent',
          color: 'var(--sid-muted)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', transition: 'all 0.15s',
        }}
      >
        {collapsed ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronLeft size={14} aria-hidden="true" />}
      </button>
    </aside>
  )
}

// CHURN-29: real API status instead of a hard-coded "API Live" label.
function ApiStatus() {
  const [status, setStatus] = useState('checking')
  useEffect(() => {
    let active = true
    const check = () => api.health({ timeoutMs: 8000 }).then(({ error }) => {
      if (active) setStatus(error ? 'down' : 'up')
    })
    check()
    const id = setInterval(check, 60000)
    return () => { active = false; clearInterval(id) }
  }, [])
  const look = {
    up:       { text: 'API connected',   color: 'var(--green)',  bg: 'rgba(56,161,105,0.12)' },
    down:     { text: 'API unreachable', color: 'var(--red)',    bg: 'rgba(229,62,62,0.12)' },
    checking: { text: 'Checking API…',   color: 'var(--text2)',  bg: 'var(--bg2)' },
  }[status]
  return (
    <span role="status" aria-live="polite" data-api-status={status} style={{
      fontSize: 11, fontWeight: 600, background: look.bg, color: look.color,
      padding: '3px 10px', borderRadius: 20, whiteSpace: 'nowrap',
    }}>
      ● {look.text}
    </span>
  )
}

function Navbar({ dark, setDark, menuOpen, setMenuOpen }) {
  return (
    <header className="navbar" style={{
      height: 56,
      background: 'var(--card)',
      borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 24px',
      gap: 10,
      flexShrink: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
        <button
          type="button"
          className="menu-btn btn-secondary"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={menuOpen}
          aria-controls="app-sidebar"
          style={{ padding: 7 }}
        >
          {menuOpen ? <X size={16} aria-hidden="true" /> : <Menu size={16} aria-hidden="true" />}
        </button>
        <div style={{ minWidth: 0 }}>
          <p style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', letterSpacing: '-0.01em' }}>
            ChurnIQ Pro
          </p>
          <p className="navbar-subtitle" style={{ fontSize: 11, color: 'var(--text2)', marginTop: 1 }}>
            OTT Churn Intelligence Platform
          </p>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <ApiStatus />
        <button
          type="button"
          onClick={() => setDark(!dark)}
          aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
          aria-pressed={dark}
          title={dark ? 'Switch to light theme' : 'Switch to dark theme'}
          style={{
            width: 34, height: 34, borderRadius: 8,
            border: '1px solid var(--border)',
            background: 'var(--bg2)',
            color: 'var(--text2)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', transition: 'all 0.15s', flexShrink: 0,
          }}
        >
          {dark ? <Sun size={15} aria-hidden="true" /> : <Moon size={15} aria-hidden="true" />}
        </button>
      </div>
    </header>
  )
}

export function NotFound() {
  return (
    <div style={{ textAlign: 'center', padding: 48 }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>Page not found</h2>
      <p style={{ fontSize: 13, color: 'var(--text2)', marginTop: 6 }}>
        There is no page at this address.
      </p>
      <Link to="/" className="btn-secondary" style={{ marginTop: 16, textDecoration: 'none' }}>
        Go to the dashboard
      </Link>
    </div>
  )
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/"           element={<Dashboard />} />
      <Route path="/risk"       element={<RiskTable />} />
      <Route path="/risk/:id"   element={<CustomerDetail />} />
      <Route path="/segments"   element={<SegmentAnalysis />} />
      <Route path="/predict"    element={<ChurnPredict />} />
      <Route path="/similarity" element={<CustomerSimilarity />} />
      <Route path="*"           element={<NotFound />} />
    </Routes>
  )
}

function Layout({ dark, setDark }) {
  const [collapsed, setCollapsed] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  // Close the mobile menu on navigation and on Escape.
  useEffect(() => { setMenuOpen(false) }, [location.pathname])
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e) => { if (e.key === 'Escape') setMenuOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  return (
    <div className="app-shell">
      <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} open={menuOpen} onNavigate={() => setMenuOpen(false)} />
      <div className={`sidebar-backdrop${menuOpen ? ' open' : ''}`} onClick={() => setMenuOpen(false)} aria-hidden="true" />
      <div className="app-col">
        <Navbar dark={dark} setDark={setDark} menuOpen={menuOpen} setMenuOpen={setMenuOpen} />
        <main className="app-main">
          <AppRoutes />
        </main>
      </div>
    </div>
  )
}

export default function App() {
  const [dark, setDark] = useState(initialDark)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try { localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light') } catch { /* storage unavailable */ }
  }, [dark])

  return (
    <BrowserRouter>
      <Layout dark={dark} setDark={setDark} />
    </BrowserRouter>
  )
}
