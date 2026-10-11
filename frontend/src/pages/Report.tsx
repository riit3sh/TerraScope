import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowLeft, ChevronRight, FileText, FlaskConical, History, IndianRupee, Printer, Sparkles, TriangleAlert, X } from 'lucide-react'
import { evaluateParcel, EvaluationSettings, ParcelRecord, PropertyDetails, Valuation, FloodIndicators } from '../lib/api'

type EvidenceTab = 'Satellite' | 'Infrastructure' | 'Flood indicators' | 'RERA' | 'Uploaded Documents' | 'Derived Scores'

const MECHANISM_LABEL: Record<string, string> = { river_flooding: 'River flooding (modelled)', historical_inundation: 'Historical inundation (observed)', observed_surface_water: 'Surface water seen 1984-2021', terrain_and_nearby_water: 'Terrain and nearby water', rainfall_waterlogging: 'Rainfall / waterlogging', coastal_flooding: 'Coastal flooding' }
const STATUS_LABEL: Record<string, string> = { assessed: 'assessed', partial: 'partly assessed', not_modelled: 'not modelled here', unavailable: 'unavailable', not_integrated: 'not integrated', not_assessed: 'not assessed' }
const pct = (value: number | null | undefined) => value == null ? '—' : `${Math.round(value * 100)}%`

const m = (value: number | null | undefined) => value == null ? '—' : `${Math.round(value).toLocaleString('en-IN')} m`

/** One line per flood mechanism, with the measurement behind it. Missing evidence reads as unknown, never as safe. */
function floodGlance(ind: FloodIndicators): { mechanism: string; status: string; text: string }[] {
  const byMechanism = Object.fromEntries((ind.components || []).map(c => [c.mechanism, c]))
  const river = ind.river_flood
  const lines: { mechanism: string; status: string; text: string }[] = []
  const riverComponent = byMechanism.river_flooding
  if (river?.scenarios?.length && riverComponent?.status !== 'unavailable') {
    const first = river.scenarios.find(s => (s.flooded_share_of_parcel || 0) > 0)
    const hundred = river.scenarios.find(s => s.return_period_years === 100)
    const parcel = first
      ? `Parcel first reached in the 1-in-${first.return_period_years}-year scenario (${(first.annual_exceedance_probability * 100).toFixed(first.annual_exceedance_probability < 0.01 ? 1 : 0)}% chance a year): ${pct(first.flooded_share_of_parcel)} of the parcel${first.max_depth_m == null ? '' : `, up to ${first.max_depth_m} m deep`}.`
      : 'No modelled river inundation on the parcel in any scenario up to 1-in-500 years.'
    const around = hundred?.surroundings_flooded_share == null ? '' : ` ${pct(hundred.surroundings_flooded_share)} of land within 500 m is flooded at 1-in-100.`
    const partial = river.assessed_share_of_parcel < 1 ? ` Only ${pct(river.assessed_share_of_parcel)} of the parcel is inside the modelled area.` : ''
    lines.push({ mechanism: 'river_flooding', status: riverComponent?.status || 'assessed', text: parcel + around + partial })
  } else if (riverComponent) lines.push({ mechanism: 'river_flooding', status: riverComponent.status, text: riverComponent.summary || '' })
  if (byMechanism.historical_inundation) lines.push({ mechanism: 'historical_inundation', status: byMechanism.historical_inundation.status, text: 'Not integrated: the NRSC flood atlas (1998-2022) has no machine-readable release. Unknown, not "never flooded".' })
  const sw = ind.surface_water
  if (sw?.parcel && sw.within_buffer) lines.push({ mechanism: 'observed_surface_water', status: 'assessed', text: `Water seen at least once on ${pct(sw.parcel.water_ever_fraction)} of the parcel's 30 m pixels${sw.parcel.water_ever_fraction > 0 ? ` (the wettest pixel was water in ${sw.parcel.occurrence_max_pct === 0 ? 'under 1' : sw.parcel.occurrence_max_pct}% of observations)` : ''}; at least once on ${pct(sw.within_buffer.water_ever_fraction)} of pixels within ${sw.buffer_m} m. Landsat 1984-2021: where water was seen, not a flood record.` })
  else if (byMechanism.observed_surface_water) lines.push({ mechanism: 'observed_surface_water', status: byMechanism.observed_surface_water.status, text: byMechanism.observed_surface_water.summary || '' })
  const t = ind.terrain, w = ind.water_distances
  const terrainParts = [
    t?.parcel_elevation_m == null ? null : `Parcel ${t.parcel_elevation_m} m above sea level`,
    t?.elevation_above_nearest_water_m == null ? (t?.water_features_available === false ? null : 'no mapped water within 2 km to compare against')
      : `${t.elevation_above_nearest_water_m >= 0 ? '+' : ''}${t.elevation_above_nearest_water_m} m relative to the nearest mapped water (${t.nearest_water_feature_class || t.nearest_water_feature_kind}${t.nearest_water_feature_name ? ` ${t.nearest_water_feature_name}` : ''}, ${m(t.nearest_water_feature_distance_m)} away)`,
    w ? `nearest river/canal ${m(w.nearest_river_canal_distance_m)}, tank/lake ${m(w.nearest_tank_lake_distance_m)}` : null,
  ].filter(Boolean)
  if (terrainParts.length) lines.push({ mechanism: 'terrain_and_nearby_water', status: 'assessed', text: `${terrainParts.join('; ')}. A terrain indicator, not a flood probability.` })
  else if (byMechanism.terrain_and_nearby_water) lines.push({ mechanism: 'terrain_and_nearby_water', status: byMechanism.terrain_and_nearby_water.status, text: byMechanism.terrain_and_nearby_water.summary || '' })
  for (const mechanism of ['rainfall_waterlogging', 'coastal_flooding']) if (byMechanism[mechanism]) lines.push({ mechanism, status: byMechanism[mechanism].status, text: byMechanism[mechanism].status === 'not_assessed' ? 'Not assessed: no dataset integrated. Unknown, not safe.' : byMechanism[mechanism].summary || '' })
  return lines
}

function FloodPanel({ indicators }: { indicators?: FloodIndicators | null }) {
  if (!indicators?.components?.length) return null
  const river = indicators.river_flood
  const partial = indicators.assessment_status === 'partial'
  return <section className="flood-section"><div className="section-head"><div><div className="section-label">FLOOD EVIDENCE · NOT USED IN ANY SCORE OR PRICE</div><h2>{partial ? 'Partial flood assessment' : 'No usable flood evidence'}</h2></div><span className="completeness">Each mechanism separately, with its measurement. No overall flood score or safety percentage.</span></div>
    <table className="flood-glance"><tbody>{floodGlance(indicators).map(line => <tr key={line.mechanism}><th>{MECHANISM_LABEL[line.mechanism] || line.mechanism}</th><td><span className={`factor-badge ${line.status}`}>{STATUS_LABEL[line.status] || line.status}</span></td><td>{line.text}</td></tr>)}</tbody></table>
    <details className="flood-details"><summary>Scenario table, sources and method</summary>
    {river && river.scenarios?.length > 0 && <div className="flood-table-wrap"><table className="flood-table"><caption>Modelled river flooding by return period · {river.dataset} · {river.resolution} · {pct(river.assessed_share_of_parcel)} of the parcel assessed{river.permanent_water_area_m2 > 0 ? ` · ${Math.round(river.permanent_water_area_m2)} m² permanent water excluded` : ''}{river.quality_flagged_area_m2 > 0 ? ` · ${Math.round(river.quality_flagged_area_m2)} m² in a provider-flagged area (depths withheld)` : ''}</caption><thead><tr><th>Scenario</th><th>Chance in any year</th><th>Parcel area flooded</th><th>Max depth</th><th>Mean depth</th><th>Land within 500 m flooded</th></tr></thead><tbody>{river.scenarios.map(s => <tr key={s.return_period_years}><td>1-in-{s.return_period_years} years</td><td>{(s.annual_exceedance_probability * 100).toFixed(s.annual_exceedance_probability < 0.01 ? 1 : 0)}%</td><td>{pct(s.flooded_share_of_parcel)}{s.flooded_area_m2 > 0 ? ` (${Math.round(s.flooded_area_m2).toLocaleString()} m²)` : ''}</td><td>{s.max_depth_m == null ? '—' : `${s.max_depth_m} m`}</td><td>{s.mean_depth_m == null ? '—' : `${s.mean_depth_m} m`}</td><td>{pct(s.surroundings_flooded_share)}</td></tr>)}</tbody></table><small className="flood-note">Modelled scenarios, not observed floods. “0%” means no modelled river inundation at ~90 m for rivers with basins over ~500 km²; it does not cover small streams, rainfall waterlogging or coastal surge, and is not building-level safety.</small></div>}
    <div className="flood-components">{indicators.components.map(c => <div className={`flood-component ${c.status}`} key={c.mechanism}><div className="flood-component-head"><strong>{MECHANISM_LABEL[c.mechanism] || c.mechanism}</strong><span className={`factor-badge ${c.status}`}>{STATUS_LABEL[c.status] || c.status}</span></div><p>{c.summary}</p>{(c.source || c.period || c.resolution) && <small>{[c.source, c.period, c.resolution, c.coverage_share == null ? null : `${pct(c.coverage_share)} of parcel covered`].filter(Boolean).join(' · ')}</small>}</div>)}</div>
    </details>
  </section>
}

function Bar({ label, value, color, status }: { label: string; value: number | null; color: string; status?: string }) {
  const available = typeof value === 'number'
  return <div className={`score-line${available ? '' : ' unassessed'}`}>
    <div><span>{label}</span><strong>{available ? value : 'Not assessed'}</strong></div>
    <div className="bar"><i style={{ width: available ? `${Math.max(0, Math.min(100, value))}%` : '0%', background: color }} /></div>
    {status && status !== 'assessed' && <small className="score-status">{status === 'indicative' ? 'indicative only' : status === 'partial' ? 'partial evidence · not scored' : 'no supporting evidence'}</small>}
  </div>
}

function EvidenceRow({ title, refName, freshness, summary, observedAt, details }: { title: string; refName: string; freshness: string; summary: string; observedAt?: string | null; details?: string }) {
  return <div className="evidence-row"><div className="evidence-icon"><FileText size={16} /></div><div><strong>{title}</strong><p>{summary}</p><small>{refName} · {(observedAt || '').slice(0, 10) || 'date unavailable'}</small>{details && <small className="evidence-details">{details}</small>}</div><span className={`freshness ${freshness}`}>{freshness.replace('_', ' ')}</span></div>
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
  no_price_data: 'No licensed listing feed or permitted price data is loaded, so TerraScope does not quote a price.',
  price_data_invalid: 'The loaded price data could not be used.',
  price_type_not_covered: 'No prices of the selected type are loaded.',
  land_use_not_covered: 'No comparable prices exist for this land use.',
  no_comparables_nearby: 'No comparable land prices exist near this parcel.',
  stale_data_only: 'The only nearby prices are too old to use.',
  area_outside_support: 'This parcel is far larger or smaller than every comparable, so their prices do not transfer.',
  insufficient_comparables: 'Too few comparable prices exist near this parcel.',
  request_failed: 'The valuation service could not be reached.',
  valuation_error: 'The valuation could not be computed.',
}
const PRICE_TITLE: Record<string, string> = { asking: 'Listing-based estimated price range', transaction: 'Sale-based estimated price range', guideline: 'Government guideline value (reference)' }

function ValuationSection({ valuation, property }: { valuation: Valuation | null; property: PropertyDetails | null }) {
  const label = <div className="section-label"><IndianRupee size={13} /> LAND PRICE · KEPT SEPARATE FROM LEGAL, FLOOD AND SUITABILITY</div>
  if (!valuation) {
    return <section className="valuation-section unavailable">{label}<h2>Not requested</h2><p className="muted">No price estimate was run for this parcel. It needs a location and a plot area.</p></section>
  }
  if (valuation.status === 'unavailable') {
    return <section className="valuation-section unavailable">{label}<h2>No price estimate</h2><p className="valuation-reason">{unavailableCopy[valuation.reason] || 'A price estimate could not be produced.'}</p><p className="muted valuation-detail">{valuation.detail}</p><p className="muted">TerraScope refuses rather than guesses. Asking prices, sale prices and government guideline values are kept separate and are never invented.</p></section>
  }
  const spread = valuation.spread_inr_per_sqft
  const validated = valuation.validation.status === 'validated'
  return <section className="valuation-section">
    <div className="section-head"><div>{label}<h2>{PRICE_TITLE[valuation.price_type] || 'Estimated price range'}</h2></div><span className={`valuation-stamp${validated ? '' : ' unvalidated'}`}>{validated ? 'held-out accuracy measured' : 'NOT YET VALIDATED'} · data {valuation.data_version} · {valuation.valuation_date}</span></div>
    <p className="valuation-basis">Based on <strong>{valuation.price_type_label}</strong>.{valuation.price_type === 'asking' ? ' These are not completed sale prices.' : ''}</p>
    <div className="valuation-grid">
      <div className="valuation-primary"><span>TYPICAL ({valuation.comparable_count} COMPARABLES)</span><strong>₹{inr(valuation.estimate_inr_per_sqft)}</strong><small>per sq ft · median</small></div>
      <div className="valuation-primary"><span>MIDDLE HALF OF COMPARABLES</span><strong>₹{inr(spread.p25)} – ₹{inr(spread.p75)}</strong><small>per sq ft · full spread ₹{inr(spread.min)} – ₹{inr(spread.max)}</small></div>
      <div className="valuation-range">{valuation.total_inr
        ? <><span>TOTAL FOR {inr(valuation.area_sqft)} SQ FT</span><strong>{compactInr(valuation.total_inr.p25)} – {compactInr(valuation.total_inr.p75)}</strong><small>{property?.area_sqft_override ? 'area you entered' : 'area from your boundary'} × the middle-half rates</small></>
        : <><span>TOTAL</span><strong className="muted-strong">Not shown</strong><small>The parcel is outside the size range of the comparables.</small></>}</div>
    </div>
    <p className="muted valuation-detail">{valuation.spread_basis}</p>
    <div className="valuation-facts">
      <div><span>COMPARABLES</span><strong>{valuation.comparable_count} within {valuation.radius_km} km</strong><small>{valuation.land_use.replace('_', ' ')} {valuation.property_category.replace('_', ' ')} only</small></div>
      <div><span>DATES</span><strong>{valuation.observed_from} – {valuation.observed_to}</strong><small>not adjusted for price changes over time</small></div>
      <div><span>SOURCES</span><strong>{valuation.sources.length}</strong><small>{valuation.sources.join(', ')}</small></div>
      <div><span>PREDICTION QUALITY</span><strong>{validated ? 'Measured' : 'Not yet validated'}</strong><small>{validated ? Object.entries(valuation.validation.holdouts || {}).map(([name, h]) => h.baseline ? `${name}: median error ${h.baseline.median_ape_pct}% on ${h.estimates} held-out ${valuation.price_type} prices` : `${name}: not validated`).join(' · ') : valuation.validation.note || 'Too few held-out observations to measure accuracy.'}</small></div>
    </div>
    <div className="valuation-uncertainty"><strong>Why this is uncertain</strong><ul>{valuation.uncertainty.map(reason => <li key={reason}>{reason}</li>)}</ul></div>
    <details className="valuation-comparables"><summary>Comparable observations ({valuation.comparables.length} shown)</summary><table className="flood-table"><thead><tr><th>Source / record</th><th>Type</th><th>Observed</th><th>₹ / sq ft</th><th>Area (sq ft)</th><th>Distance</th><th>Location</th></tr></thead><tbody>{valuation.comparables.map(c => <tr key={`${c.source}-${c.source_record_id}`}><td>{c.source_url ? <a href={c.source_url} target="_blank" rel="noreferrer">{c.source} · {c.source_record_id}</a> : `${c.source} · ${c.source_record_id}`}{c.listed_by_sources > 1 ? ` (listed ${c.listed_by_sources}×, counted once)` : ''}<small className="comparable-basis">reuse: {c.reuse_basis} · retrieved {c.retrieved_date}</small></td><td>{c.price_type}</td><td>{c.observed_date}</td><td>₹{inr(c.price_inr_per_sqft)}</td><td>{c.area_sqft == null ? '—' : inr(c.area_sqft)}</td><td>{c.distance_km} km</td><td>{c.location_precision}{c.locality ? ` · ${c.locality}` : ''}</td></tr>)}</tbody></table></details>
    <p className="valuation-foot">The price comes only from comparable prices and the property details you entered. It never uses your suitability weights, flood evidence or legal status, and none of those use it.</p>
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
  const factors = breakdown?.factors || []
  const assessedWeight = Math.round(breakdown?.assessed_weight_pct ?? 0)
  const insufficient = verdict === 'INSUFFICIENT_EVIDENCE'
  const statusOf = (name: string) => factors.find(f => f.factor === name)?.status
  const satelliteIsDemo = evidence.some(item => (item.source_type || '') === 'satellite' && /synthetic/i.test(`${item.source_reference || ''} ${item.title || ''}`))
  const tabMatch: Record<EvidenceTab, string[]> = { Satellite: ['satellite'], Infrastructure: ['openstreetmap', 'infrastructure'], 'Flood indicators': ['jrc_gsw', 'copernicus_dem', 'osm_water', 'open_elevation', 'elevation'], RERA: ['maharera_seed', 'rera'], 'Uploaded Documents': ['document', 'user_upload'], 'Derived Scores': ['derived'] }
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
      <section className="report-heading"><div><div className="eyebrow"><span className="pulse" /> ANALYSIS SNAPSHOT · {(record.metadata.analysis_snapshot_id || '—').slice(0, 8)}</div><h1>{record.location?.address || 'Location unavailable'}</h1><p>{record.geometry_metadata?.area_acres == null ? 'Area unavailable' : `${record.geometry_metadata.area_acres.toFixed(2)} acres`} <span>·</span> {record.metadata.analysis_date_from || '—'} — {record.metadata.analysis_date_to || '—'}</p></div><div className={`verdict-badge ${verdict.toLowerCase()}`}><span>RECOMMENDATION</span><strong>{insufficient ? 'INSUFFICIENT EVIDENCE' : verdict}</strong><small>{insufficient ? `${assessedWeight}% of weighting evidenced` : 'rule-based verdict'}</small></div></section>
      <ValuationSection valuation={valuation} property={property} />
      <div className="section-label suitability-divider">SUITABILITY FOR YOU — scored from your weights, independent of the market price above</div>
      <section className="score-strip"><Bar label="Legal Safety" value={legal} color="#77d8ff" status={statusOf('legal_safety')} /><Bar label="Accessibility" value={accessibility} color="#f8c15c" status={statusOf('accessibility')} /><Bar label="Flood Safety" value={flood} color="#d49aff" status={statusOf('flood_safety')} /><Bar label="Growth" value={growth} color="#b8f36a" status={statusOf('growth')} /></section>
      <section className="evidence-status"><div className="section-head"><div><div className="section-label">EVIDENCE BEHIND EACH FACTOR</div><h2>What is actually assessed</h2></div><span className="completeness">{assessedWeight}% of your weighting is backed by evidence</span></div>{insufficient && <p className="insufficient-note">No BUY / WAIT / AVOID is shown. A factor carrying weight but no evidence is left unknown rather than scored 50, and the remaining factors are not re-weighted to fill the gap.</p>}<div className="factor-list">{factors.map(f => <div className={`factor ${f.status}`} key={f.factor}><div className="factor-head"><strong>{f.factor.replace(/_/g, ' ')}</strong><span className={`factor-badge ${f.status}`}>{f.score == null ? f.status.replace(/_/g, ' ') : `${f.score} · ${f.status}`}</span><em>{f.weight_pct}% weight</em></div><p>{f.basis}</p><small>{f.limitations}</small>{f.checklist && f.checklist.length > 0 && <ul className="checklist">{f.checklist.map(c => <li key={c}>{c}</li>)}</ul>}</div>)}</div></section><FloodPanel indicators={record.flood_indicators} /><section className="why-grid"><div><div className="section-label">WHY THIS VERDICT?</div><h2>The weights are visible.<br /><em>The reasoning is grounded.</em></h2><div className="contribution-list">{contributions.map((item, index) => <div key={index}><span>{item.factor || 'Unnamed factor'}</span><strong className={(item.contribution || 0) < 0 ? 'negative' : ''}>{(item.contribution || 0) > 0 ? '+' : ''}{item.contribution ?? '—'}</strong></div>)}</div><div className="final-verdict"><span>FINAL</span><strong>{insufficient ? 'INSUFFICIENT EVIDENCE' : verdict}</strong><b>{record.score_breakdown?.composite_score ?? '—'}</b></div></div><div className="grounded-box"><div className="section-label"><Sparkles size={13} /> GROUNDED AI EXPLANATION</div><p>{record.verdict?.reasoning_summary || 'No grounded reasoning was returned for this evaluation.'}</p><button className="citation-row" onClick={() => setCitationsOpen(open => !open)}><span>Based on {record.verdict?.citations?.length || 0} citations</span><ChevronRight size={14} className={citationsOpen ? 'rotate-90' : ''} /></button>{citationsOpen && <div className="citation-list">{record.verdict?.citations?.length ? record.verdict.citations.map((citation, index) => <div key={index}><strong>{citation.claim}</strong><small>{citation.source_type} · {citation.source_reference}</small></div>) : <p className="muted">No grounded citations were returned.</p>}</div>}</div></section>
      <section className={`satellite-section${satelliteIsDemo ? ' synthetic' : ''}`}>{satelliteIsDemo && <div className="demo-banner"><TriangleAlert size={15} /> <strong>DEMO DATA.</strong> No AppEEARS credentials are configured, so this curve is invented to exercise the chart. It is not imagery and shows nothing about real vegetation or construction.</div>}<div className="section-head"><div><div className="section-label">SATELLITE SIGNAL</div><h2>Change over time</h2></div><div className="signal-summary"><strong>{satelliteIsDemo ? 'demo series' : record.satellite?.change_type ? record.satellite.change_type.replace('_', ' ') : 'unavailable'}</strong><span>{satelliteIsDemo ? 'no confidence figure: series is invented' : record.satellite?.change_confidence == null ? 'confidence unavailable' : `${Math.round(record.satellite.change_confidence * 100)}% confidence`} · {chart.length} usable observations</span></div></div>{chart.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={250}><LineChart data={chart}><CartesianGrid stroke="#25313a" vertical={false} /><XAxis dataKey="date" stroke="#71808b" tickLine={false} axisLine={false} /><YAxis stroke="#71808b" tickLine={false} axisLine={false} /><Tooltip contentStyle={{ background: '#11191d', border: '1px solid #2d3b42' }} /><Line type="monotone" dataKey="ndvi" stroke="#b8f36a" strokeWidth={2} dot={{ r: 3 }} name="NDVI" connectNulls={false} /><Line type="monotone" dataKey="ndbi" stroke="#f8c15c" strokeWidth={2} dot={{ r: 3 }} name="NDBI" connectNulls={false} /></LineChart></ResponsiveContainer></div> : <div className="chart-empty">No satellite observations were returned for this parcel and date range. Configure valid AppEEARS access to plot NDVI/NDBI.</div>}<div className="signal-foot"><span>{record.satellite?.change_type ? <>Satellite signal is classified as <strong>{record.satellite.change_type.replace('_', ' ')}.</strong></> : 'Satellite signal unavailable.'}</span><span>Analysis period · {record.metadata.analysis_date_from || '—'} to {record.metadata.analysis_date_to || '—'}</span></div></section>
      <section className="evidence-section"><div className="section-head"><div><div className="section-label">EVIDENCE LEDGER</div><h2>What supports the read</h2></div><span className="completeness" title="Share of evidence fields actually collected for this parcel">{record.metadata.data_completeness_pct ?? '—'}% of evidence fields collected</span></div><div className="tabs">{(['Satellite', 'Infrastructure', 'Flood indicators', 'RERA', 'Uploaded Documents', 'Derived Scores'] as EvidenceTab[]).map(tab => <button className={tab === activeEvidenceTab ? 'active' : ''} key={tab} onClick={() => setActiveEvidenceTab(tab)}>{tab}</button>)}</div><div className="source-legend ledger-legend"><span><i className="dot live" /> LIVE</span><span><i className="dot cached" /> CACHED</span><span><i className="dot user_upload" /> YOUR UPLOAD</span><span><i className="dot derived" /> DERIVED</span><span><i className="dot seed" /> SEED DATA</span></div>{visibleEvidence.length ? visibleEvidence.map(item => <EvidenceRow key={item.evidence_id || item.title} title={item.title || item.source_type || 'Evidence'} refName={item.source_reference || 'TerraScope'} freshness={item.freshness || 'derived'} summary={item.summary || 'Collected evidence used in the evaluation.'} observedAt={item.observed_at} details={[item.observation_period && `observed ${item.observation_period}`, item.resolution, item.licence].filter(Boolean).join(' · ')} />) : <p className="muted evidence-empty">No {activeEvidenceTab.toLowerCase()} evidence is available for this parcel.</p>}</section>
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
