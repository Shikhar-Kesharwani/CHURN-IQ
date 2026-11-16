import { useState, useEffect } from 'react'
import { api } from '../api/churniq'
import {
  Users, Search, GitCompare, ArrowRight, CheckCircle2,
  AlertTriangle, Clock, PlayCircle, ShieldAlert,
  SlidersHorizontal, Sparkles, RefreshCw, Layers
} from 'lucide-react'

// Quick sample IDs for one-click testing
const SAMPLE_IDS = ['CUST00001', 'CUST00002', 'CUST00003', 'CUST01033', 'CUST02039']

function RiskBadge({ level }) {
  const cls = level === 'HIGH' ? 'badge-high' : level === 'MEDIUM' ? 'badge-medium' : 'badge-low'
  return <span className={cls}>{level}</span>
}

function OutcomeBadge({ outcome }) {
  const isChurned = outcome === 'Churned'
  const style = {
    fontSize: 11,
    fontWeight: 600,
    padding: '3px 9px',
    borderRadius: 20,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    background: isChurned ? 'rgba(229,62,62,0.12)' : 'rgba(56,161,105,0.12)',
    color: isChurned ? 'var(--red)' : 'var(--green)',
  }
  return (
    <span style={style}>
      {isChurned ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}
      {outcome}
    </span>
  )
}

function StatBox({ label, value, sub, highlight }) {
  return (
    <div style={{
      background: 'var(--bg2)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: '12px 14px',
      display: 'flex',
      flexDirection: 'column',
      gap: 3,
    }}>
      <span style={{ fontSize: 11, color: 'var(--text2)', fontWeight: 500 }}>{label}</span>
      <span style={{
        fontSize: 18,
        fontWeight: 700,
        color: highlight ? 'var(--red)' : 'var(--text)',
        fontFamily: 'var(--mono)'
      }}>
        {value}
      </span>
      {sub && <span style={{ fontSize: 10, color: 'var(--text3)' }}>{sub}</span>}
    </div>
  )
}

export default function CustomerSimilarity() {
  const [searchId, setSearchId] = useState('CUST00001')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [selectedCompare, setSelectedCompare] = useState(null)

  const fetchSimilarity = async (cid) => {
    const targetId = (cid || searchId).trim().toUpperCase()
    if (!targetId) return

    setLoading(true)
    setError(null)
    try {
      const res = await api.getCustomerSimilarity({ customer_id: targetId, n_neighbors: 5 })
      if (res?.error) {
        setError(res.error)
        setData(null)
      } else if (res?.similar_customers) {
        setData(res)
        // Default compare customer to the closest neighbor
        setSelectedCompare(res.similar_customers[0] || null)
      } else {
        setError('Unexpected response from similarity service.')
      }
    } catch (e) {
      setError(e.message || 'Error connecting to backend')
    } finally {
      setLoading(false)
    }
  }

  // Load initial customer on mount
  useEffect(() => {
    fetchSimilarity('CUST00001')
  }, [])

  const selected = data?.selected_customer
  const neighbors = data?.similar_customers || []
  const insights = data?.insights || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1200, margin: '0 auto' }}>
      
      {/* ── A. Page Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: 'var(--text)', color: 'var(--bg)',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <Users size={17} />
            </div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>
              Customer Similarity Finder
            </h1>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text2)', marginTop: 4 }}>
            Discover customers with similar behaviour and understand their historical outcomes using K-Nearest Neighbors (KNN).
          </p>
        </div>

        {/* Info Pill */}
        <div style={{
          background: 'var(--card)',
          border: '1px solid var(--border)',
          borderRadius: 20,
          padding: '6px 14px',
          fontSize: 12,
          color: 'var(--text2)',
          display: 'flex',
          alignItems: 'center',
          gap: 6
        }}>
          <Sparkles size={14} color="var(--yellow)" />
          <span>KNN Euclidean Distance • Standardized Feature Space</span>
        </div>
      </div>

      {/* ── B. Customer Selection & Search ── */}
      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 240 }}>
            <Search size={16} color="var(--text3)" style={{ position: 'absolute', left: 12, top: 12 }} />
            <input
              type="text"
              value={searchId}
              onChange={e => setSearchId(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && fetchSimilarity()}
              placeholder="Search by Customer ID (e.g. CUST00001)"
              className="inp"
              style={{ paddingLeft: 36, height: 40 }}
            />
          </div>
          <button
            onClick={() => fetchSimilarity()}
            disabled={loading}
            style={{
              background: 'var(--text)',
              color: 'var(--bg)',
              border: 'none',
              borderRadius: 8,
              padding: '0 20px',
              fontSize: 13,
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              height: 40,
              opacity: loading ? 0.7 : 1,
              transition: 'opacity 0.15s',
            }}
          >
            {loading ? (
              <RefreshCw size={15} style={{ animation: 'spin 1s linear infinite' }} />
            ) : (
              <Search size={15} />
            )}
            Find Similar Customers
          </button>
        </div>

        {/* Sample Customer Quick Pick */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingTop: 4 }}>
          <span style={{ fontSize: 11, color: 'var(--text3)', fontWeight: 500 }}>Example Customers:</span>
          {SAMPLE_IDS.map(id => (
            <button
              key={id}
              onClick={() => { setSearchId(id); fetchSimilarity(id); }}
              style={{
                background: searchId === id ? 'var(--text)' : 'var(--bg2)',
                color: searchId === id ? 'var(--bg)' : 'var(--text2)',
                border: '1px solid var(--border)',
                borderRadius: 14,
                padding: '3px 10px',
                fontSize: 11,
                cursor: 'pointer',
                fontFamily: 'var(--mono)',
                fontWeight: 600,
                transition: 'all 0.15s',
              }}
            >
              {id}
            </button>
          ))}
        </div>

        {error && (
          <div style={{
            background: 'rgba(229,62,62,0.1)',
            border: '1px solid var(--red)',
            borderRadius: 8,
            padding: '10px 14px',
            fontSize: 13,
            color: 'var(--red)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}
      </div>

      {selected && (
        <>
          {/* ── C. Selected Customer Profile ── */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--mono)' }}>
                    {selected.customer_id}
                  </span>
                  <span style={{
                    fontSize: 12,
                    fontWeight: 600,
                    background: 'var(--bg2)',
                    border: '1px solid var(--border)',
                    padding: '2px 8px',
                    borderRadius: 6,
                    color: 'var(--text)'
                  }}>
                    {selected.plan_type} Plan
                  </span>
                  <RiskBadge level={selected.risk_level} />
                  <OutcomeBadge outcome={selected.historical_outcome} />
                </div>
                <p style={{ fontSize: 12, color: 'var(--text2)', marginTop: 3 }}>
                  Target Customer • {selected.device_type} • {selected.preferred_genre} • {selected.payment_method}
                </p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--text3)' }}>XGBoost Churn Risk</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: selected.risk_level === 'HIGH' ? 'var(--red)' : selected.risk_level === 'MEDIUM' ? 'var(--yellow)' : 'var(--green)' }}>
                    {selected.churn_percent}
                  </div>
                </div>
              </div>
            </div>

            {/* Profile Metrics Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10 }}>
              <StatBox label="Subscription Plan" value={selected.plan_type} sub={`₹${selected.monthly_charge}/mo`} />
              <StatBox label="Tenure" value={`${selected.tenure_months} mo`} sub="Customer Lifetime" />
              <StatBox label="Monthly Charge" value={`₹${selected.monthly_charge}`} sub="Billed monthly" />
              <StatBox label="Weekly Watch Hours" value={`${selected.watch_hours_per_week}h`} sub="Hours per week" />
              <StatBox label="30-Day Logins" value={selected.logins_last_30_days} sub="Activity frequency" />
              <StatBox label="Payment Failures" value={selected.payment_failures_3m} sub="Last 3 months" highlight={selected.payment_failures_3m > 0} />
              <StatBox label="Support Tickets" value={selected.support_tickets} sub="Total tickets" highlight={selected.support_tickets > 1} />
            </div>
          </div>

          {/* ── D. Similar Customer Results ── */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Layers size={17} />
                  Top 5 Nearest Historical Lookalikes
                </h2>
                <p style={{ fontSize: 12, color: 'var(--text2)', marginTop: 2 }}>
                  Selected customer excluded. Ranked by Euclidean similarity in standardized behavioral space.
                </p>
              </div>
              <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--mono)' }}>
                Returned {neighbors.length} neighbours
              </span>
            </div>

            {/* Results Table */}
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text2)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    <th style={{ padding: '10px 12px' }}>Customer ID</th>
                    <th style={{ padding: '10px 12px' }}>Similarity Score</th>
                    <th style={{ padding: '10px 12px' }}>Churn Risk</th>
                    <th style={{ padding: '10px 12px' }}>Historical Outcome</th>
                    <th style={{ padding: '10px 12px' }}>Tenure</th>
                    <th style={{ padding: '10px 12px' }}>Plan & Charge</th>
                    <th style={{ padding: '10px 12px' }}>Watch Hrs / Logins</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Compare</th>
                  </tr>
                </thead>
                <tbody>
                  {neighbors.map((cust, idx) => {
                    const isComparing = selectedCompare?.customer_id === cust.customer_id
                    return (
                      <tr
                        key={cust.customer_id}
                        style={{
                          borderBottom: '1px solid var(--border)',
                          background: isComparing ? 'var(--bg2)' : 'transparent',
                          transition: 'background 0.15s',
                        }}
                      >
                        {/* ID & Name */}
                        <td style={{ padding: '12px' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--mono)' }}>
                            {cust.customer_id}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--text3)' }}>
                            Rank #{idx + 1} • {cust.device_type}
                          </div>
                        </td>

                        {/* Similarity Score with visual bar */}
                        <td style={{ padding: '12px', minWidth: 140 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 13 }}>
                              {cust.similarity_score}%
                            </span>
                            <div style={{
                              flex: 1,
                              height: 6,
                              background: 'var(--border)',
                              borderRadius: 3,
                              overflow: 'hidden'
                            }}>
                              <div style={{
                                width: `${Math.min(100, cust.similarity_score)}%`,
                                height: '100%',
                                background: 'var(--blue)',
                                borderRadius: 3,
                              }} />
                            </div>
                          </div>
                          <span style={{ fontSize: 10, color: 'var(--text3)' }}>
                            dist: {cust.distance}
                          </span>
                        </td>

                        {/* Churn Risk */}
                        <td style={{ padding: '12px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ fontWeight: 600, fontFamily: 'var(--mono)' }}>{cust.churn_percent}</span>
                            <RiskBadge level={cust.risk_level} />
                          </div>
                        </td>

                        {/* Historical Ground-truth Outcome */}
                        <td style={{ padding: '12px' }}>
                          <OutcomeBadge outcome={cust.historical_outcome} />
                        </td>

                        {/* Tenure */}
                        <td style={{ padding: '12px', fontFamily: 'var(--mono)' }}>
                          {cust.tenure_months} mo
                        </td>

                        {/* Plan & Monthly Charge */}
                        <td style={{ padding: '12px' }}>
                          <div style={{ fontWeight: 500, color: 'var(--text)' }}>{cust.plan_type}</div>
                          <div style={{ fontSize: 11, color: 'var(--text3)' }}>₹{cust.monthly_charge}/mo</div>
                        </td>

                        {/* Behavior */}
                        <td style={{ padding: '12px' }}>
                          <div style={{ fontSize: 12, color: 'var(--text)' }}>{cust.watch_hours_per_week} hrs/wk</div>
                          <div style={{ fontSize: 11, color: 'var(--text3)' }}>{cust.logins_last_30_days} logins / mo</div>
                        </td>

                        {/* Compare Action */}
                        <td style={{ padding: '12px', textAlign: 'right' }}>
                          <button
                            onClick={() => setSelectedCompare(cust)}
                            style={{
                              background: isComparing ? 'var(--text)' : 'var(--bg2)',
                              color: isComparing ? 'var(--bg)' : 'var(--text2)',
                              border: '1px solid var(--border)',
                              borderRadius: 6,
                              padding: '5px 10px',
                              fontSize: 11,
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 4,
                              transition: 'all 0.15s',
                            }}
                          >
                            <GitCompare size={12} />
                            {isComparing ? 'Comparing' : 'Compare'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── E. Head-to-Head Comparison Section ── */}
          {selectedCompare && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
                <div>
                  <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <GitCompare size={17} />
                    Side-by-Side Customer Comparison
                  </h3>
                  <p style={{ fontSize: 12, color: 'var(--text2)', marginTop: 2 }}>
                    Comparing selected customer <strong style={{ color: 'var(--text)' }}>{selected.customer_id}</strong> with lookalike <strong style={{ color: 'var(--text)' }}>{selectedCompare.customer_id}</strong> ({selectedCompare.similarity_score}% similarity).
                  </p>
                </div>
                <OutcomeBadge outcome={selectedCompare.historical_outcome} />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
                
                {/* Metric 1: Viewing Hours */}
                <ComparisonMetric
                  label="Viewing Hours per Week"
                  icon={PlayCircle}
                  valA={`${selected.watch_hours_per_week} hrs`}
                  valB={`${selectedCompare.watch_hours_per_week} hrs`}
                  delta={`${(selectedCompare.watch_hours_per_week - selected.watch_hours_per_week).toFixed(1)} hrs`}
                  isPositive={selectedCompare.watch_hours_per_week >= selected.watch_hours_per_week}
                />

                {/* Metric 2: Login Frequency */}
                <ComparisonMetric
                  label="Logins in Last 30 Days"
                  icon={Clock}
                  valA={`${selected.logins_last_30_days} logins`}
                  valB={`${selectedCompare.logins_last_30_days} logins`}
                  delta={`${selectedCompare.logins_last_30_days - selected.logins_last_30_days} logins`}
                  isPositive={selectedCompare.logins_last_30_days >= selected.logins_last_30_days}
                />

                {/* Metric 3: Payment Failures */}
                <ComparisonMetric
                  label="Payment Failures (3m)"
                  icon={AlertTriangle}
                  valA={`${selected.payment_failures_3m}`}
                  valB={`${selectedCompare.payment_failures_3m}`}
                  delta={`${selectedCompare.payment_failures_3m - selected.payment_failures_3m}`}
                  isPositive={selectedCompare.payment_failures_3m <= selected.payment_failures_3m}
                />

                {/* Metric 4: Support Tickets */}
                <ComparisonMetric
                  label="Support Tickets"
                  icon={ShieldAlert}
                  valA={`${selected.support_tickets}`}
                  valB={`${selectedCompare.support_tickets}`}
                  delta={`${selectedCompare.support_tickets - selected.support_tickets}`}
                  isPositive={selectedCompare.support_tickets <= selected.support_tickets}
                />

                {/* Metric 5: Tenure */}
                <ComparisonMetric
                  label="Tenure"
                  icon={SlidersHorizontal}
                  valA={`${selected.tenure_months} months`}
                  valB={`${selectedCompare.tenure_months} months`}
                  delta={`${selectedCompare.tenure_months - selected.tenure_months} mo`}
                  isPositive={selectedCompare.tenure_months >= selected.tenure_months}
                />

                {/* Metric 6: Monthly Charges */}
                <ComparisonMetric
                  label="Monthly Charges"
                  icon={Layers}
                  valA={`₹${selected.monthly_charge}`}
                  valB={`₹${selectedCompare.monthly_charge}`}
                  delta={`₹${selectedCompare.monthly_charge - selected.monthly_charge}`}
                  isPositive={selectedCompare.monthly_charge <= selected.monthly_charge}
                />
              </div>
            </div>
          )}

          {/* ── F. Factual Insights Section ── */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Sparkles size={17} color="var(--yellow)" />
                Data-Driven Lookalike Insights
              </h3>
              <p style={{ fontSize: 12, color: 'var(--text2)', marginTop: 2 }}>
                Factual observations synthesized directly from the top 5 nearest historical records.
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
              {insights.map((insight, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'var(--bg2)',
                    border: '1px solid var(--border)',
                    borderRadius: 10,
                    padding: '14px 16px',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                  }}
                >
                  <div style={{
                    width: 22, height: 22, borderRadius: '50%',
                    background: 'var(--card)', border: '1px solid var(--border)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0, fontSize: 11, fontWeight: 700, color: 'var(--text)'
                  }}>
                    {idx + 1}
                  </div>
                  <p style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.5, margin: 0 }}>
                    {insight}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function ComparisonMetric({ label, icon: Icon, valA, valB, delta, isPositive }) {
  return (
    <div style={{
      background: 'var(--bg2)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: '12px 14px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text2)', fontSize: 12, fontWeight: 500 }}>
        <Icon size={14} />
        <span>{label}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text3)' }}>Target</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--mono)' }}>{valA}</div>
        </div>

        <ArrowRight size={14} color="var(--text3)" />

        <div>
          <div style={{ fontSize: 10, color: 'var(--text3)' }}>Lookalike</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--mono)' }}>{valB}</div>
        </div>

        <div style={{
          fontSize: 11,
          fontWeight: 600,
          padding: '2px 8px',
          borderRadius: 6,
          background: isPositive ? 'rgba(56,161,105,0.12)' : 'rgba(229,62,62,0.12)',
          color: isPositive ? 'var(--green)' : 'var(--red)',
          fontFamily: 'var(--mono)',
        }}>
          {delta.startsWith('-') || delta.startsWith('+') ? delta : `+${delta}`}
        </div>
      </div>
    </div>
  )
}
