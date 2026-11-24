import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api, getEmailToken, setEmailToken, clearEmailToken } from '../api/churniq'
import { useApi } from '../hooks/useApi'
import { Loading, ErrorState, RiskBadge, riskColor } from '../components/Status'
import { ArrowLeft, Mail, Copy, Send, AlertTriangle, CheckCircle, Sliders, Users, Info } from 'lucide-react'

function Gauge({ pct, level }) {
  // pct === null → customer not scored by the model (no out-of-sample prediction)
  const r = 52, cx = 64, cy = 64
  const circ = 2 * Math.PI * r
  const dash = pct == null ? 0 : (pct / 100) * circ
  const color = riskColor(level)
  return (
    <svg width={128} height={128} viewBox="0 0 128 128" role="img"
      aria-label={pct == null ? 'Not scored' : `Churn risk ${pct}%`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border)" strokeWidth={10} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={10}
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeDashoffset={circ / 4}
        strokeLinecap="round"
        style={{ transition: 'stroke-dasharray 0.8s ease' }}
      />
      <text x={cx} y={cy - 4} textAnchor="middle" dominantBaseline="middle"
        style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font)', fill: color }}>
        {pct == null ? 'N/A' : `${pct}%`}
      </text>
      <text x={cx} y={cy + 18} textAnchor="middle"
        style={{ fontSize: 9, fontFamily: 'var(--font)', fill: 'var(--text2)' }}>
        {pct == null ? 'NOT SCORED' : 'CHURN RISK'}
      </text>
    </svg>
  )
}

function NotScoredNote({ what }) {
  return (
    <div style={{ marginTop: 14, padding: '8px 12px', borderRadius: 8, background: 'var(--bg2)', border: '1px dashed var(--border)', display: 'flex', gap: 6, alignItems: 'center' }}>
      <AlertTriangle size={13} style={{ color: 'var(--text2)', flexShrink: 0 }} aria-hidden="true" />
      <p style={{ fontSize: 11, color: 'var(--text2)' }}>
        {what} unavailable: this customer has no out-of-sample churn prediction (not scored by the model).
      </p>
    </div>
  )
}

function Slider({ id, label, value, min, max, step = 1, onChange, hint }) {
  // Never let the slider clamp the customer's real value: widen the range if needed.
  const hi = Math.max(max, value ?? max)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <label htmlFor={id} style={{ fontSize: 12, fontWeight: 500, color: 'var(--text2)' }}>{label}</label>
        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--mono)' }}>
          {value}{hint}
        </span>
      </div>
      <input id={id} type="range" min={min} max={hi} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--text)' }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text3)' }} aria-hidden="true">
        <span>{min}</span><span>{hi}</span>
      </div>
    </div>
  )
}

const SLIDERS = [
  // step 0.1: the data has one decimal place, so the slider must not round the customer's value (CHURN-52)
  { field: 'watch_hours_per_week', label: 'Watch Hours / Week',  min: 0.5, max: 40, step: 0.1, hint: ' hrs' },
  { field: 'logins_last_30_days',  label: 'Logins Last 30 Days', min: 0,   max: 30, hint: '' },
  { field: 'payment_failures_3m',  label: 'Payment Failures',    min: 0,   max: 4,  hint: '' },
  { field: 'support_tickets',      label: 'Support Tickets',     min: 0,   max: 5,  hint: '' },
  { field: 'tenure_months',        label: 'Tenure (months)',     min: 1,   max: 72, hint: ' mo' },
]

export default function CustomerDetail() {
  const { id } = useParams()
  const nav    = useNavigate()
  const { data: customer, error, loading, reload } = useApi((signal) => api.getCustomer(id, { signal }), [id])

  const back = (
    <button type="button" onClick={() => nav('/risk')}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text2)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, width: 'fit-content' }}>
      <ArrowLeft size={14} aria-hidden="true" /> Back to Risk Table
    </button>
  )

  if (loading) return <Loading label="Loading customer…" height={300} />

  if (error) {
    const notFound = error.kind === 'http' && error.status === 404
    const badId    = error.kind === 'http' && error.status === 422
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {back}
        <ErrorState
          error={error}
          title={notFound ? `Customer not found: ${id}` : badId ? `Invalid customer ID: ${id}` : 'Customer could not be loaded'}
          onRetry={notFound || badId ? undefined : reload}
        />
      </div>
    )
  }

  // Keyed by customer ID: What-If and email state can never carry over to another customer.
  return <CustomerView key={customer.customer_id} customer={customer} back={back} nav={nav} />
}

function CustomerView({ customer, back, nav }) {
  const id = customer.customer_id

  // What-if state
  const [sliders, setSliders]     = useState(() => Object.fromEntries(SLIDERS.map(s => [s.field, customer[s.field]])))
  const [wiResult, setWiResult]   = useState(null)
  const [wiError, setWiError]     = useState(null)
  const [wiLoading, setWiLoading] = useState(false)

  // Email state
  const [emailData, setEmailData]       = useState(null)
  const [emailError, setEmailError]     = useState(null)
  const [emailLoading, setEmailLoading] = useState(false)
  const [sendLoading, setSendLoading]   = useState(false)
  const [sendResult, setSendResult]     = useState(null)
  const [copied, setCopied]             = useState(false)

  const runWhatIf = async () => {
    setWiLoading(true)
    setWiResult(null)
    setWiError(null)
    const { data, error } = await api.whatIf({ customer_id: id, ...sliders })
    setWiResult(data)
    setWiError(error)
    setWiLoading(false)
  }

  const generateEmail = async () => {
    setEmailLoading(true)
    setEmailData(null)
    setEmailError(null)
    setSendResult(null)
    const { data, error } = await api.getRetention(id)
    setEmailData(data)
    setEmailError(error)
    setEmailLoading(false)
  }

  // CHURN-44 flow, unchanged: token prompted once per tab, cleared on 401.
  const handleSend = async () => {
    if (!emailData) return
    setSendResult(null)
    let token = getEmailToken()
    if (!token) {
      token = (window.prompt('Enter the email API token (EMAIL_API_TOKEN) to send this email:') || '').trim()
      if (!token) {
        setSendResult({ error: 'An email API token is required to send emails.' })
        return
      }
      setEmailToken(token)
    }
    setSendLoading(true)
    const res = await api.sendEmail({
      customer_id: id,
      subject: emailData.subject,
      body: emailData.email,
    }, token)
    if (res?.status === 401) clearEmailToken()   // wrong token: ask again next time
    setSendResult(res)
    setSendLoading(false)
  }

  const handleCopy = async () => {
    if (!emailData) return
    try {
      await navigator.clipboard.writeText(`Subject: ${emailData.subject}\n\n${emailData.email}`)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setSendResult({ error: 'Copy failed: the browser blocked clipboard access.' })
    }
  }

  const scored = customer.churn_prob != null
  const pct    = scored ? Math.round(customer.churn_prob * 100) : null
  const wiPct  = wiResult ? Math.round(wiResult.new_churn_prob * 100) : null
  const wiBefore = wiResult ? Math.round(wiResult.original_churn_prob * 100) : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        {back}
        <button type="button" className="btn-secondary" onClick={() => nav(`/similarity?customer=${encodeURIComponent(id)}`)}
          style={{ fontSize: 12 }}>
          <Users size={14} aria-hidden="true" /> Find Similar Customers
        </button>
      </div>

      {/* Profile + Gauge — GET /customer/{id} */}
      <div className="grid-profile">
        <div className="card fade-in" style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4, flexWrap: 'wrap' }}>
                <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>{customer.name}</h2>
                <RiskBadge level={customer.risk_level} />
              </div>
              <p style={{ fontSize: 12, color: 'var(--text2)', fontFamily: 'var(--mono)' }}>{customer.customer_id}</p>
            </div>
            <dl style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
              {[
                { label: 'Plan',    value: customer.plan_type },
                { label: 'Charge',  value: `₹${customer.monthly_charge}/mo` },
                { label: 'Tenure',  value: customer.tenure_display || `${customer.tenure_months} months` },
                { label: 'Device',  value: customer.device_type },
                { label: 'CLV',     value: customer.clv_formatted || (customer.clv_score == null ? 'N/A' : `₹${Number(customer.clv_score).toLocaleString('en-US')}`) },
                { label: 'CLV Tier', value: customer.clv_segment },
              ].map(({ label, value }) => (
                <div key={label} style={{ textAlign: 'center' }}>
                  <dt style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>{label}</dt>
                  <dd data-testid={`profile-${label}`} style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{value ?? '—'}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
        <div className="card fade-in" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Gauge pct={pct} level={customer.risk_level} />
        </div>
      </div>

      {/* SHAP Reasons — GET /customer/{id} top_reason_1..3 */}
      <div className="card fade-in">
        <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 14 }}>Top Churn Reasons — SHAP Analysis</p>
        {[customer.top_reason_1, customer.top_reason_2, customer.top_reason_3].filter(Boolean).length === 0 ? (
          <p className="note">No SHAP explanation available for this customer.</p>
        ) : (
          <ol style={{ display: 'flex', flexDirection: 'column', gap: 10, listStyle: 'none' }}>
            {[customer.top_reason_1, customer.top_reason_2, customer.top_reason_3].filter(Boolean).map((r, i) => {
              const shap = r.match(/SHAP: ([+-]?[\d.]+)/)?.[1]
              const text = r.split('[')[0].trim()
              const pctBar = Math.min(100, (Math.abs(parseFloat(shap) || 0) / 3) * 100)
              const colors = ['var(--red)', 'var(--yellow)', 'var(--blue)']
              return (
                <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span aria-hidden="true" style={{
                    width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                    background: 'var(--bg2)', color: colors[i],
                    fontSize: 11, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>{i + 1}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p data-testid="shap-reason" style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500, marginBottom: 4 }}>{text}</p>
                    <div style={{ height: 4, borderRadius: 2, background: 'var(--bg2)', overflow: 'hidden' }} aria-hidden="true">
                      <div style={{ height: '100%', width: `${pctBar}%`, background: colors[i], borderRadius: 2, transition: 'width 0.8s ease' }} />
                    </div>
                  </div>
                  {shap && <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: colors[i], flexShrink: 0 }}>SHAP {shap}</span>}
                </li>
              )
            })}
          </ol>
        )}
      </div>

      {/* What-If + Email side by side (stacked on narrow screens) */}
      <div className="grid-2">

        {/* What-If Simulator — POST /whatif */}
        <div className="card fade-in" style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Sliders size={15} style={{ color: 'var(--text2)' }} aria-hidden="true" />
            <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>What-If Simulator</p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {SLIDERS.map(s => (
              <Slider key={s.field} id={`wi-${s.field}`} label={s.label} value={sliders[s.field] ?? s.min}
                min={s.min} max={s.max} step={s.step} hint={s.hint}
                onChange={v => setSliders(prev => ({ ...prev, [s.field]: v }))} />
            ))}
          </div>
          {!scored && <NotScoredNote what="What-if comparison" />}
          <button type="button" className="btn-primary" onClick={runWhatIf} disabled={wiLoading || !scored}
            style={{ marginTop: 16, width: '100%', padding: 10 }}>
            {wiLoading ? <div className="spinner" style={{ width: 14, height: 14, borderTopColor: 'var(--bg)' }} /> : 'Recalculate Churn'}
          </button>
          {wiError && <div style={{ marginTop: 12 }}><ErrorState compact error={wiError} title="What-If calculation failed" /></div>}
          {wiResult && (
            <div data-testid="whatif-result" aria-live="polite" style={{ marginTop: 14, padding: 14, borderRadius: 10, background: 'var(--bg2)', border: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <div style={{ textAlign: 'center' }}>
                  <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Before</p>
                  <p style={{ fontSize: 20, fontWeight: 700, color: riskColor(wiResult.original_risk) }}>{wiBefore}%</p>
                  <RiskBadge level={wiResult.original_risk} />
                </div>
                <span style={{ fontSize: 18, color: 'var(--text3)' }} aria-hidden="true">→</span>
                <div style={{ textAlign: 'center' }}>
                  <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>After</p>
                  <p style={{ fontSize: 20, fontWeight: 700, color: riskColor(wiResult.new_risk) }}>{wiPct}%</p>
                  <RiskBadge level={wiResult.new_risk} />
                </div>
                <div style={{ textAlign: 'center' }}>
                  <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Change</p>
                  <p style={{ fontSize: 16, fontWeight: 700, color: wiResult.improved ? 'var(--green)' : wiResult.change === 0 ? 'var(--text2)' : 'var(--red)' }}>
                    {wiResult.change_percent}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Retention Email — GET /retention/{id}; sending needs the operator's token */}
        <div className="card fade-in" style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Mail size={15} style={{ color: 'var(--text2)' }} aria-hidden="true" />
            <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>Retention Email</p>
          </div>

          {!emailData && !emailLoading && !emailError && (
            <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--text2)' }}>
              <Mail size={32} style={{ margin: '0 auto 12px', opacity: 0.3 }} aria-hidden="true" />
              <p style={{ fontSize: 13 }}>
                Drafts a retention email from this customer's SHAP churn reasons, using Gemini when the
                server has it configured and a rule-based template otherwise. Nothing is sent until you click Send.
              </p>
            </div>
          )}

          {emailLoading && <Loading height={120} label="Generating email…" />}
          {emailError && <div style={{ marginBottom: 12 }}><ErrorState compact error={emailError} title="Retention email could not be generated" /></div>}

          {emailData && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 10 }}>
              <div data-testid="retention-source" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text2)' }}>
                <Info size={12} aria-hidden="true" />
                {emailData.ai_generated
                  ? <span>AI-generated by {emailData.generated_by}</span>
                  : <span>Rule-based template{emailData.fallback_reason ? ` (AI unavailable: ${emailData.fallback_reason.replace(/_/g, ' ')})` : ''}</span>}
                {emailData.priority && <span style={{ marginLeft: 'auto' }}>Priority: {emailData.priority}</span>}
              </div>
              <div style={{ padding: 12, borderRadius: 8, background: 'var(--bg2)', border: '1px solid var(--border)' }}>
                <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Subject</p>
                <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{emailData.subject}</p>
              </div>
              <div style={{ padding: 12, borderRadius: 8, background: 'var(--bg2)', border: '1px solid var(--border)', maxHeight: 160, overflowY: 'auto' }}>
                <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Email Body</p>
                <p style={{ fontSize: 12, color: 'var(--text)', lineHeight: 1.6, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{emailData.email}</p>
              </div>
              {emailData.suggested_offer && (
                <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(56,161,105,0.08)', border: '1px solid rgba(56,161,105,0.2)' }}>
                  <p style={{ fontSize: 11, color: 'var(--green)' }}>Suggested offer: {emailData.suggested_offer}</p>
                </div>
              )}
              {emailData.actions?.length > 0 && (
                <div>
                  <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>Recommended Actions:</p>
                  <ul style={{ listStyle: 'none' }}>
                    {emailData.actions.map((a, i) => (
                      <li key={i} style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 3 }}>→ {a}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <button type="button" className="btn-secondary" onClick={handleCopy} style={{ flex: 1, fontSize: 12 }}>
                  <Copy size={12} aria-hidden="true" /> {copied ? 'Copied!' : 'Copy'}
                </button>
                <button type="button" className="btn-primary" onClick={handleSend} disabled={sendLoading} style={{ flex: 1, fontSize: 12 }}>
                  {sendLoading
                    ? <div className="spinner" style={{ width: 12, height: 12, borderTopColor: 'var(--bg)' }} />
                    : <><Send size={12} aria-hidden="true" /> Send Email</>}
                </button>
              </div>
              {sendResult?.success && (
                <div role="status" style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(56,161,105,0.1)', border: '1px solid rgba(56,161,105,0.2)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <CheckCircle size={14} style={{ color: 'var(--green)' }} aria-hidden="true" />
                  <p style={{ fontSize: 12, color: 'var(--green)' }}>Email sent to {sendResult.sent_to}!</p>
                </div>
              )}
              {sendResult?.error && (
                <div role="alert" style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(229,62,62,0.1)', border: '1px solid rgba(229,62,62,0.2)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <AlertTriangle size={14} style={{ color: 'var(--red)' }} aria-hidden="true" />
                  <p style={{ fontSize: 12, color: 'var(--red)' }}>{sendResult.error}</p>
                </div>
              )}
            </div>
          )}

          {!scored && <NotScoredNote what="Retention email" />}
          <button type="button" onClick={generateEmail} disabled={emailLoading || !scored}
            className={emailData ? 'btn-secondary' : 'btn-primary'}
            style={{ marginTop: emailData ? 0 : 16, width: '100%', padding: 10 }}>
            <Mail size={14} aria-hidden="true" />
            {emailData ? 'Regenerate Email' : 'Generate Retention Email'}
          </button>
        </div>
      </div>
    </div>
  )
}
