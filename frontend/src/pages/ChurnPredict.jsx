import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, CUSTOMER_ID_RE, WHATIF_BOUNDS, validateWhatIfField } from '../api/churniq'
import { ErrorState, Loading, RiskBadge, riskColor } from '../components/Status'
import { TrendingUp, Search, ArrowRight } from 'lucide-react'

// CHURN-31: "Churn Predict" is a What-If simulator on a real customer.
// The backend has no endpoint that scores a hypothetical customer from scratch:
// POST /whatif takes an existing customer and overrides up to six behaviour
// fields. So the user loads a customer, edits those fields (validated with the
// backend's own bounds) and sees the model's before/after result. There is no
// offline estimate: if the API fails, the page says so.

const FIELDS = Object.keys(WHATIF_BOUNDS)
const SAMPLE_IDS = ['CUST00001', 'CUST01033', 'CUST02261', 'CUST00936']

const GUIDANCE = {
  HIGH:   ['Contact the customer directly with a retention offer', 'Resolve any payment-method issues', 'Recommend content matched to their viewing'],
  MEDIUM: ['Send curated content recommendations', 'Consider a loyalty discount', 'Trigger a re-engagement notification'],
  LOW:    ['Continue standard engagement', 'Review again if behaviour changes'],
}

function Field({ field, value, error, onChange }) {
  const b = WHATIF_BOUNDS[field]
  const id = `wi-${field}`
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label htmlFor={id} style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>
        {b.label} <span style={{ fontSize: 11, color: 'var(--text3)', fontWeight: 400 }}>— {b.min} to {b.max}</span>
      </label>
      <input id={id} type="number" inputMode="decimal" className="inp"
        min={b.min} max={b.max} step={b.step} value={value}
        aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined}
        onChange={e => onChange(field, e.target.value)}
        style={error ? { borderColor: 'var(--red)' } : undefined} />
      {error && <span id={`${id}-err`} role="alert" style={{ fontSize: 11, color: 'var(--red)' }}>{error}</span>}
    </div>
  )
}

export default function ChurnPredict() {
  const [params] = useSearchParams()
  const [idInput, setIdInput]     = useState(params.get('customer') || '')
  const [idError, setIdError]     = useState(null)
  const [customer, setCustomer]   = useState(null)
  const [loadState, setLoadState] = useState({ loading: false, error: null })
  const [form, setForm]           = useState({})
  const [errors, setErrors]       = useState({})
  const [result, setResult]       = useState(null)
  const [submit, setSubmit]       = useState({ loading: false, error: null })

  const loadCustomer = async (raw) => {
    const id = String(raw ?? idInput).trim().toUpperCase()
    setIdInput(id)
    if (!CUSTOMER_ID_RE.test(id)) {
      setIdError('Enter a customer ID: 1–32 letters, digits, "_" or "-" (e.g. CUST00001).')
      return
    }
    setIdError(null)
    setResult(null)
    setSubmit({ loading: false, error: null })
    setCustomer(null)
    setLoadState({ loading: true, error: null })
    const { data, error } = await api.getCustomer(id)
    setLoadState({ loading: false, error })
    if (data) {
      setCustomer(data)
      setForm(Object.fromEntries(FIELDS.map(f => [f, String(data[f])])))
      setErrors({})
    }
  }

  const onChange = (field, v) => {
    setForm(f => ({ ...f, [field]: v }))
    setErrors(e => ({ ...e, [field]: validateWhatIfField(field, v) }))
    setResult(null)
  }

  const predict = async () => {
    const errs = Object.fromEntries(FIELDS.map(f => [f, validateWhatIfField(f, form[f])]))
    setErrors(errs)
    if (Object.values(errs).some(Boolean)) return
    setSubmit({ loading: true, error: null })
    setResult(null)
    const body = { customer_id: customer.customer_id, ...Object.fromEntries(FIELDS.map(f => [f, Number(form[f])])) }
    const { data, error } = await api.whatIf(body)
    setSubmit({ loading: false, error })
    setResult(data)
  }

  const changed = customer ? FIELDS.filter(f => Number(form[f]) !== Number(customer[f])) : []
  const reasons = customer ? [customer.top_reason_1, customer.top_reason_2, customer.top_reason_3].filter(Boolean) : []
  const scored = customer?.churn_prob != null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>Churn Predict — What-If</h2>
        <p style={{ fontSize: 13, color: 'var(--text2)', marginTop: 3 }}>
          Load a customer, change their behaviour, and see how the XGBoost model's churn prediction responds.
        </p>
      </div>

      {/* Step 1: choose a customer */}
      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <form onSubmit={e => { e.preventDefault(); loadCustomer() }} style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: '1 1 220px', minWidth: 0 }}>
            <label htmlFor="predict-customer" className="sr-only">Customer ID</label>
            <Search size={14} aria-hidden="true" style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--text3)' }} />
            <input id="predict-customer" className="inp" value={idInput} placeholder="Customer ID (e.g. CUST00001)"
              onChange={e => setIdInput(e.target.value.toUpperCase())}
              aria-invalid={!!idError} aria-describedby={idError ? 'predict-customer-err' : undefined}
              style={{ paddingLeft: 32, height: 38 }} />
          </div>
          <button type="submit" className="btn-primary" disabled={loadState.loading} style={{ height: 38 }}>
            Load customer
          </button>
        </form>
        {idError && <p id="predict-customer-err" role="alert" style={{ fontSize: 12, color: 'var(--red)' }}>{idError}</p>}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--text3)' }}>Examples:</span>
          {SAMPLE_IDS.map(id => (
            <button key={id} type="button" className="btn-secondary" style={{ padding: '3px 9px', fontSize: 11, fontFamily: 'var(--mono)' }}
              onClick={() => loadCustomer(id)}>{id}</button>
          ))}
        </div>
      </div>

      {loadState.loading && <Loading label="Loading customer…" />}
      {loadState.error && (
        <ErrorState error={loadState.error}
          title={loadState.error.status === 404 ? 'Customer not found' : 'Customer could not be loaded'}
          onRetry={loadState.error.kind === 'http' && loadState.error.status < 500 ? undefined : () => loadCustomer()} />
      )}

      {!customer && !loadState.loading && !loadState.error && (
        <div className="card" style={{ textAlign: 'center', padding: '40px 24px' }}>
          <TrendingUp size={36} style={{ color: 'var(--border)', margin: '0 auto 14px' }} aria-hidden="true" />
          <p style={{ fontWeight: 600, color: 'var(--text2)', fontSize: 14 }}>Choose a customer to start</p>
        </div>
      )}

      {customer && (
        <div className="grid-2">
          {/* Step 2: edit the six supported fields */}
          <div className="card fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
              <div>
                <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{customer.name}</p>
                <p style={{ fontSize: 11, color: 'var(--text2)', fontFamily: 'var(--mono)' }}>
                  <Link to={`/risk/${customer.customer_id}`} style={{ color: 'inherit' }}>{customer.customer_id}</Link>
                  {' · '}{customer.plan_type} · {customer.device_type}
                </p>
              </div>
              <div style={{ textAlign: 'right' }}>
                <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase' }}>Current prediction</p>
                <p style={{ fontSize: 18, fontWeight: 700, color: riskColor(customer.risk_level) }}>{customer.churn_percent}</p>
              </div>
            </div>
            <p className="note" style={{ marginTop: 0 }}>
              Only these six fields can be changed; plan type, device and every other model feature stay as recorded for this customer.
            </p>
            <form onSubmit={e => { e.preventDefault(); predict() }} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {FIELDS.map(f => <Field key={f} field={f} value={form[f] ?? ''} error={errors[f]} onChange={onChange} />)}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="submit" className="btn-primary" disabled={submit.loading || !scored} style={{ flex: 1, padding: 11 }}>
                  {submit.loading
                    ? <div className="spinner" style={{ width: 14, height: 14, borderTopColor: 'var(--bg)' }} />
                    : <><TrendingUp size={15} aria-hidden="true" /> Predict Churn</>}
                </button>
                <button type="button" className="btn-secondary" disabled={changed.length === 0}
                  onClick={() => { setForm(Object.fromEntries(FIELDS.map(f => [f, String(customer[f])]))); setErrors({}); setResult(null) }}>
                  Reset
                </button>
              </div>
              {!scored && <p className="note">This customer is not scored by the model, so What-If is unavailable.</p>}
            </form>
          </div>

          {/* Step 3: result */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
            {submit.error && <ErrorState error={submit.error} title="Prediction failed" onRetry={predict} />}

            {result ? (
              <div className="card fade-in" data-testid="predict-result" aria-live="polite" style={{ borderLeft: `3px solid ${riskColor(result.new_risk)}` }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase' }}>Before</p>
                    <p style={{ fontSize: 22, fontWeight: 700, color: riskColor(result.original_risk) }}>{(result.original_churn_prob * 100).toFixed(1)}%</p>
                    <RiskBadge level={result.original_risk} />
                  </div>
                  <ArrowRight size={18} style={{ color: 'var(--text3)' }} aria-hidden="true" />
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase' }}>After</p>
                    <p style={{ fontSize: 22, fontWeight: 700, color: riskColor(result.new_risk) }}>{(result.new_churn_prob * 100).toFixed(1)}%</p>
                    <RiskBadge level={result.new_risk} />
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ fontSize: 10, color: 'var(--text2)', textTransform: 'uppercase' }}>Change</p>
                    <p style={{ fontSize: 18, fontWeight: 700, color: result.change < 0 ? 'var(--green)' : result.change > 0 ? 'var(--red)' : 'var(--text2)' }}>
                      {result.change_percent}
                    </p>
                  </div>
                </div>
                <p className="note">
                  {changed.length === 0
                    ? 'No fields changed — this is the customer\'s current prediction.'
                    : `Changed: ${changed.map(f => WHATIF_BOUNDS[f].label).join(', ')}.`}
                </p>
                <div style={{ marginTop: 12 }}>
                  <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>Suggested next steps ({result.new_risk} risk)</p>
                  <ul style={{ listStyle: 'none' }}>
                    {(GUIDANCE[result.new_risk] || []).map((s, i) => (
                      <li key={i} style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 4 }}>→ {s}</li>
                    ))}
                  </ul>
                  <p className="note">General guidance by risk tier, not model output.</p>
                </div>
              </div>
            ) : !submit.error && (
              <div className="card" style={{ padding: '32px 24px', textAlign: 'center' }}>
                <p style={{ fontSize: 13, color: 'var(--text2)' }}>Change one or more fields and click <strong>Predict Churn</strong>.</p>
              </div>
            )}

            {/* The customer's real SHAP explanation (current behaviour) */}
            <div className="card">
              <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', marginBottom: 10 }}>Current top churn reasons (SHAP)</p>
              {reasons.length === 0 ? <p className="note">No SHAP explanation available.</p> : (
                <ol style={{ paddingLeft: 18 }}>
                  {reasons.map((r, i) => <li key={i} style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 4 }}>{r}</li>)}
                </ol>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
