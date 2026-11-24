// Shared loading / error / empty states and the risk badge (CHURN-27, CHURN-29).
import { AlertTriangle, RefreshCw, Inbox } from 'lucide-react'

export function Loading({ label = 'Loading…', height = 200 }) {
  return (
    <div role="status" aria-live="polite"
      style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, height }}>
      <div className="spinner" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </div>
  )
}

const TITLES = {
  network: 'Cannot reach the API',
  timeout: 'The API took too long to respond',
  invalid: 'Unexpected response from the API',
  http:    'The request failed',
}

export function ErrorState({ error, onRetry, title, compact = false }) {
  if (!error) return null
  const heading = title || (error.status === 404 ? 'Not found' : TITLES[error.kind] || 'Something went wrong')
  return (
    <div role="alert" className="error-box" style={{ padding: compact ? '10px 12px' : 20 }}>
      <AlertTriangle size={compact ? 14 : 18} style={{ color: 'var(--red)', flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: compact ? 12 : 14, fontWeight: 600, color: 'var(--text)' }}>{heading}</p>
        <p style={{ fontSize: 12, color: 'var(--text2)', marginTop: 3, overflowWrap: 'anywhere' }}>{error.message}</p>
        {error.fieldErrors?.length > 0 && (
          <ul style={{ margin: '6px 0 0 16px', fontSize: 12, color: 'var(--text2)' }}>
            {error.fieldErrors.map((f, i) => <li key={i}>{f.field}: {f.message}</li>)}
          </ul>
        )}
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary">
          <RefreshCw size={13} aria-hidden="true" /> Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, children }) {
  return (
    <div style={{ textAlign: 'center', padding: 48, color: 'var(--text2)' }}>
      <Inbox size={28} style={{ margin: '0 auto 10px', opacity: 0.4 }} aria-hidden="true" />
      <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{title}</p>
      {children && <p style={{ fontSize: 12, marginTop: 4 }}>{children}</p>}
    </div>
  )
}

// Risk badge — NOT_SCORED = no out-of-sample model prediction (never shown as LOW).
export function RiskBadge({ level }) {
  const cls = level === 'HIGH' ? 'badge-high' : level === 'MEDIUM' ? 'badge-medium'
            : level === 'LOW' ? 'badge-low' : 'badge-none'
  return <span className={cls}>{level === 'NOT_SCORED' || !level ? 'NOT SCORED' : level}</span>
}

// Colour for a value that carries a backend risk level (thresholds live in the backend).
export const riskColor = (level) =>
  level === 'HIGH' ? 'var(--red)' : level === 'MEDIUM' ? 'var(--yellow)' : level === 'LOW' ? 'var(--green)' : 'var(--text2)'
