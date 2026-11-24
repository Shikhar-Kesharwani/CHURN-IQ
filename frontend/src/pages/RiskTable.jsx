import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/churniq'
import { useApi } from '../hooks/useApi'
import { Loading, ErrorState, EmptyState, RiskBadge, riskColor } from '../components/Status'
import { Search, Eye, ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'

// CHURN-27: all customers are loaded once (GET /customers?limit=10000) and
// filtered / sorted / paginated in the browser. Values are shown exactly as the
// API returns them; risk colours follow the backend's risk_level.

const RISK_RANK = { HIGH: 3, MEDIUM: 2, LOW: 1 }   // NOT_SCORED / null → no rank (sorted last)
const PAGE_SIZES = [25, 50, 100]

const COLUMNS = [
  { label: 'Customer ID',     key: 'customer_id' },
  { label: 'Name',            key: 'name' },
  { label: 'Churn %',         key: 'churn_prob' },
  { label: 'Risk',            key: 'risk_level' },
  { label: 'Plan',            key: 'plan_type' },
  { label: 'CLV Score',       key: 'clv_score' },
  { label: 'Top Risk Factor', key: null },
  { label: 'Action',          key: null },
]

function sortValue(row, key) {
  if (key === 'risk_level') return RISK_RANK[row.risk_level] ?? null
  const v = row[key]
  return v === undefined ? null : v
}

/** Pure filter + sort used by the page (exported for tests). */
export function filterAndSort(rows, { search = '', risk = 'ALL', plan = 'ALL', sort = { key: 'churn_prob', dir: 'desc' } }) {
  const q = search.trim().toLowerCase()
  let list = rows.filter(c =>
    (!q || c.customer_id.toLowerCase().includes(q) || (c.name || '').toLowerCase().includes(q)) &&
    (risk === 'ALL' || (risk === 'NOT_SCORED' ? !(c.risk_level in RISK_RANK) : c.risk_level === risk)) &&
    (plan === 'ALL' || c.plan_type === plan)
  )
  const dir = sort.dir === 'asc' ? 1 : -1
  list = [...list].sort((a, b) => {
    const va = sortValue(a, sort.key), vb = sortValue(b, sort.key)
    // Missing values (e.g. unscored customers) always sort last, in both directions.
    if (va === null || vb === null) {
      if (va === null && vb === null) return a.customer_id.localeCompare(b.customer_id)
      return va === null ? 1 : -1
    }
    const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb
    // Ties: always by customer ID ascending, so the order is deterministic.
    return cmp !== 0 ? cmp * dir : a.customer_id.localeCompare(b.customer_id)
  })
  return list
}

function Sel({ value, onChange, options, label }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} className="inp" aria-label={label}
      style={{ width: 'auto', minWidth: 130 }}>
      {options.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  )
}

export default function RiskTable() {
  const { data, error, loading, reload } = useApi((signal) => api.getCustomers({ signal }), [])
  const [search, setSearch]     = useState('')
  const [risk, setRisk]         = useState('ALL')
  const [plan, setPlan]         = useState('ALL')
  const [sort, setSort]         = useState({ key: 'churn_prob', dir: 'desc' })
  const [page, setPage]         = useState(1)
  const [pageSize, setPageSize] = useState(25)

  const all = data?.customers || []
  const rows = useMemo(() => filterAndSort(all, { search, risk, plan, sort }), [all, search, risk, plan, sort])

  // Back to page 1 whenever the result set changes.
  useEffect(() => { setPage(1) }, [search, risk, plan, sort, pageSize])

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const current = Math.min(page, pageCount)
  const start = (current - 1) * pageSize
  const pageRows = rows.slice(start, start + pageSize)

  const sortBy = (key) => setSort(s => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }))
  const sortLabel = COLUMNS.find(c => c.key === sort.key)?.label || sort.key

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>Customer Risk Table</h2>
        <p style={{ fontSize: 13, color: 'var(--text2)', marginTop: 3 }} aria-live="polite">
          {loading ? 'Loading customers…'
            : error ? 'Customers could not be loaded'
            : `${rows.length.toLocaleString('en-US')} of ${all.length.toLocaleString('en-US')} customers — sorted by ${sortLabel} (${sort.dir === 'desc' ? 'high → low' : 'low → high'})`}
        </p>
      </div>

      {/* Filters */}
      <div className="card" style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', padding: 14 }}>
        <div style={{ position: 'relative', flex: '1 1 200px', minWidth: 0 }}>
          <Search size={13} aria-hidden="true" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text2)' }} />
          <input
            className="inp" placeholder="Search name or ID..." aria-label="Search by customer name or ID"
            type="search" value={search} onChange={e => setSearch(e.target.value)}
            style={{ paddingLeft: 32 }}
          />
        </div>
        <Sel label="Filter by risk level" value={risk} onChange={setRisk} options={[
          { v: 'ALL', l: 'All Risk Levels' },
          { v: 'HIGH', l: 'High Risk' },
          { v: 'MEDIUM', l: 'Medium Risk' },
          { v: 'LOW', l: 'Low Risk' },
          { v: 'NOT_SCORED', l: 'Not Scored' },
        ]} />
        <Sel label="Filter by plan" value={plan} onChange={setPlan} options={[
          { v: 'ALL', l: 'All Plans' },
          { v: 'Basic', l: 'Basic' },
          { v: 'Standard', l: 'Standard' },
          { v: 'Premium', l: 'Premium' },
        ]} />
      </div>

      {/* Table */}
      <div className="card fade-in" style={{ padding: 0, overflow: 'hidden', minWidth: 0 }}>
        {loading ? (
          <Loading label="Loading customers…" />
        ) : error ? (
          <div style={{ padding: 16 }}>
            <ErrorState error={error} onRetry={reload} title="Customers could not be loaded" />
          </div>
        ) : all.length === 0 ? (
          <EmptyState title="No customers returned by the API" />
        ) : rows.length === 0 ? (
          <EmptyState title="No customers match the current filters">
            Try a different search term or clear the filters.
          </EmptyState>
        ) : (
          <>
            <div className="table-scroll">
              <table className="tbl">
                <caption className="sr-only">Customers by churn risk</caption>
                <thead>
                  <tr>
                    {COLUMNS.map(({ label, key }) => (
                      <th key={label} scope="col"
                        aria-sort={key && sort.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                        {key ? (
                          <button type="button" onClick={() => sortBy(key)} className="th-btn"
                            style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', padding: 0, font: 'inherit', color: 'inherit', textTransform: 'inherit', letterSpacing: 'inherit', cursor: 'pointer' }}>
                            {label}
                            {sort.key === key && (sort.dir === 'asc' ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />)}
                          </button>
                        ) : label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map(c => (
                    <tr key={c.customer_id}>
                      <td style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text2)' }}>{c.customer_id}</td>
                      <td style={{ fontWeight: 500 }}>{c.name}</td>
                      <td style={{ fontWeight: 700, color: riskColor(c.risk_level) }}>{c.churn_percent}</td>
                      <td><RiskBadge level={c.risk_level} /></td>
                      <td style={{ color: 'var(--text2)', fontSize: 12 }}>{c.plan_type}</td>
                      <td style={{ fontWeight: 600 }}>{c.clv_score == null ? 'N/A' : `₹${Number(c.clv_score).toLocaleString('en-US')}`}</td>
                      <td style={{ maxWidth: 200, color: 'var(--text2)', fontSize: 11 }}>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
                          title={c.top_reason_1?.split('[')[0]?.trim()}>
                          {c.top_reason_1?.split('[')[0]?.trim()}
                        </span>
                      </td>
                      <td>
                        <Link to={`/risk/${c.customer_id}`} className="btn-secondary"
                          aria-label={`View ${c.name} (${c.customer_id})`}
                          style={{ padding: '5px 10px', fontSize: 12, fontWeight: 500, textDecoration: 'none' }}>
                          <Eye size={12} aria-hidden="true" /> View
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <nav aria-label="Pagination" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '12px 14px', borderTop: '1px solid var(--border)' }}>
              <span style={{ fontSize: 12, color: 'var(--text2)' }} data-testid="page-range">
                Showing {(start + 1).toLocaleString('en-US')}–{(start + pageRows.length).toLocaleString('en-US')} of {rows.length.toLocaleString('en-US')}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <label style={{ fontSize: 12, color: 'var(--text2)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  Rows
                  <select className="inp" value={pageSize} onChange={e => setPageSize(Number(e.target.value))} style={{ width: 'auto', padding: '4px 8px' }}>
                    {PAGE_SIZES.map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <button type="button" className="btn-secondary" style={{ padding: '5px 8px' }}
                  onClick={() => setPage(p => Math.max(1, p - 1))} disabled={current <= 1} aria-label="Previous page">
                  <ChevronLeft size={14} aria-hidden="true" />
                </button>
                <span style={{ fontSize: 12, color: 'var(--text)' }} aria-current="page">Page {current} of {pageCount}</span>
                <button type="button" className="btn-secondary" style={{ padding: '5px 8px' }}
                  onClick={() => setPage(p => Math.min(pageCount, p + 1))} disabled={current >= pageCount} aria-label="Next page">
                  <ChevronRight size={14} aria-hidden="true" />
                </button>
              </div>
            </nav>
          </>
        )}
      </div>
    </div>
  )
}
