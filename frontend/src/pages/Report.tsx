import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowLeft, ChevronRight, FileText, FlaskConical, History, Sparkles, X } from 'lucide-react'
import { evaluateParcel, EvaluationSettings, ParcelRecord } from '../lib/api'

type EvidenceTab = 'Satellite' | 'Infrastructure' | 'RERA' | 'Uploaded Documents' | 'Derived Scores'

function Bar({ label, value, color }: { label: string; value: number | null; color: string }) {
  const available = typeof value === 'number'
  return <div className="score-line"><div><span>{label}</span><strong>{available ? value : '—'}</strong></div><div className="bar"><i style={{ width: available ? `${Math.max(0, Math.min(100, value))}%` : '0%', background: color }} /></div></div>
}

function EvidenceRow({ title, refName, freshness, summary, observedAt }: { title: string; refName: string; freshness: string; summary: string; observedAt?: string | null }) {
  return <div className="evidence-row"><div className="evidence-icon"><FileText size={16} /></div><div><strong>{title}</strong><p>{summary}</p><small>{refName} · {(observedAt || '').slice(0, 10) || 'date unavailable'}</small></div><span className={`freshness ${freshness}`}>{freshness.replace('_', ' ')}</span></div>
}

export function Report({ initialSnapshot, initialSettings, onBack }: { initialSnapshot: ParcelRecord; initialSettings: EvaluationSettings; onBack: () => void }) {
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
  const legal = record.risk?.legal_risk_score == null ? null : Math.max(0, 100 - record.risk.legal_risk_score)
  const accessibility = record.risk?.accessibility_score ?? null
  const flood = record.risk?.flood_risk_score == null ? null : Math.max(0, 100 - record.risk.flood_risk_score)
  const growth = record.opportunity?.growth_score ?? null
  const verdict = record.verdict?.recommendation || 'UNAVAILABLE'
  const confidence = record.verdict?.confidence == null ? null : Math.round(record.verdict.confidence * 100)
  const contributions = record.score_breakdown?.weighted_contributions || []
  const evidence = record.evidence || []
  const tabMatch: Record<EvidenceTab, string[]> = { Satellite: ['satellite'], Infrastructure: ['openstreetmap', 'infrastructure'], RERA: ['maharera_seed', 'rera'], 'Uploaded Documents': ['document', 'user_upload'], 'Derived Scores': ['derived'] }
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
    <header className="report-topbar"><button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Workspace</button><div className="wordmark"><span className="mark"><Sparkles size={14} /></span> TERRASCOPE</div><div className="report-tools"><button className="quiet-button" onClick={() => setHistoryOpen(true)}><History size={15} /> Scenario history</button><button className="quiet-button" onClick={() => setScenario(true)}><FlaskConical size={15} /> Explore scenarios</button></div></header>
    <div className="report-content">
      <section className="report-heading"><div><div className="eyebrow"><span className="pulse" /> ANALYSIS SNAPSHOT · {(record.metadata.analysis_snapshot_id || '—').slice(0, 8)}</div><h1>{record.location?.address || 'Location unavailable'}</h1><p>{record.geometry_metadata?.area_acres == null ? 'Area unavailable' : `${record.geometry_metadata.area_acres.toFixed(2)} acres`} <span>·</span> {record.metadata.analysis_date_from || '—'} — {record.metadata.analysis_date_to || '—'}</p></div><div className={`verdict-badge ${verdict.toLowerCase()}`}><span>RECOMMENDATION</span><strong>{verdict}</strong><small>{confidence == null ? 'confidence unavailable' : `${confidence}% confidence`}</small></div></section>
      <section className="score-strip"><Bar label="Legal Safety" value={legal} color="#77d8ff" /><Bar label="Accessibility" value={accessibility} color="#f8c15c" /><Bar label="Flood Safety" value={flood} color="#d49aff" /><Bar label="Growth" value={growth} color="#b8f36a" /></section>
      <section className="why-grid"><div><div className="section-label">WHY THIS VERDICT?</div><h2>The weights are visible.<br /><em>The reasoning is grounded.</em></h2><div className="contribution-list">{contributions.map((item, index) => <div key={index}><span>{item.factor || 'Unnamed factor'}</span><strong className={(item.contribution || 0) < 0 ? 'negative' : ''}>{(item.contribution || 0) > 0 ? '+' : ''}{item.contribution ?? '—'}</strong></div>)}</div><div className="final-verdict"><span>FINAL</span><strong>{verdict}</strong><b>{record.score_breakdown?.composite_score ?? '—'}</b></div></div><div className="grounded-box"><div className="section-label"><Sparkles size={13} /> GROUNDED AI EXPLANATION</div><p>{record.verdict?.reasoning_summary || 'No grounded reasoning was returned for this evaluation.'}</p><button className="citation-row" onClick={() => setCitationsOpen(open => !open)}><span>Based on {record.verdict?.citations?.length || 0} citations</span><ChevronRight size={14} className={citationsOpen ? 'rotate-90' : ''} /></button>{citationsOpen && <div className="citation-list">{record.verdict?.citations?.length ? record.verdict.citations.map((citation, index) => <div key={index}><strong>{citation.claim}</strong><small>{citation.source_type} · {citation.source_reference}</small></div>) : <p className="muted">No grounded citations were returned.</p>}</div>}</div></section>
      <section className="satellite-section"><div className="section-head"><div><div className="section-label">SATELLITE SIGNAL</div><h2>Change over time</h2></div><div className="signal-summary"><strong>{record.satellite?.change_type ? record.satellite.change_type.replace('_', ' ') : 'unavailable'}</strong><span>{record.satellite?.change_confidence == null ? 'confidence unavailable' : `${Math.round(record.satellite.change_confidence * 100)}% confidence`} · {chart.length} usable observations</span></div></div>{chart.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={250}><LineChart data={chart}><CartesianGrid stroke="#25313a" vertical={false} /><XAxis dataKey="date" stroke="#71808b" tickLine={false} axisLine={false} /><YAxis stroke="#71808b" tickLine={false} axisLine={false} /><Tooltip contentStyle={{ background: '#11191d', border: '1px solid #2d3b42' }} /><Line type="monotone" dataKey="ndvi" stroke="#b8f36a" strokeWidth={2} dot={{ r: 3 }} name="NDVI" connectNulls={false} /><Line type="monotone" dataKey="ndbi" stroke="#f8c15c" strokeWidth={2} dot={{ r: 3 }} name="NDBI" connectNulls={false} /></LineChart></ResponsiveContainer></div> : <div className="chart-empty">No satellite observations were returned for this parcel and date range. Configure valid AppEEARS access to plot NDVI/NDBI.</div>}<div className="signal-foot"><span>{record.satellite?.change_type ? <>Satellite signal is classified as <strong>{record.satellite.change_type.replace('_', ' ')}.</strong></> : 'Satellite signal unavailable.'}</span><span>Analysis period · {record.metadata.analysis_date_from || '—'} to {record.metadata.analysis_date_to || '—'}</span></div></section>
      <section className="evidence-section"><div className="section-head"><div><div className="section-label">EVIDENCE LEDGER</div><h2>What supports the read</h2></div><span className="completeness">{record.metadata.data_completeness_pct ?? '—'}% complete</span></div><div className="tabs">{(['Satellite', 'Infrastructure', 'RERA', 'Uploaded Documents', 'Derived Scores'] as EvidenceTab[]).map(tab => <button className={tab === activeEvidenceTab ? 'active' : ''} key={tab} onClick={() => setActiveEvidenceTab(tab)}>{tab}</button>)}</div>{visibleEvidence.length ? visibleEvidence.map(item => <EvidenceRow key={item.evidence_id || item.title} title={item.title || item.source_type || 'Evidence'} refName={item.source_reference || 'TerraScope'} freshness={item.freshness || 'derived'} summary={item.summary || 'Collected evidence used in the evaluation.'} observedAt={item.observed_at} />) : <p className="muted evidence-empty">No {activeEvidenceTab.toLowerCase()} evidence is available for this parcel.</p>}</section>
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
