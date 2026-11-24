import { Link } from 'react-router-dom'
import { api } from '../api/churniq'
import { useApi } from '../hooks/useApi'
import { Loading, ErrorState, RiskBadge } from '../components/Status'
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import { Users, AlertTriangle, DollarSign, TrendingDown } from 'lucide-react'

// CHURN-26: every value on this page comes from GET /dashboard/summary or
// GET /segments. There are no fallback numbers: a missing value shows "—",
// a real 0 shows "0", and a failed request shows an error with Retry.

const tipStyle = {
  background: 'var(--card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  fontSize: 12,
  color: 'var(--text)',
}

export const fmtInt = (n) => (typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('en-US') : '—')
export const fmtRupees = (n) => (typeof n === 'number' && Number.isFinite(n)
  ? `₹${Math.round(n).toLocaleString('en-US')}` : '—')
const show = (v) => (v === null || v === undefined || v === '' ? '—' : v)

const REASON_LABELS = {
  low_engagement: 'Low engagement (< 3 watch hrs/week)',
  payment_issues: 'Payment failures (last 3 months)',
  new_customers:  'New customers (< 6 months tenure)',
  support_issues: 'More than 1 support ticket',
}
const PLAN_ORDER = ['Basic', 'Standard', 'Premium']
const CLV_ORDER = ['High', 'Medium', 'Low']

/** Customer-weighted average CLV from /segments by_plan (avg_clv × count). */
export function weightedAvgClv(byPlan) {
  if (!Array.isArray(byPlan) || byPlan.length === 0) return null
  let total = 0, n = 0
  for (const p of byPlan) {
    if (typeof p.avg_clv !== 'number' || typeof p.count !== 'number') return null
    total += p.avg_clv * p.count
    n += p.count
  }
  return n ? total / n : null
}

function KPICard({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="card fade-in" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
      <div style={{
        width: 44, height: 44, borderRadius: 10, flexShrink: 0,
        background: 'var(--bg2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={20} style={{ color }} aria-hidden="true" />
      </div>
      <div style={{ minWidth: 0 }}>
        <p style={{ fontSize: 11, color: 'var(--text2)', fontWeight: 500, marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</p>
        <p data-testid={`kpi-${label}`} style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em', lineHeight: 1 }}>{value}</p>
        {sub && <p style={{ fontSize: 11, color: 'var(--text3)', marginTop: 3 }}>{sub}</p>}
      </div>
    </div>
  )
}

function ChartCard({ title, children, note }) {
  return (
    // overflow: hidden keeps recharts' off-screen tooltip from widening the page on mobile (CHURN-30)
    <div className="card fade-in" style={{ minWidth: 0, overflow: 'hidden' }}>
      <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 16 }}>{title}</p>
      {children}
      {note && <p className="note">{note}</p>}
    </div>
  )
}

export default function Dashboard() {
  const summary  = useApi((signal) => api.getDashboard({ signal }), [])
  const segments = useApi((signal) => api.getSegments({ signal }), [])

  if (summary.loading) return <Loading label="Loading dashboard…" height={300} />
  if (summary.error) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <PageHeader />
        <ErrorState error={summary.error} onRetry={summary.reload} title="Dashboard data could not be loaded" />
      </div>
    )
  }

  const d = summary.data
  const k = d.kpis || {}
  const reasons = Object.entries(d.churn_reasons_breakdown || {}).map(([key, value]) => ({
    name: REASON_LABELS[key] || key, value,
  }))

  const seg = segments.data
  const plans = (seg?.by_plan || [])
    .map(p => ({ plan: p.plan_type, rate: p.churn_rate_pct }))
    .sort((a, b) => PLAN_ORDER.indexOf(a.plan) - PLAN_ORDER.indexOf(b.plan))
  const clvSegments = (seg?.by_clv || [])
    .filter(c => CLV_ORDER.includes(c.clv_segment))
    .sort((a, b) => CLV_ORDER.indexOf(a.clv_segment) - CLV_ORDER.indexOf(b.clv_segment))
  const avgClv = weightedAvgClv(seg?.by_plan)
  const trend = (seg?.monthly_trend || []).map(t => ({ m: t.month, v: t.churn_rate }))

  const segmentsPlaceholder = segments.loading
    ? <Loading height={200} label="Loading segment data…" />
    : <ErrorState compact error={segments.error} onRetry={segments.reload} title="Segment data could not be loaded" />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageHeader />

      {/* KPI row — GET /dashboard/summary → kpis */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(200px, 100%), 1fr))', gap: 14 }}>
        <KPICard icon={Users} label="Total Customers" value={fmtInt(k.total_customers)} color="var(--text)"
          sub={k.unscored_count > 0 ? `${fmtInt(k.unscored_count)} not scored by the model` : `${fmtInt(k.scored_customers)} scored by the model`} />
        <KPICard icon={AlertTriangle} label="High Risk Count" value={fmtInt(k.high_risk_count)} color="var(--red)"
          sub={typeof k.high_risk_pct === 'number' ? `${k.high_risk_pct}% of scored · ≥70% churn probability` : '≥70% churn probability'} />
        <KPICard icon={DollarSign} label="Revenue at Risk / mo" value={show(k.revenue_at_risk_formatted)} color="var(--yellow)"
          sub="Σ monthly charge × churn probability" />
        <KPICard icon={TrendingDown} label="Avg Churn Probability" value={show(k.avg_churn_percent)} color="var(--blue)"
          sub="Mean over scored customers" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(380px, 100%), 1fr))', gap: 14 }}>

        {/* Risk signals — GET /dashboard/summary → churn_reasons_breakdown */}
        <ChartCard title="Churn Risk Signals — Customers Affected"
          note="A customer can show several signals, so these counts overlap and do not add up to the total.">
          {reasons.length === 0 ? <p className="note">No data returned.</p> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={reasons} layout="vertical" margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--text2)' }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 10, fill: 'var(--text2)' }} axisLine={false} tickLine={false} />
                <Tooltip formatter={v => [fmtInt(v), 'Customers']} contentStyle={tipStyle} cursor={{ fill: 'var(--bg2)' }} />
                <Bar dataKey="value" fill="var(--text)" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        {/* Plan churn — GET /segments → by_plan */}
        <ChartCard title="Average Churn Probability by Plan Type" note={segments.data ? 'Source: /segments (by_plan.churn_rate_pct).' : null}>
          {!segments.data ? segmentsPlaceholder : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={plans} barSize={40} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <XAxis dataKey="plan" tick={{ fontSize: 12, fill: 'var(--text2)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text2)' }} axisLine={false} tickLine={false} unit="%" />
                <Tooltip formatter={v => [`${v}%`, 'Avg churn probability']} contentStyle={tipStyle} cursor={{ fill: 'var(--bg2)' }} />
                <Bar dataKey="rate" fill="var(--text)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        {/* CLV — GET /segments → by_plan (weighted average) and by_clv (tier counts) */}
        <ChartCard title="Customer Lifetime Value"
          note={segments.data ? 'Average CLV is weighted by plan size (by_plan); tier counts come from by_clv.' : null}>
          {!segments.data ? segmentsPlaceholder : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 10 }}>
              {[{ label: 'Avg CLV', value: fmtRupees(avgClv), sub: 'per customer' },
                ...clvSegments.map(c => ({ label: `${c.clv_segment} CLV tier`, value: fmtInt(c.count), sub: 'customers' })),
              ].map(({ label, value, sub }) => (
                <div key={label} style={{
                  border: '1px solid var(--border)', borderRadius: 10, background: 'var(--bg2)',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  padding: '12px 8px', textAlign: 'center',
                }}>
                  <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{label}</p>
                  <p data-testid={`clv-${label}`} style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>{value}</p>
                  <p style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4 }}>{sub}</p>
                </div>
              ))}
            </div>
          )}
        </ChartCard>

        {/* Trend — GET /segments → monthly_trend (simulated by the API) */}
        <ChartCard title="Monthly Churn Trend (simulated)"
          note={segments.data ? 'Illustrative only: the dataset has no monthly history, so the API generates this series around the current average. It is not observed data.' : null}>
          {!segments.data ? segmentsPlaceholder : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={trend} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <XAxis dataKey="m" tick={{ fontSize: 11, fill: 'var(--text2)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text2)' }} axisLine={false} tickLine={false} unit="%" domain={['auto', 'auto']} />
                <Tooltip formatter={v => [`${v}%`, 'Simulated churn rate']} contentStyle={tipStyle} />
                <Line type="monotone" dataKey="v" stroke="var(--text)" strokeWidth={2} strokeDasharray="5 4" dot={false} activeDot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      {/* Priority customers — GET /dashboard/summary → priority_customers */}
      {d.priority_customers?.length > 0 && (
        <div className="card fade-in" style={{ minWidth: 0 }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 14 }}>
            Top Priority — High CLV + High Risk
          </p>
          <div className="table-scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th scope="col">Customer ID</th>
                  <th scope="col">Churn Risk</th>
                  <th scope="col">Plan</th>
                  <th scope="col">CLV Score</th>
                  <th scope="col">Risk Level</th>
                </tr>
              </thead>
              <tbody>
                {d.priority_customers.map(c => (
                  <tr key={c.customer_id}>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>
                      <Link to={`/risk/${c.customer_id}`} style={{ color: 'var(--text)' }}>{c.customer_id}</Link>
                    </td>
                    <td style={{ fontWeight: 700, color: 'var(--red)' }}>{c.churn_pct}</td>
                    <td>{c.plan_type}</td>
                    <td style={{ fontWeight: 600 }}>{fmtRupees(c.clv_score)}</td>
                    <td><RiskBadge level={c.risk_level} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function PageHeader() {
  return (
    <div>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>Dashboard</h2>
      <p style={{ fontSize: 13, color: 'var(--text2)', marginTop: 3 }}>OTT churn intelligence overview</p>
    </div>
  )
}
