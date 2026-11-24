import { api } from '../api/churniq'
import { useApi } from '../hooks/useApi'
import { Loading, ErrorState } from '../components/Status'
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer
} from 'recharts'

// CHURN-53: nothing on this page is hard-coded. Every figure and every insight
// is derived from GET /segments. The API's rates are average *predicted* churn
// probabilities (model output), so the page labels them as predicted.

const isNum = (v) => typeof v === 'number' && Number.isFinite(v)

export const fmtRupeesK = (v) => (isNum(v) ? `₹${(v / 1000).toFixed(0)}K` : '—')
export const fmtRupees  = (v) => (isNum(v) ? `₹${Math.round(v).toLocaleString('en-US')}` : '—')

/** Per-plan monthly revenue at risk, only for plans the API gave a number for. */
export function revenueByPlan(byPlan) {
  return (byPlan || [])
    .filter(p => isNum(p.revenue_at_risk))
    .map(p => ({ segment: p.plan_type, risk: p.revenue_at_risk }))
}

function extremes(rows, key) {
  const valid = (rows || []).filter(r => isNum(r.churn_rate_pct) && r[key] != null)
  if (valid.length < 2) return null
  const sorted = [...valid].sort((a, b) => b.churn_rate_pct - a.churn_rate_pct)
  return { hi: sorted[0], lo: sorted[sorted.length - 1], key }
}

const GROUPS = [
  ['by_tenure', 'tenure_bucket',   'Tenure',          (v) => `customers with tenure ${v}`],
  ['by_device', 'device_type',     'Device',          (v) => `${v} users`],
  ['by_plan',   'plan_type',       'Plan',            (v) => `${v} plan customers`],
  ['by_genre',  'preferred_genre', 'Preferred genre', (v) => `${v} viewers`],
]

/**
 * Insights computed from the /segments response: for each grouping, the
 * highest and lowest predicted churn rate, plus the overall average.
 * Groups with fewer than two usable rows are skipped rather than guessed.
 */
export function buildInsights(s) {
  if (!s) return []
  const out = []
  for (const [field, key, label, name] of GROUPS) {
    const e = extremes(s[field], key)
    if (!e) continue
    const gap = Math.round((e.hi.churn_rate_pct - e.lo.churn_rate_pct) * 10) / 10
    out.push(`${label}: ${name(e.hi[key])} have the highest predicted churn rate (${e.hi.churn_rate_pct}%), ` +
             `${gap} points above ${name(e.lo[key])} (${e.lo.churn_rate_pct}%).`)
  }
  const o = s.overall
  if (o && isNum(o.avg_churn_rate_pct) && isNum(o.scored_customers)) {
    out.push(`Average predicted churn rate across ${o.scored_customers.toLocaleString('en-US')} scored customers: ${o.avg_churn_rate_pct}%.`)
  }
  return out
}

const tip = { background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, color: 'var(--text)' }

function ChartCard({ title, children }) {
  return (
    <div className="card fade-in">
      <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 16 }}>{title}</p>
      {children}
    </div>
  )
}

export default function SegmentAnalysis() {
  // CHURN-29: no mock fallback — a failed request shows an error with Retry.
  const { data: s, error, loading, reload } = useApi((signal) => api.getSegments({ signal }), [])

  if (loading) return <Loading label="Loading segments…" height={300} />
  if (error) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>Segment Analysis</h2>
      <ErrorState error={error} onRetry={reload} title="Segment data could not be loaded" />
    </div>
  )

  const avg = s.overall?.avg_churn_rate_pct
  const revenue = revenueByPlan(s.by_plan)
  const insights = buildInsights(s)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>Segment Analysis</h2>
        <p style={{ fontSize: 13, color: 'var(--text2)', marginTop: 3 }}>Predicted churn breakdown by key customer segments</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 14 }}>

        {/* By Plan */}
        <ChartCard title="Churn Rate by Plan Type">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={s.by_plan} barSize={44} margin={{ left: -20 }}>
              <XAxis dataKey="plan_type" tick={{ fontSize: 12, fill: 'var(--text2)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text2)' }} axisLine={false} tickLine={false} unit="%" />
              <Tooltip formatter={v => [`${v}%`, 'Churn Rate']} contentStyle={tip} />
              <Bar dataKey="churn_rate_pct" fill="var(--text)" radius={[6,6,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* By Device */}
        <ChartCard title="Churn Rate by Device Type">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={s.by_device} barSize={36} margin={{ left: -20 }}>
              <XAxis dataKey="device_type" tick={{ fontSize: 11, fill: 'var(--text2)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text2)' }} axisLine={false} tickLine={false} unit="%" />
              <Tooltip formatter={v => [`${v}%`, 'Churn Rate']} contentStyle={tip} />
              <Bar dataKey="churn_rate_pct" fill="var(--text2)" radius={[6,6,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* By Tenure */}
        <ChartCard title="Churn Rate by Tenure Bucket">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={s.by_tenure} margin={{ left: -20 }}>
              <XAxis dataKey="tenure_bucket" tick={{ fontSize: 11, fill: 'var(--text2)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text2)' }} axisLine={false} tickLine={false} unit="%" />
              <Tooltip formatter={v => [`${v}%`, 'Churn Rate']} contentStyle={tip} />
              <Line type="monotone" dataKey="churn_rate_pct" stroke="var(--text)" strokeWidth={2.5} dot={{ r: 4, fill: 'var(--text)' }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Genre table */}
        <ChartCard title="Churn Rate by Preferred Genre">
          <table className="tbl">
            <thead>
              <tr>
                <th>Genre</th>
                <th>Churn Rate</th>
                <th>vs Average{isNum(avg) ? ` (${avg}%)` : ''}</th>
              </tr>
            </thead>
            <tbody>
              {s.by_genre?.map(g => {
                const above = isNum(avg) && isNum(g.churn_rate_pct) ? g.churn_rate_pct > avg : null
                return (
                  <tr key={g.preferred_genre}>
                    <td style={{ fontWeight: 500 }}>{g.preferred_genre}</td>
                    <td style={{ fontWeight: 700, fontFamily: 'var(--mono)', color: above ? 'var(--red)' : above === false ? 'var(--green)' : 'var(--text2)' }}>
                      {isNum(g.churn_rate_pct) ? `${g.churn_rate_pct}%` : '—'}
                    </td>
                    <td>
                      {above === null ? '—' : (
                        <span className={above ? 'badge-high' : 'badge-low'}>{above ? 'Above' : 'At or below'}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </ChartCard>

        {/* Revenue at Risk — GET /segments by_plan[].revenue_at_risk */}
        <ChartCard title="Monthly Revenue at Risk by Plan">
          {revenue.length === 0 ? (
            <p data-testid="revenue-unavailable" style={{ fontSize: 12, color: 'var(--text2)' }}>
              Revenue at risk by plan is not available from the API.
            </p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={revenue} barSize={44} margin={{ left: -20 }}>
                  <XAxis dataKey="segment" tick={{ fontSize: 12, fill: 'var(--text2)' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: 'var(--text2)' }} axisLine={false} tickLine={false} tickFormatter={fmtRupeesK} />
                  <Tooltip formatter={v => [fmtRupees(v), 'Revenue at Risk / mo']} contentStyle={tip} />
                  <Bar dataKey="risk" fill="var(--yellow)" radius={[6,6,0,0]} />
                </BarChart>
              </ResponsiveContainer>
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${revenue.length}, 1fr)`, gap: 8, marginTop: 12 }}>
                {revenue.map(r => (
                  <div key={r.segment} data-testid={`revenue-${r.segment}`} style={{ textAlign: 'center', padding: '10px 6px', borderRadius: 8, background: 'var(--bg2)', border: '1px solid var(--border)' }}>
                    <p style={{ fontSize: 10, color: 'var(--text2)', marginBottom: 3 }}>{r.segment}</p>
                    <p style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{fmtRupees(r.risk)}</p>
                  </div>
                ))}
              </div>
            </>
          )}
          <p data-testid="revenue-total" style={{ fontSize: 11, color: 'var(--text2)', marginTop: 10 }}>
            Total: {fmtRupees(s.overall?.total_revenue_at_risk)} / month (monthly charge × predicted churn probability)
          </p>
        </ChartCard>

        {/* Insights — computed from the same response */}
        <div className="card fade-in" style={{ borderLeft: '3px solid var(--text)' }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>Insights from the data</p>
          <p style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 14 }}>Computed from the segment figures above.</p>
          {insights.length === 0 ? (
            <p style={{ fontSize: 12, color: 'var(--text2)' }}>Not enough segment data to compare.</p>
          ) : (
            <ol data-testid="insights" style={{ display: 'flex', flexDirection: 'column', gap: 10, listStyle: 'none', margin: 0, padding: 0 }}>
              {insights.map((ins, i) => (
                <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  <span aria-hidden="true" style={{
                    width: 20, height: 20, borderRadius: '50%',
                    background: 'var(--bg2)', border: '1px solid var(--border)',
                    color: 'var(--text2)', fontSize: 10, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
                  }}>{i + 1}</span>
                  <p style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.5 }}>{ins}</p>
                </li>
              ))}
            </ol>
          )}
        </div>

      </div>
    </div>
  )
}
