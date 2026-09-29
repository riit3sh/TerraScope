import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowLeft, ChevronRight, FileText, FlaskConical, History, IndianRupee, Printer, Sparkles, TriangleAlert, X } from 'lucide-react'
import { evaluateParcel, EvaluationSettings, ParcelRecord, PropertyDetails, Valuation } from '../lib/api'

type EvidenceTab = 'Satellite' | 'Infrastructure' | 'RERA' | 'Uploaded Documents' | 'Derived Scores'

function Bar({ label, value, color }: { label: string; value: number | null; color: string }) {
  const available = typeof value === 'number'
  return <div className="score-line"><div><span>{label}</span><strong>{available ? value : '—'}</strong></div><div className="bar"><i style={{ width: available ? `${Math.max(0, Math.min(100, value))}%` : '0%', background: color }} /></div></div>
}

function EvidenceRow({ title, refName, freshness, summary, observedAt }: { title: string; refName: string; freshness: string; summary: string; observedAt?: string | null }) {
  return <div className="evidence-row"><div className="evidence-icon"><FileText size={16} /></div><div><strong>{title}</strong><p>{summary}</p><small>{refName} · {(observedAt || '').slice(0, 10) || 'date unavailable'}</small></div><span className={`freshness ${freshness}`}>{freshness.replace('_', ' ')}</span></div>
}


const inr = (value: number) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(Math.round(value))
function compactInr(value: number) {
  // Indian scale: beyond a lakh crore, "13,684 Cr" stops being readable.
  if (value >= 1e12) return `₹${(value / 1e12).toFixed(2)} Lakh Cr`
  if (value >= 1e7) return `₹${(value / 1e7).toFixed(2)} Cr`
  if (value >= 1e5) return `₹${(value / 1e5).toFixed(2)} L`
  return `₹${inr(value)}`
}

const unavailableCopy: Record<string, string> = {
  model_not_trained: 'No valuation model has been trained yet. Import a land-price CSV and run the training pipeline (see valuation/README.md).',
  location_not_covered: 'This parcel sits outside the area the price dataset covers.',
  land_use_not_covered: 'The price dataset holds no comparable sales for this land use.',
  synthetic_model_only: 'No real market price data has been loaded yet. The only trained model uses synthetic demo rows, so no price is quoted.',
  request_failed: 'The valuation service could not be reached.',
  valuation_error: 'The valuation model could not be evaluated.',
}

function ValuationSection({ valuation, property }: { valuation: Valuation | null; property: PropertyDetails | null }) {
  if (!valuation) {
    return <section className="valuation-section unavailable"><div className="section-label"><IndianRupee size={13} /> MARKET VALUATION</div><h2>Not requested</h2><p className="muted">No valuation was run for this parcel. It needs a location and a plot area.</p></section>
  }
  if (valuation.status === 'unavailable') {
    return <section className="valuation-section unavailable"><div className="section-label"><IndianRupee size={13} /> MARKET VALUATION</div><h2>Unavailable for this parcel</h2><p className="valuation-reason">{unavailableCopy[valuation.reason] || 'A valuation could not be produced.'}</p><p className="muted valuation-detail">{valuation.detail}</p><p className="muted">No estimate is shown rather than a guess.</p></section>
  }
  const coverage = valuation.evidence_coverage
  return <section className={`valuation-section${valuation.is_synthetic ? ' synthetic' : ''}`}>
    {valuation.is_synthetic && <div className="demo-banner"><TriangleAlert size={15} /> <strong>DEMO DATA.</strong> This model is trained on a synthetic fixture, not real market prices. Do not use these figures for a real decision.</div>}
    <div className="section-head"><div><div className="section-label"><IndianRupee size={13} /> MARKET VALUATION</div><h2>What the land is worth</h2></div><span className="valuation-stamp">{valuation.model_version} · valued {valuation.valuation_date}</span></div>
    <div className="valuation-grid">
      <div className="valuation-primary"><span>ESTIMATED PRICE</span><strong>₹{inr(valuation.estimated_inr_per_sqft)}</strong><small>per sq ft</small></div>
      <div className="valuation-primary total"><span>TOTAL LAND VALUE</span><strong>{compactInr(valuation.estimated_total_inr)}</strong><small>{inr(valuation.area_sqft)} sq ft · {valuation.land_use.replace('_', ' ')}{property?.area_sqft_override ? ' · area you entered' : ' · area from your boundary'}</small></div>
      <div className="valuation-range">{valuation.range
        ? <><span>LIKELY RANGE</span><strong>{compactInr(valuation.range.low_total_inr)} – {compactInr(valuation.range.high_total_inr)}</strong><small>{valuation.range.basis}</small></>
        : <><span>LIKELY RANGE</span><strong className="muted-strong">Not shown</strong><small>{valuation.range_unavailable_reason}</small></>}</div>
    </div>
    <div className="valuation-facts">
      <div><span>HELD-OUT ERROR</span><strong>±₹{inr(valuation.accuracy.model_mae_inr_per_sqft)}/sq ft</strong><small>MAE · RMSE ₹{inr(valuation.accuracy.model_rmse_inr_per_sqft)} · {valuation.accuracy.holdout_strategy} holdout</small></div>
      <div><span>VS SIMPLE BASELINE</span><strong>{valuation.accuracy.model_beats_baseline ? 'Model wins' : 'Baseline wins'}</strong><small>district median MAE ₹{inr(valuation.accuracy.baseline_mae_inr_per_sqft)}/sq ft</small></div>
      <div><span>DATA BEHIND IT</span><strong>{coverage.observations_within_radius} sales within {coverage.radius_km} km</strong><small>{coverage.dataset_rows} rows total · {coverage.dataset_date_from} to {coverage.dataset_date_to}</small></div>
      <div><span>NEAREST OBSERVATION</span><strong>{coverage.nearest_observation_km == null ? '—' : `${coverage.nearest_observation_km} km`}</strong><small>{coverage.districts_nearby.length ? coverage.districts_nearby.join(', ') : 'no districts nearby'}</small></div>
    </div>
    <p className="valuation-foot">Market value is computed from comparable land prices and the property details you entered. It does not use your suitability weights, so changing a priority slider cannot move it.</p>
  </section>
}

export function Report({ initialSnapshot, initialSettings, valuation, property, onBack }: { initialSnapshot: ParcelRecord; initialSettings: EvaluationSettings; valuation: Valuation | null; property: PropertyDetails | null; onBack: () => void }) {
  const [record, setRecord] = useState(initialSnapshot)
  const [settings, setSettings] = useState(initialSettings)
  const [scenario, setScenario] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<{ profile: string; changed: string; verdict: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [activeEvidenceTab, setActiveEvidenceTab] = useState<EvidenceTab>('Satellite')
  const [citationsOpen, setCitationsOpen] = useState(false)
  const [scenarioError, setScenarioError] = useState('')

  const chart = useMemo(() => {
    const ndvi = record.satellite?.ndvi_trend || []
    const ndbi = record.satellite?.ndbi_trend || []
    return ndvi.map((point, index) => ({ date: point.date?.slice(0, 7) || '—', ndvi: point.value, ndbi: ndbi[index]?.value ?? null })).filter(point => point.ndvi !== null || point.ndbi !== null)
  }, [record])
  // score_breakdown is what the evaluation actually computed; the risk block is a
  // partial mirror of it and leaves accessibility unset, which showed "—" next to
  // a live accessibility contribution.
  const breakdown = record.score_breakdown
  const legal = breakdown?.legal_safety_score ?? (record.risk?.legal_risk_score == null ? null : Math.max(0, 100 - record.risk.legal_risk_score))
  const accessibility = breakdown?.accessibility_score ?? record.risk?.accessibility_score ?? null
  const flood = breakdown?.flood_safety_score ?? (record.risk?.flood_risk_score == null ? null : Math.max(0, 100 - record.risk.flood_risk_score))
  const growth = breakdown?.growth_score ?? record.opportunity?.growth_score ?? null
  const verdict = record.verdict?.recommendation || 'UNAVAILABLE'
  const confidence = record.verdict?.confidence == null ? null : Math.round(record.verdict.confidence * 100)
  const contributions = record.score_breakdown?.weighted_contributions || []
  const evidence = record.evidence || []
  const satelliteIsDemo = evidence.some(item => (item.source_type || '') === 'satellite' && /synthetic/i.test(`${item.source_reference || ''} ${item.title || ''}`))
  const tabMatch: Record<EvidenceTab, string[]> = { Satellite: ['satellite'], Infrastructure: ['openstreetmap', 'infrastructure', 'open_elevation', 'elevation'], RERA: ['maharera_seed', 'rera'], 'Uploaded Documents': ['document', 'user_upload'], 'Derived Scores': ['derived'] }
  const visibleEvidence = evidence.filter(item => tabMatch[activeEvidenceTab].some(type => (item.source_type || '').toLowerCase().includes(type)))

  async function rerun(next: EvaluationSettings) {
    setSettings(next)
    setBusy(true)
    setScenarioError('')
    try {
      const result = await evaluateParcel(record.parcel_id || '', next, record.metadata.analysis_snapshot_id || '')
      setRecord(result)
      setHistory(items => [{ profile: next.profile, changed: `Flood Safety ${next.weights.flood_safety_pct}%`, verdict: result.verdict?.recommendation || 'UNAVAILABLE' }, ...items])
      setScenario(false)
    } catch (error) {
      setScenarioError(error instanceof Error ? error.message : 'Scenario evaluation failed.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="report-shell">
    <header className="report-topbar"><button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Workspace</button><div className="wordmark"><span className="mark"><Sparkles size={14} /></span> TERRASCOPE</div><div className="report-tools"><button className="quiet-button" onClick={() => setHistoryOpen(true)}><History size={15} /> Scenario history</button><button className="quiet-button" onClick={() => setScenario(true)}><FlaskConical size={15} /> Explore scenarios</button><button className="quiet-button" onClick={() => window.print()}><Printer size={15} /> Print</button></div></header>
    <div className="report-content">
      <section className="report-heading"><div><div className="eyebrow"><span className="pulse" /> ANALYSIS SNAPSHOT · {(record.metadata.analysis_snapshot_id || '—').slice(0, 8)}</div><h1>{record.location?.address || 'Location unavailable'}</h1><p>{record.geometry_metadata?.area_acres == null ? 'Area unavailable' : `${record.geometry_metadata.area_acres.toFixed(2)} acres`} <span>·</span> {record.metadata.analysis_date_from || '—'} — {record.metadata.analysis_date_to || '—'}</p></div><div className={`verdict-badge ${verdict.toLowerCase()}`}><span>RECOMMENDATION</span><strong>{verdict}</strong><small>{confidence == null ? 'confidence unavailable' : `${confidence}% confidence`}</small></div></section>
      <ValuationSection valuation={valuation} property={property} />
      <div className="section-label suitability-divider">SUITABILITY FOR YOU — scored from your weights, independent of the market price above</div>
      <section className="score-strip"><Bar label="Legal Safety" value={legal} color="#77d8ff" /><Bar label="Accessibility" value={accessibility} color="#f8c15c" /><Bar label="Flood Safety" value={flood} color="#d49aff" /><Bar label="Growth" value={growth} color="#b8f36a" /></section>
      <section className="why-grid"><div><div className="section-label">WHY THIS VERDICT?</div><h2>The weights are visible.<br /><em>The reasoning is grounded.</em></h2><div className="contribution-list">{contributions.map((item, index) => <div key={index}><span>{item.factor || 'Unnamed factor'}</span><strong className={(item.contribution || 0) < 0 ? 'negative' : ''}>{(item.contribution || 0) > 0 ? '+' : ''}{item.contribution ?? '—'}</strong></div>)}</div><div className="final-verdict"><span>FINAL</span><strong>{verdict}</strong><b>{record.score_breakdown?.composite_score ?? '—'}</b></div></div><div className="grounded-box"><div className="section-label"><Sparkles size={13} /> GROUNDED AI EXPLANATION</div><p>{record.verdict?.reasoning_summary || 'No grounded reasoning was returned for this evaluation.'}</p><button className="citation-row" onClick={() => setCitationsOpen(open => !open)}><span>Based on {record.verdict?.citations?.length || 0} citations</span><ChevronRight size={14} className={citationsOpen ? 'rotate-90' : ''} /></button>{citationsOpen && <div className="citation-list">{record.verdict?.citations?.length ? record.verdict.citations.map((citation, index) => <div key={index}><strong>{citation.claim}</strong><small>{citation.source_type} · {citation.source_reference}</small></div>) : <p className="muted">No grounded citations were returned.</p>}</div>}</div></section>
      <section className={`satellite-section${satelliteIsDemo ? ' synthetic' : ''}`}>{satelliteIsDemo && <div className="demo-banner"><TriangleAlert size={15} /> <strong>DEMO DATA.</strong> No AppEEARS credentials are configured, so this curve is invented to exercise the chart. It is not imagery and shows nothing about real vegetation or construction.</div>}<div className="section-head"><div><div className="section-label">SATELLITE SIGNAL</div><h2>Change over time</h2></div><div className="signal-summary"><strong>{record.satellite?.change_type ? record.satellite.change_type.replace('_', ' ') : 'unavailable'}</strong><span>{record.satellite?.change_confidence == null ? 'confidence unavailable' : `${Math.round(record.satellite.change_confidence * 100)}% confidence`} · {chart.length} usable observations</span></div></div>{chart.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={250}><LineChart data={chart}><CartesianGrid stroke="#25313a" vertical={false} /><XAxis dataKey="date" stroke="#71808b" tickLine={false} axisLine={false} /><YAxis stroke="#71808b" tickLine={false} axisLine={false} /><Tooltip contentStyle={{ background: '#11191d', border: '1px solid #2d3b42' }} /><Line type="monotone" dataKey="ndvi" stroke="#b8f36a" strokeWidth={2} dot={{ r: 3 }} name="NDVI" connectNulls={false} /><Line type="monotone" dataKey="ndbi" stroke="#f8c15c" strokeWidth={2} dot={{ r: 3 }} name="NDBI" connectNulls={false} /></LineChart></ResponsiveContainer></div> : <div className="chart-empty">No satellite observations were returned for this parcel and date range. Configure valid AppEEARS access to plot NDVI/NDBI.</div>}<div className="signal-foot"><span>{record.satellite?.change_type ? <>Satellite signal is classified as <strong>{record.satellite.change_type.replace('_', ' ')}.</strong></> : 'Satellite signal unavailable.'}</span><span>Analysis period · {record.metadata.analysis_date_from || '—'} to {record.metadata.analysis_date_to || '—'}</span></div></section>
      <section className="evidence-section"><div className="section-head"><div><div className="section-label">EVIDENCE LEDGER</div><h2>What supports the read</h2></div><span className="completeness" title="Share of evidence fields actually collected for this parcel">{record.metadata.data_completeness_pct ?? '—'}% of evidence fields collected</span></div><div className="tabs">{(['Satellite', 'Infrastructure', 'RERA', 'Uploaded Documents', 'Derived Scores'] as EvidenceTab[]).map(tab => <button className={tab === activeEvidenceTab ? 'active' : ''} key={tab} onClick={() => setActiveEvidenceTab(tab)}>{tab}</button>)}</div><div className="source-legend ledger-legend"><span><i className="dot live" /> LIVE</span><span><i className="dot cached" /> CACHED</span><span><i className="dot user_upload" /> YOUR UPLOAD</span><span><i className="dot derived" /> DERIVED</span><span><i className="dot seed" /> SEED DATA</span></div>{visibleEvidence.length ? visibleEvidence.map(item => <EvidenceRow key={item.evidence_id || item.title} title={item.title || item.source_type || 'Evidence'} refName={item.source_reference || 'TerraScope'} freshness={item.freshness || 'derived'} summary={item.summary || 'Collected evidence used in the evaluation.'} observedAt={item.observed_at} />) : <p className="muted evidence-empty">No {activeEvidenceTab.toLowerCase()} evidence is available for this parcel.</p>}</section>
    </div>
    {scenario && <Scenario settings={settings} verdict={verdict} before={record.score_breakdown?.composite_score ?? null} busy={busy} error={scenarioError} onClose={() => setScenario(false)} onRun={rerun} />}
    {historyOpen && <div className="drawer-backdrop" onClick={() => setHistoryOpen(false)}><aside className="history-drawer" onClick={event => event.stopPropagation()}><div className="drawer-header"><div><div className="panel-kicker">DECISION TRAIL</div><h2>Scenario history</h2></div><button className="icon-button" onClick={() => setHistoryOpen(false)}><X size={18} /></button></div><div className="history-list">{history.length ? history.map((item, index) => <div className="history-item" key={index}><div><strong>{item.profile}</strong><span>{item.changed}</span></div><b>{item.verdict}</b></div>) : <p className="muted">No alternate lenses explored yet. The immutable evidence stays fixed while you test assumptions.</p>}</div></aside></div>}
  </main>
}

function Scenario({ settings, verdict, before, onClose, onRun, busy, error }: { settings: EvaluationSettings; verdict: string; before: number | null; onClose: () => void; onRun: (settings: EvaluationSettings) => void; busy: boolean; error: string }) {
  const [local, setLocal] = useState(settings)
  const flood = local.weights.flood_safety_pct
  const maxFlood = Math.max(0, 100 - local.weights.legal_safety_pct - local.weights.accessibility_pct)
  const change = (value: number) => setLocal(current => ({ ...current, weights: { ...current.weights, flood_safety_pct: value, growth_pct: 100 - value - current.weights.legal_safety_pct - current.weights.accessibility_pct } }))
  return <div className="drawer-backdrop" onClick={onClose}><aside className="scenario-drawer" onClick={event => event.stopPropagation()}><div className="drawer-header"><div><div className="panel-kicker">SCENARIO MODE</div><h2>Explore scenarios</h2></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div><p className="drawer-intro">Change an assumption and re-evaluate the same evidence. Collection stays untouched.</p><div className="scenario-score"><div><span>BEFORE</span><strong>{verdict} · {before ?? '—'}</strong></div><ChevronRight size={20} /><div className="after"><span>AFTER</span><strong>Apply to calculate</strong></div></div><label className="field-label">FLOOD SAFETY WEIGHT <strong>{flood}%</strong></label><input className="scenario-range" type="range" min="0" max={maxFlood} value={Math.min(flood, maxFlood)} onChange={event => change(Number(event.target.value))} /><div className="scenario-note"><Sparkles size={15} /><p><strong>What changed?</strong><br />Adjust the weight, then apply the scenario to calculate a new verdict from the same immutable evidence.</p></div>{error && <p className="form-error">{error}</p>}<button className="primary-button scenario-apply" disabled={busy} onClick={() => onRun(local)}>{busy ? 'Re-evaluating…' : 'Apply scenario'}</button></aside></div>
}
