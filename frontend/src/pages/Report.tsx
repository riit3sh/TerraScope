import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowLeft, FileText, FlaskConical, History, IndianRupee, Printer, RefreshCw, Sparkles, TriangleAlert, Upload, X } from 'lucide-react'
import { DOC_TYPE_LABEL, DocType, estimateValuation, evaluateParcel, PriceBasis, EvaluationSettings, FactorAssessment, Finding, FloodIndicators, LandCoverHistory, LandDetails, ParcelRecord, PropertyDetails, saveLandDetails, uploadEvidence, Valuation } from '../lib/api'

type EvidenceTab = 'Satellite' | 'Infrastructure' | 'Flood indicators' | 'RERA' | 'Uploaded Documents' | 'Derived Scores'

const MECHANISM_LABEL: Record<string, string> = { river_flooding: 'River flooding (modelled)', historical_inundation: 'Historical inundation (observed)', observed_surface_water: 'Surface water seen 1984-2021', terrain_and_nearby_water: 'Terrain and nearby water', rainfall_waterlogging: 'Rainfall / waterlogging', coastal_flooding: 'Coastal flooding' }
const STATUS_LABEL: Record<string, string> = { assessed: 'assessed', partial: 'partly assessed', not_modelled: 'not modelled here', unavailable: 'unavailable', not_integrated: 'not integrated', not_assessed: 'not assessed' }
const FACTOR_LABEL: Record<string, string> = { legal_safety: 'Legal safety', accessibility: 'Accessibility', flood_safety: 'Flood safety', growth: 'Area growth' }
const COMPLETENESS_LABEL: Record<string, string> = { district: 'District (from geocoding)', area_m2: 'Parcel area', satellite_series: 'Satellite series', nearest_road: 'Nearest road', nearest_school: 'Nearest school', elevation: 'Elevation', flood_proxy: 'Terrain position', surface_water: 'Surface water', water_features: 'Rivers, canals, tanks', river_flood_hazard: 'River flood model', area_history: 'Area history 2017-2023', rera_status: 'RERA registration', land_records: 'Land records' }
const CHANGE_LABEL: Record<string, string> = { no_change: 'no material change', inconclusive: 'inconclusive change signal', construction_growth: 'change consistent with construction', vegetation_loss: 'vegetation loss', vegetation_gain: 'vegetation gain', insufficient_evidence: 'too few observations' }
/** Whole percent, except one decimal below 10% so 1.49% never shows as "1%" beside a "1.5%". */
const pct = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(value > 0 && value < 0.1 ? 1 : 0)}%`
const m = (value: number | null | undefined) => value == null ? '—' : `${Math.round(value).toLocaleString('en-IN')} m`
/** Annual exceedance probability of a 1-in-N-year modelled event, exactly: 1-in-75 is 1.33%, not "1%". */
const aep = (returnPeriod: number) => `${Number((100 / returnPeriod).toFixed(2))}%`
const sentence = (text: string | null | undefined) => (text || '').trim()
const cutOff = (text: string) => text.length > 0 && !/[.!?)"']$/.test(text)

/** "Vellore Institute of Technology, Subway, …" -> heading "Vellore Institute of Technology"; the full address goes underneath. */
function placeName(address: string | null | undefined) {
  if (!address) return 'Unnamed parcel'
  const parts = address.split(',').map(part => part.trim()).filter(Boolean)
  return parts[0].length < 4 || /^\d/.test(parts[0]) ? parts.slice(0, 2).join(', ') : parts[0]
}

/** One headline for the flood evidence: what was assessed and what was not, never a safety figure. */
function floodHeadline(ind: FloodIndicators | null | undefined) {
  const parts = ind?.components || []
  if (!parts.length) return 'No flood evidence collected'
  const river = parts.find(c => c.mechanism === 'river_flooding')
  const missing = parts.some(c => !['assessed', 'partial'].includes(c.status))
  const riverDone = river && ['assessed', 'partial'].includes(river.status)
  if (riverDone) return missing ? 'River flood exposure assessed; other mechanisms incomplete' : 'River flood exposure assessed'
  return parts.some(c => ['assessed', 'partial'].includes(c.status)) ? 'River flooding not assessed; other indicators measured' : 'No usable flood evidence'
}

function riverSentence(ind: FloodIndicators) {
  const river = ind.river_flood
  if (!river?.scenarios?.length) return null
  const first = river.scenarios.find(s => (s.flooded_area_m2 || 0) > 0)
  if (!first) return `No modelled river inundation on the parcel in any scenario up to 1-in-500 years.`
  return `Modelled river inundation first reaches the parcel in the 1-in-${first.return_period_years}-year scenario (annual exceedance probability ${aep(first.return_period_years)}): ${pct(first.flooded_share_of_parcel)} of the parcel${first.max_depth_m == null ? '' : `, up to ${first.max_depth_m} m deep`}.`
}

/** One line per mechanism, with the measurement behind it. Missing evidence reads as unknown, never as safe. */
function floodGlance(ind: FloodIndicators): { mechanism: string; status: string; text: string }[] {
  const byMechanism = Object.fromEntries((ind.components || []).map(c => [c.mechanism, c]))
  const lines: { mechanism: string; status: string; text: string }[] = []
  const river = ind.river_flood, riverComponent = byMechanism.river_flooding
  if (river?.scenarios?.length && riverComponent?.status !== 'unavailable') {
    const hundred = river.scenarios.find(s => s.return_period_years === 100)
    const around = hundred?.surroundings_flooded_share == null ? '' : ` Parcel and the ${river.surroundings_m || 500} m around it: ${pct(hundred.surroundings_flooded_share)} of the land flooded at 1-in-100.`
    const partial = river.assessed_share_of_parcel < 1 ? ` Only ${pct(river.assessed_share_of_parcel)} of the parcel lies inside the map.` : ''
    lines.push({ mechanism: 'river_flooding', status: riverComponent?.status || 'assessed', text: `${riverSentence(ind)}${around}${partial}` })
  } else if (riverComponent) lines.push({ mechanism: 'river_flooding', status: riverComponent.status, text: sentence(riverComponent.summary) })
  if (byMechanism.historical_inundation) lines.push({ mechanism: 'historical_inundation', status: byMechanism.historical_inundation.status, text: 'No permitted machine-readable source integrated (the NRSC flood atlas was investigated). Unknown, not "never flooded".' })
  const sw = ind.surface_water
  if (sw?.parcel && sw.within_buffer) lines.push({ mechanism: 'observed_surface_water', status: 'assessed', text: `Water seen at least once on ${pct(sw.parcel.water_ever_fraction)} of the ${sw.parcel.pixels} pixels touching the parcel, and on ${pct(sw.within_buffer.water_ever_fraction)} of pixels in the parcel and the ${sw.buffer_m} m around it. Where water was seen, not a flood record.` })
  else if (byMechanism.observed_surface_water) lines.push({ mechanism: 'observed_surface_water', status: byMechanism.observed_surface_water.status, text: sentence(byMechanism.observed_surface_water.summary) })
  const t = ind.terrain, w = ind.water_distances
  const terrainParts = [
    t?.parcel_elevation_m == null ? null : `Parcel ${t.parcel_elevation_m} m above sea level`,
    t?.elevation_above_nearest_water_m == null ? (t?.water_features_available === false ? null : 'no mapped water within 2 km to compare against')
      : `${t.elevation_above_nearest_water_m >= 0 ? '+' : ''}${t.elevation_above_nearest_water_m} m relative to the nearest mapped water (${t.nearest_water_feature_class || t.nearest_water_feature_kind}${t.nearest_water_feature_name ? ` ${t.nearest_water_feature_name}` : ''}, ${m(t.nearest_water_feature_distance_m)} away)`,
    w ? `nearest river/canal ${m(w.nearest_river_canal_distance_m)}, tank/lake ${m(w.nearest_tank_lake_distance_m)}` : null,
  ].filter(Boolean)
  if (terrainParts.length) lines.push({ mechanism: 'terrain_and_nearby_water', status: byMechanism.terrain_and_nearby_water?.status || 'assessed', text: `${terrainParts.join('; ')}.` })
  else if (byMechanism.terrain_and_nearby_water) lines.push({ mechanism: 'terrain_and_nearby_water', status: byMechanism.terrain_and_nearby_water.status, text: sentence(byMechanism.terrain_and_nearby_water.summary) })
  for (const mechanism of ['rainfall_waterlogging', 'coastal_flooding']) if (byMechanism[mechanism]) lines.push({ mechanism, status: byMechanism[mechanism].status, text: byMechanism[mechanism].status === 'not_assessed' ? 'No dataset integrated. Unknown, not safe.' : sentence(byMechanism[mechanism].summary) })
  return lines
}

function FloodPanel({ indicators, latitude }: { indicators?: FloodIndicators | null; latitude: number | null | undefined }) {
  if (!indicators?.components?.length) return null
  const river = indicators.river_flood
  const cellArea = river?.model_cell_area_m2 ?? (latitude == null ? null : (3 / 3600) * 111320 * Math.cos(latitude * Math.PI / 180) * (3 / 3600) * 110574)
  const parcelArea = river?.parcel_area_m2
  const cells = river?.model_cells_overlapping_parcel
  return <section className="flood-section"><div className="section-head"><div><div className="section-label">FLOOD EVIDENCE · RED FLAGS ONLY, NO FLOOD SCORE OR PRICE</div><h2>{floodHeadline(indicators)}</h2></div><span className="completeness">No overall flood score or safety percentage: mechanisms that are not assessed are unknown, not safe.</span></div>
    <table className="flood-glance"><tbody>{floodGlance(indicators).map(line => <tr key={line.mechanism}><th>{MECHANISM_LABEL[line.mechanism] || line.mechanism}</th><td><span className={`factor-badge ${line.status}`}>{STATUS_LABEL[line.status] || line.status}</span></td><td>{line.text}</td></tr>)}</tbody></table>
    <details className="flood-details"><summary>Scenarios, sources and method</summary>
      {river && river.scenarios?.length > 0 && <div className="flood-table-wrap"><table className="flood-table"><caption>Modelled river flooding by return period · {river.dataset} · {river.resolution}</caption><thead><tr><th>Scenario</th><th>Annual exceedance probability</th><th>Parcel flooded</th><th>Max depth</th><th>Mean depth</th><th>Parcel + {river.surroundings_m || 500} m flooded</th></tr></thead><tbody>{river.scenarios.map(s => <tr key={s.return_period_years}><td>1-in-{s.return_period_years} years</td><td>{aep(s.return_period_years)}</td><td>{s.flooded_area_m2 > 0 ? `${pct(s.flooded_share_of_parcel)} (${Math.round(s.flooded_area_m2).toLocaleString()} m²)` : 'none modelled'}</td><td>{s.max_depth_m == null ? '—' : `${s.max_depth_m} m`}</td><td>{s.mean_depth_m == null ? '—' : `${s.mean_depth_m} m`}</td><td>{pct(s.surroundings_flooded_share)}</td></tr>)}</tbody></table></div>}
      <ul className="method-notes">
        {river && <li><strong>Coverage.</strong> Hazard-map cells were read for {pct(river.assessed_share_of_parcel)} of the parcel{cells ? `: ${cells} model cell${cells === 1 ? '' : 's'}` : ''}{cellArea ? ` of about ${(cellArea / 10000).toFixed(1)} ha each` : ''}{parcelArea ? ` (the parcel is ${(parcelArea / 10000).toFixed(1)} ha)` : ''}. The results describe those ~90 m cells, not individual buildings or plots. The model covers river (fluvial) flooding on rivers with basins over ~500 km² only; “none modelled” means the model shows no river inundation in that cell, not that the land cannot flood (small streams, drains, rainfall and the coast are outside it).{river.permanent_water_area_m2 > 0 ? ` ${Math.round(river.permanent_water_area_m2)} m² of permanent water is excluded.` : ''}{river.quality_flagged_area_m2 > 0 ? ` ${Math.round(river.quality_flagged_area_m2)} m² lies in a provider-flagged area, where depths are withheld but the area still counts as flooded.` : ''}</li>}
        <li><strong>Probabilities.</strong> Annual exceedance probability is the chance, in any one year, of a river flood at least as large as the modelled scenario (1 ÷ return period). It is not the probability that this parcel floods, and it is not a promise about when the next such flood comes.</li>
        <li><strong>Surroundings.</strong> “Parcel + {river?.surroundings_m || 500} m” is the parcel together with the {river?.surroundings_m || 500} m ring around it, permanent water excluded; the surface-water figures use the same zone at 30 m.</li>
      </ul>
      <div className="flood-components">{indicators.components.map(c => <div className={`flood-component ${c.status}`} key={c.mechanism}><div className="flood-component-head"><strong>{MECHANISM_LABEL[c.mechanism] || c.mechanism}</strong><span className={`factor-badge ${c.status}`}>{STATUS_LABEL[c.status] || c.status}</span></div><p>{sentence(c.summary)}{cutOff(sentence(c.summary)) && <em className="cut-note"> … (this sentence was cut off when the report was saved; the figures above are complete)</em>}</p>{(c.source || c.period || c.resolution) && <small>{[c.source, c.period, c.resolution].filter(Boolean).join(' · ')}</small>}</div>)}</div>
    </details>
  </section>
}

const CLASS_LABEL: Record<string, string> = { built: 'built area', crops: 'crops', trees: 'trees', rangeland: 'rangeland', bare: 'bare ground', water: 'water', flooded_vegetation: 'flooded vegetation', snow_ice: 'snow / ice' }

/** "crops 2017–2021, then built area 2022–2023": the plot's own class each year, with runs collapsed. */
function plotStory(years: NonNullable<LandCoverHistory['parcel']>) {
  const runs: { cls: string; from: number; to: number }[] = []
  for (const y of years) {
    const last = runs[runs.length - 1]
    if (last && last.cls === y.dominant && last.to === y.year - 1) last.to = y.year
    else runs.push({ cls: y.dominant, from: y.year, to: y.year })
  }
  return runs.map(r => `${CLASS_LABEL[r.cls] || r.cls} ${r.from === r.to ? r.from : `${r.from}–${r.to}`}`).join(', then ')
}

/** What the buy / wait call rests on: red flags, the area's development history, and what TerraScope cannot check. */
function DecisionPanel({ record, growth }: { record: ParcelRecord; growth?: FactorAssessment }) {
  const history = record.land_cover_history
  const flags = record.verdict?.red_flags || []
  const checks = record.verdict?.pre_purchase_checks
  const share = (value: number | null) => value == null ? null : Number((value * 100).toFixed(1))
  const data = (history?.surroundings || []).map(r => ({ year: String(r.year), near: share(r.built_share_within_1km), far: share(r.built_share_1_to_3km) }))
  const headline = growth && ['indicative', 'built_out'].includes(growth.status) ? growth.basis.split(':')[0] : 'No area history in this report'
  return <section className="decision-section">
    <div>
      <div className="section-label">AREA HISTORY · WHAT THE BUY / WAIT CALL RESTS ON</div>
      <h2>{headline}</h2>
      {flags.length > 0 && <div className="red-flags" role="alert"><strong><TriangleAlert size={14} /> Red flags: don’t buy unless these are explained</strong><ul>{flags.map(flag => <li key={flag}>{flag}</li>)}</ul></div>}
      {data.length > 1 ? <div className="chart-wrap history-chart"><ResponsiveContainer width="100%" height={210}><LineChart data={data}><CartesianGrid stroke="#25313a" vertical={false} /><XAxis dataKey="year" stroke="#71808b" tickLine={false} axisLine={false} /><YAxis domain={[0, 100]} stroke="#71808b" tickLine={false} axisLine={false} unit="%" width={44} /><Tooltip contentStyle={{ background: '#11191d', border: '1px solid #2d3b42' }} formatter={value => `${value}%`} /><Line type="monotone" dataKey="near" stroke="#b8f36a" strokeWidth={2} dot={{ r: 3 }} name="Built up within 1 km" connectNulls={false} /><Line type="monotone" dataKey="far" stroke="#77d8ff" strokeWidth={2} dot={{ r: 3 }} name="Built up 1–3 km away" connectNulls={false} /></LineChart></ResponsiveContainer></div>
        : <p className="muted">{history ? `Area history unavailable: ${history.error || 'too few years were classified around the plot.'}` : 'This report was made before TerraScope read the area history. Analyse the same boundary again to add it.'}</p>}
      {data.length > 1 && <p className="history-legend"><span><i className="dot near" /> built up within 1 km of the plot</span><span><i className="dot far" /> 1–3 km away</span></p>}
      {history?.parcel?.length ? <p className="muted window-note"><strong>The plot itself:</strong> {plotStory(history.parcel)}.</p> : null}
      {data.length > 1 && <p className="muted window-note">{history?.dataset || 'Annual land cover'}, 10 m, one map a year. A modelled classification: a single year can be off, so the decision uses the trend over every year. It shows building on the ground, not prices or approvals.</p>}
    </div>
    <div>
      <div className="section-label">BEFORE YOU PAY</div>
      {checks == null ? <p className="muted">This evaluation predates the checklist. Re-evaluate the report to list it.</p> : checks.length ? <ul className="checklist">{checks.map(check => <li key={check}>{check}</li>)}</ul> : <p className="muted">Nothing outstanding.</p>}
      <p className="field-hint">TerraScope cannot read land records, so title, encumbrance and approvals are never verified here. Get them from the sub-registrar office and the seller.</p>
    </div>
  </section>
}

const ASSESSMENT_LABEL: Record<Finding['assessment'], string> = { red_flag: 'Red flag', caution: 'Caution', ok: 'OK', unknown: 'Unknown' }
const BASIS_LABEL: Record<Finding['basis'], string> = { measured: 'measured', modelled: 'model scenario', user_provided: 'your claim, not verified', not_verified: 'not verified', unavailable: 'source unavailable' }

/** The price result the report already holds, as one more row: shown, never computed here. */
function priceFinding(valuation: Valuation | null): Finding {
  if (valuation?.status === 'available') return { area: 'Land price', finding: `Typical ₹${inr(valuation.estimate_inr_per_sqft)} per sq ft from ${valuation.comparable_count} ${valuation.price_type_label}, ${valuation.observed_from} to ${valuation.observed_to}. ${valuation.validation.status === 'validated' ? '' : 'Accuracy not yet validated.'}`.trim(), assessment: 'ok', basis: 'measured', source: valuation.sources.join(', '), as_of: valuation.valuation_date, next_step: 'Compare the asking price with this range and with the government guideline value.' }
  return { area: 'Land price', finding: valuation ? (NO_PRICE_REASON[valuation.reason] || valuation.detail) : 'No price estimate was run.', assessment: 'unknown', basis: 'unavailable', source: 'No permitted price data loaded', next_step: 'Check the government guideline value at the sub-registrar office (Tamil Nadu: tnreginet.gov.in) and ask the seller for recent sale deeds nearby.' }
}

function FindingsTable({ findings, valuation }: { findings?: Finding[] | null; valuation: Valuation | null }) {
  if (!findings?.length) return <section className="findings-section"><div className="section-label">WHAT WE FOUND</div><p className="muted">This evaluation predates the findings list. Use “Re-evaluate with current methods” above to add it.</p></section>
  const rows = [...findings, priceFinding(valuation)]
  const counts = rows.reduce<Record<string, number>>((n, f) => ({ ...n, [f.assessment]: (n[f.assessment] || 0) + 1 }), {})
  return <section className="findings-section">
    <div className="section-head"><div><div className="section-label">WHAT WE FOUND · EVERY CHECK, ITS SOURCE AND YOUR NEXT STEP</div><h2>{counts.red_flag ? `${counts.red_flag} red flag${counts.red_flag > 1 ? 's' : ''}` : 'No red flags'}{counts.caution ? `, ${counts.caution} to check` : ''}{counts.unknown ? `, ${counts.unknown} not verifiable here` : ''}</h2></div></div>
    <div className="finding-list">{rows.map(f => <div className={`finding ${f.assessment}`} key={f.area}>
      <div className="finding-what"><strong>{f.area}</strong><span className={`finding-badge ${f.assessment}`}>{ASSESSMENT_LABEL[f.assessment]}</span></div>
      <div className="finding-body"><p>{f.finding}</p><small>{BASIS_LABEL[f.basis]}{f.source ? ` · ${f.source}` : ''}{f.as_of ? ` · as of ${f.as_of}` : ''}</small></div>
      <div className="finding-next"><span>NEXT STEP</span><p>{f.next_step}</p></div>
    </div>)}</div>
  </section>
}

function Bar({ label, value, color, status }: { label: string; value: number | null; color: string; status?: string }) {
  const available = typeof value === 'number'
  return <div className={`score-line${available ? '' : ' unassessed'}`}>
    <div><span>{label}</span><strong>{available ? value : status === 'partial' ? 'Partly assessed' : 'Not scored'}</strong></div>
    <div className="bar"><i style={{ width: available ? `${Math.max(0, Math.min(100, value))}%` : '0%', background: color }} /></div>
    {status && status !== 'assessed' && <small className="score-status">{status === 'indicative' ? 'indicative only' : status === 'partial' ? 'evidence shown · not scored' : status === 'built_out' ? 'already built out · not scored' : 'no supporting evidence'}</small>}
  </div>
}

function EvidenceRow({ title, refName, freshness, summary, observedAt, details }: { title: string; refName: string; freshness: string; summary: string; observedAt?: string | null; details?: string }) {
  return <div className="evidence-row"><div className="evidence-icon"><FileText size={16} /></div><div><strong>{title}</strong><p>{summary}{cutOff(summary) && <em className="cut-note"> … (cut off when this report was saved)</em>}</p><small>{refName} · {(observedAt || '').slice(0, 10) || 'date unavailable'}</small>{details && <small className="evidence-details">{details}</small>}</div><span className={`freshness ${freshness}`}>{freshness.replace('_', ' ')}</span></div>
}

const inr = (value: number) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(Math.round(value))
function compactInr(value: number) {
  // Indian scale: beyond a lakh crore, "13,684 Cr" stops being readable.
  if (value >= 1e12) return `₹${(value / 1e12).toFixed(2)} Lakh Cr`
  if (value >= 1e7) return `₹${(value / 1e7).toFixed(2)} Cr`
  if (value >= 1e5) return `₹${(value / 1e5).toFixed(2)} L`
  return `₹${inr(value)}`
}

/** One reason and one next step; the specific backend detail is used when it carries numbers. */
const NO_PRICE_REASON: Record<string, string> = {
  no_price_data: 'No permitted land-price observations are loaded yet, for this or any area.',
  request_failed: 'The valuation service could not be reached.',
}
const NEXT_ACTION: Record<string, string> = {
  no_price_data: 'Import an owner/broker or licensed price CSV from “Price data” on the start page. A sale-based range needs at least 5 vacant plots of similar size (one third to three times this parcel) within 10 km.',
  insufficient_comparables: 'Import more vacant-plot prices of similar size near this parcel.',
  area_outside_support: 'Prices of much smaller plots do not transfer to a parcel this size; it needs comparables of similar size.',
  no_comparables_nearby: 'Import prices for plots within 10 km of this parcel.',
  stale_data_only: 'Import recent prices for this area.',
  price_type_not_covered: 'Choose a price basis that has data, or import that type.',
  land_use_not_covered: 'Import prices for this land use, or choose the land use that matches the data.',
}
const PRICE_TITLE: Record<string, string> = { asking: 'Listing-based estimated price range', transaction: 'Sale-based estimated price range', guideline: 'Government guideline value (reference)' }

function ValuationSection({ valuation, property, record }: { valuation: Valuation | null; property: PropertyDetails | null; record: ParcelRecord }) {
  const [current, setCurrent] = useState(valuation)
  const [basis, setBasis] = useState<PriceBasis>(property?.price_basis || 'asking')
  async function switchBasis(next: PriceBasis) {
    setBasis(next)
    const area = property?.area_sqft_override ?? ((record.geometry_metadata?.area_m2 ?? 0) * 10.763910416709722)
    if (record.location?.latitude == null || record.location?.longitude == null || !area) return
    try { setCurrent(await estimateValuation({ latitude: record.location.latitude, longitude: record.location.longitude, area_sqft: area, land_use: property?.land_use || 'residential', price_basis: next })) }
    catch (error) { setCurrent({ status: 'unavailable', reason: 'request_failed', detail: error instanceof Error ? error.message : 'The valuation service could not be reached.' }) }
  }
  const picker = <label className="basis-picker">Compare against <select value={basis} onChange={e => switchBasis(e.target.value as PriceBasis)}><option value="asking">asking prices (listings)</option><option value="transaction">registered sale prices</option><option value="guideline">government guideline values</option></select></label>
  valuation = current
  const label = <div className="section-label"><IndianRupee size={13} /> LAND PRICE · KEPT SEPARATE FROM LEGAL, FLOOD AND SUITABILITY</div>
  if (!valuation) return <section className="valuation-section unavailable">{label}<h2>Not requested</h2><p className="muted">No price estimate was run: it needs a location and a plot area.</p></section>
  if (valuation.status === 'unavailable') {
    return <section className="valuation-section unavailable">{label}<h2>No price estimate</h2>{picker}<p className="valuation-reason">{NO_PRICE_REASON[valuation.reason] || valuation.detail}</p>{NEXT_ACTION[valuation.reason] && <p className="muted valuation-detail"><strong>Next:</strong> {NEXT_ACTION[valuation.reason]}</p>}</section>
  }
  const spread = valuation.spread_inr_per_sqft
  const validated = valuation.validation.status === 'validated'
  return <section className="valuation-section">
    <div className="section-head"><div>{label}<h2>{PRICE_TITLE[valuation.price_type] || 'Estimated price range'}</h2></div><span className={`valuation-stamp${validated ? '' : ' unvalidated'}`}>{validated ? 'held-out accuracy measured' : 'NOT YET VALIDATED'} · data {valuation.data_version} · {valuation.valuation_date}</span></div>
    {picker}<p className="valuation-basis">Based on <strong>{valuation.price_type_label}</strong>.{valuation.price_type === 'asking' ? ' These are not completed sale prices.' : ''}</p>
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
    <details className="valuation-comparables" open><summary>Comparable properties behind this estimate ({valuation.comparables.length} shown)</summary><table className="flood-table"><thead><tr><th>Source / record</th><th>Type</th><th>Observed</th><th>₹ / sq ft</th><th>Area (sq ft)</th><th>Distance</th><th>Location</th></tr></thead><tbody>{valuation.comparables.map(c => <tr key={`${c.source}-${c.source_record_id}`}><td>{c.source_url ? <a href={c.source_url} target="_blank" rel="noreferrer">{c.source} · {c.source_record_id}</a> : `${c.source} · ${c.source_record_id}`}{c.listed_by_sources > 1 ? ` (listed ${c.listed_by_sources}×, counted once)` : ''}<small className="comparable-basis">reuse: {c.reuse_basis} · retrieved {c.retrieved_date}</small></td><td>{c.price_type}</td><td>{c.observed_date}</td><td>₹{inr(c.price_inr_per_sqft)}</td><td>{c.area_sqft == null ? '—' : inr(c.area_sqft)}</td><td>{c.distance_km} km</td><td>{c.location_precision}{c.locality ? ` · ${c.locality}` : ''}</td></tr>)}</tbody></table></details>
    <p className="valuation-foot">The price comes only from comparable prices and the property details you entered. It never uses your suitability weights, accessibility limits, flood evidence or legal status, and none of those use it.</p>
  </section>
}

function AccessibilityDetails({ factor }: { factor: FactorAssessment }) {
  const d = factor.details
  if (!d?.road) return null
  return <div className="flood-table-wrap"><table className="flood-table access-table"><thead><tr><th>Feature</th><th>Straight-line distance</th><th>Measured from</th><th>Your limit</th><th>Sub-score</th><th>Weight</th></tr></thead><tbody>{([['Road', d.road], ['School', d.school]] as const).map(([name, part]) => <tr key={name}><td>{name}</td><td>{part.distance_m == null ? '—' : m(part.distance_m)}{part.measured_from === 'parcel boundary' && part.centroid_distance_m != null ? ` (${m(part.centroid_distance_m)} from centroid)` : ''}</td><td>{part.measured_from}</td><td>{m(part.cap_m)}</td><td>{part.sub_score == null ? 'left out' : Math.round(part.sub_score)}</td><td>×{part.weight}</td></tr>)}</tbody></table></div>
}

function LegalEvidence({ record, onChanged }: { record: ParcelRecord; onChanged: () => Promise<void> }) {
  const supplied = record.user_land_details
  const [form, setForm] = useState<LandDetails>({ state: supplied?.state ?? record.location?.state ?? '', district: supplied?.district ?? record.location?.district ?? '', taluk: supplied?.taluk ?? '', village: supplied?.village ?? record.location?.village ?? '', survey_number: supplied?.survey_number ?? '', subdivision: supplied?.subdivision ?? '' })
  const [file, setFile] = useState<File | null>(null)
  const [docType, setDocType] = useState<DocType>('encumbrance_certificate')
  const [status, setStatus] = useState('')
  async function save() {
    setStatus('Saving…')
    try {
      const clean = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, (value || '').trim() || null]).filter(([, value]) => value))
      await saveLandDetails(record.parcel_id || '', clean)
      if (file) { await uploadEvidence(record.parcel_id || '', file, docType); setFile(null) }
      await onChanged()
      setStatus('Saved and re-evaluated. These remain your claims, not a verified record.')
    } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not save.') }
  }
  const fields: [keyof LandDetails, string][] = [['state', 'State'], ['district', 'District'], ['taluk', 'Taluk / mandal'], ['village', 'Village'], ['survey_number', 'Survey no.'], ['subdivision', 'Subdivision']]
  return <div className="land-evidence">
    <div className="field-label">SURVEY DETAILS AND DOCUMENTS <span>yours · not verified</span></div>
    <div className="land-grid">{fields.map(([key, label]) => <label className="stacked-field" key={key}>{label}<input value={form[key] || ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} /></label>)}</div>
    {supplied?.documents?.length ? <ul className="doc-list">{supplied.documents.map(doc => <li key={doc.filename}><strong>{doc.filename}</strong> · {doc.doc_type ? DOC_TYPE_LABEL[doc.doc_type] : 'type not given'} · {doc.text_extracted ? `${doc.pages ? `${doc.pages} pages, ` : ''}text extracted` : 'no text extracted (scanned?)'}{doc.mentions?.length ? ` · ${doc.mentions.map(mm => `${mm.field.replace('_', ' ')} ${mm.value}${mm.pages ? ` on page ${mm.pages.join(', ')}` : ''}`).join('; ')}` : (form.survey_number ? ' · your survey number was not found in it' : '')}</li>)}</ul> : null}
    <div className="land-upload"><label className="upload-row"><input type="file" accept=".pdf,.txt,application/pdf,text/plain" onChange={e => setFile(e.target.files?.[0] || null)} /><Upload size={14} /><span>{file ? file.name : 'Add a document (PDF or TXT)'}</span></label><select value={docType} onChange={e => setDocType(e.target.value as DocType)}>{(Object.keys(DOC_TYPE_LABEL) as DocType[]).map(type => <option key={type} value={type}>{DOC_TYPE_LABEL[type]}</option>)}</select><button className="quiet-button" onClick={save}>Save and re-evaluate</button></div>
    <p className="field-hint">State, district and village are needed: survey numbers repeat across villages. TerraScope shows where your survey number and village appear in your documents (by page). That is never title verification.</p>
    {status && <p className="muted" role="status">{status}</p>}
  </div>
}

function ChangeSummary({ record, observations }: { record: ParcelRecord; observations: number }) {
  const sat = record.satellite
  const method = sat?.change_method
  if (!sat?.change_type) return <div className="signal-summary"><strong>unavailable</strong><span>{observations} usable observations</span></div>
  if (!method) {
    // statistical_change_v1 (before 2026-10-12): a straight line through all dates; the stored figure was half its mean R².
    return <div className="signal-summary"><strong>{sat.change_type === 'insufficient_evidence' ? 'too few observations' : 'no clear trend (v1 method)'}</strong><span>{sat.change_confidence == null ? '' : `stored “${Math.round(sat.change_confidence * 100)}%” was an uncalibrated trend-fit figure, not confidence · `}{observations} observations · seasons not compared</span></div>
  }
  return <div className="signal-summary"><strong>{CHANGE_LABEL[sat.change_type] || sat.change_type}</strong><span>{method.pairs} same-season pair{method.pairs === 1 ? '' : 's'} a year apart · {observations} observations · no confidence % (rule thresholds, not calibrated)</span></div>
}

export function Report({ initialSnapshot, initialSettings, valuation, property, onBack }: { initialSnapshot: ParcelRecord; initialSettings: EvaluationSettings; valuation: Valuation | null; property: PropertyDetails | null; onBack: () => void }) {
  const [record, setRecord] = useState(initialSnapshot)
  const [settings, setSettings] = useState(initialSettings)
  const [scenario, setScenario] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<{ profile: string; changed: string; verdict: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [activeEvidenceTab, setActiveEvidenceTab] = useState<EvidenceTab>('Satellite')
  const [scenarioError, setScenarioError] = useState('')

  const chart = useMemo(() => {
    const ndvi = record.satellite?.ndvi_trend || []
    const ndbi = record.satellite?.ndbi_trend || []
    return ndvi.map((point, index) => ({ date: point.date || '—', ndvi: point.value, ndbi: ndbi[index]?.value ?? null })).filter(point => point.ndvi !== null || point.ndbi !== null)
  }, [record])
  const breakdown = record.score_breakdown
  const factors = breakdown?.factors || []
  const factorOf = (name: string) => factors.find(f => f.factor === name)
  const verdict = record.verdict?.recommendation || 'UNAVAILABLE'
  const evidence = record.evidence || []
  const assessedWeight = Math.round(breakdown?.assessed_weight_pct ?? 0)
  const insufficient = verdict === 'INSUFFICIENT_EVIDENCE'
  const scored = factors.filter(f => f.score != null)
  const unscored = factors.filter(f => f.score == null && f.weight_pct > 0)
  const satelliteIsDemo = evidence.some(item => (item.source_type || '') === 'satellite' && /synthetic/i.test(`${item.source_reference || ''} ${item.title || ''}`))
  const tabMatch: Record<EvidenceTab, string[]> = { Satellite: ['satellite', 'land_cover'], Infrastructure: ['openstreetmap', 'infrastructure'], 'Flood indicators': ['jrc_gsw', 'jrc_flood_hazard', 'copernicus_dem', 'osm_water', 'open_elevation', 'elevation'], RERA: ['maharera_seed', 'rera'], 'Uploaded Documents': ['document', 'user_upload'], 'Derived Scores': ['derived'] }
  const visibleEvidence = evidence.filter(item => tabMatch[activeEvidenceTab].some(type => (item.source_type || '').toLowerCase().includes(type)))
  const fields = record.metadata.data_completeness_fields
  const fieldCount = fields ? Object.keys(fields).length : 12
  const collectedCount = fields ? Object.values(fields).filter(Boolean).length : Math.round(((record.metadata.data_completeness_pct ?? 0) / 100) * 12)
  const isAi = record.verdict?.explanation_source === 'ai'
  const olderEvaluation = record.score_breakdown != null && (record.verdict?.explanation_source == null || record.verdict?.findings == null)
  const citations = record.verdict?.citations || []
  const imagery = (record.satellite?.imagery_dates || []).filter(Boolean) as string[]
  const windowStart = record.metadata.analysis_date_from
  const lateStart = imagery.length && windowStart && !record.satellite?.collection && (Date.parse(imagery[0]) - Date.parse(windowStart)) > 90 * 864e5
  const address = record.location?.address

  async function rerun(next: EvaluationSettings, changed?: string) {
    setBusy(true)
    setScenarioError('')
    try {
      const result = await evaluateParcel(record.parcel_id || '', next, record.metadata.analysis_snapshot_id || '')
      setRecord(result)
      setSettings(next)  // only once it worked: a failed run must leave the settings the report shows, so Apply can retry
      setHistory(items => [{ profile: next.profile, changed: changed || 'Re-evaluated with current methods', verdict: result.verdict?.recommendation || 'UNAVAILABLE' }, ...items])
      setScenario(false)
    } catch (error) {
      setScenarioError(error instanceof Error ? error.message : 'Scenario evaluation failed.')
      throw error
    } finally {
      setBusy(false)
    }
  }

  return <main className="report-shell">
    <header className="report-topbar"><button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Workspace</button><div className="wordmark"><span className="mark"><Sparkles size={14} /></span> TERRASCOPE</div><div className="report-tools"><button className="quiet-button" onClick={() => setHistoryOpen(true)}><History size={15} /> Scenario history</button><button className="quiet-button" onClick={() => setScenario(true)}><FlaskConical size={15} /> Explore scenarios</button><button className="quiet-button" onClick={() => window.print()}><Printer size={15} /> Print</button></div></header>
    <div className="report-content">
      <section className="report-heading"><div><div className="eyebrow"><span className="pulse" /> ANALYSIS SNAPSHOT · {(record.metadata.analysis_snapshot_id || '—').slice(0, 8)}</div><h1>{placeName(address)}</h1>{address && <p className="full-address">{address}</p>}<p>{record.geometry_metadata?.area_acres == null ? 'Area unavailable' : `${record.geometry_metadata.area_acres.toFixed(2)} acres`} <span>·</span> {record.metadata.analysis_date_from || '—'} — {record.metadata.analysis_date_to || '—'}</p></div><div className={`verdict-badge ${verdict.toLowerCase()}`}><span>BUY NOW OR WAIT?</span><strong>{insufficient ? 'NO DECISION YET' : verdict}</strong><small>{!record.verdict ? 'not evaluated yet' : insufficient ? 'see what is missing below' : record.verdict.red_flags?.length ? 'red flags in the plot’s history' : 'rule-based · check title before paying'}</small></div></section>
      {olderEvaluation && <div className="older-note" role="note"><TriangleAlert size={15} /><span>This saved evaluation was made with an earlier version of TerraScope, so it lacks the current checks (the findings list and the buy / wait rules). Re-evaluating uses the same evidence; nothing is collected again.</span><button className="quiet-button" disabled={busy} onClick={() => rerun(settings).catch(() => undefined)}><RefreshCw size={14} /> {busy ? 'Re-evaluating…' : 'Re-evaluate with current methods'}</button></div>}
      {scenarioError && !scenario && <div className="older-note error-note" role="alert"><TriangleAlert size={15} /><span>{scenarioError}</span></div>}
      <DecisionPanel record={record} growth={factorOf('growth')} />
      <FindingsTable findings={record.verdict?.findings} valuation={valuation} />
      <ValuationSection valuation={valuation} property={property} record={record} />
      <div className="section-label suitability-divider">SUITABILITY FOR YOU — scored from your weights, independent of the market price above</div>
      <section className="score-strip"><Bar label="Legal Safety" value={breakdown?.legal_safety_score ?? null} color="#77d8ff" status={factorOf('legal_safety')?.status} /><Bar label="Accessibility" value={breakdown?.accessibility_score ?? null} color="#f8c15c" status={factorOf('accessibility')?.status} /><Bar label="Flood Safety" value={breakdown?.flood_safety_score ?? null} color="#d49aff" status={factorOf('flood_safety')?.status} /><Bar label="Area growth" value={breakdown?.growth_score ?? null} color="#b8f36a" status={factorOf('growth')?.status} /></section>
      <section className="evidence-status"><div className="section-head"><div><div className="section-label">EVIDENCE BEHIND EACH FACTOR</div><h2>What is measured, and what is scored</h2></div></div>
        <div className="coverage-figures"><div><span>SCORED</span><strong>{assessedWeight}%</strong><small>of your weighting has a score{scored.length ? ` (${scored.map(f => FACTOR_LABEL[f.factor] || f.factor).join(', ')})` : ''}</small></div><div><span>MEASURED</span><strong>{collectedCount} of {fieldCount}</strong><small>evidence fields collected for this parcel</small></div></div>
        <details className="denominators"><summary>How these two figures are counted</summary><p><strong>Scored</strong> adds up the weights of factors that have a score. {unscored.length ? `${unscored.map(f => `${FACTOR_LABEL[f.factor] || f.factor} (${f.weight_pct}%)`).join(', ')} ${unscored.length === 1 ? 'has' : 'have'} no score and ${unscored.length === 1 ? 'is' : 'are'} never filled in with 50. The composite is shared over the scored factors only. Unscored legal safety becomes the checks before you pay, and flood history can raise red flags. An unscored location factor (area growth, accessibility) withholds the decision.` : 'Every weighted factor has a score.'}</p><p><strong>Measured</strong> counts the evidence fields TerraScope tries to collect for every parcel ({record.metadata.data_completeness_pct ?? '—'}%). A field can be collected without being enough to score a factor: flood evidence is measured but not combined into a score.</p>{fields && <ul className="field-checks">{Object.entries(fields).map(([key, ok]) => <li key={key} className={ok ? 'ok' : 'missing'}>{ok ? '✓' : '—'} {COMPLETENESS_LABEL[key] || key}</li>)}</ul>}</details>
        <div className="factor-list">{[...factors].sort((a, b) => Number(b.score != null) - Number(a.score != null)).map(f => <div className={`factor ${f.status}`} key={f.factor}><div className="factor-head"><strong>{FACTOR_LABEL[f.factor] || f.factor.replace(/_/g, ' ')}</strong><span className={`factor-badge ${f.status}`}>{f.score == null ? (f.status === 'partial' ? 'partly assessed · not scored' : f.status.replace(/_/g, ' ')) : `${f.score} · ${f.status}`}</span><em>{f.weight_pct}% weight</em></div>
          <p>{f.factor === 'flood_safety' && record.flood_indicators?.components?.length ? `${floodHeadline(record.flood_indicators)}. The measurements are in the flood section below.` : f.basis}</p>
          {f.factor === 'accessibility' && <AccessibilityDetails factor={f} />}
          <small>{f.factor === 'flood_safety' ? 'No overall Flood Safety score: no validated method combines the mechanisms.' : f.limitations}</small>
          {f.checklist && f.checklist.length > 0 && <ul className="checklist">{f.checklist.map(c => <li key={c}>{c}</li>)}</ul>}
          {f.factor === 'legal_safety' && record.parcel_id && <LegalEvidence record={record} onChanged={() => rerun(settings, 'Survey details or documents updated')} />}
        </div>)}</div>
      </section>
      <FloodPanel indicators={record.flood_indicators} latitude={record.location?.latitude} />
      <section className="why-grid"><div><div className="section-label">WHY THIS RECOMMENDATION?</div><h2>Scored contributions</h2><div className="contribution-list">{(breakdown?.weighted_contributions || []).map((item, index) => <div key={index}><span>{FACTOR_LABEL[item.factor || ''] || item.factor || 'Unnamed factor'}</span><strong className={(item.contribution || 0) < 0 ? 'negative' : ''}>{(item.contribution || 0) > 0 ? '+' : ''}{item.contribution ?? '—'}</strong></div>)}{unscored.map(f => <div key={f.factor} className="unscored-row"><span>{FACTOR_LABEL[f.factor] || f.factor}</span><strong>no score · {f.weight_pct}%</strong></div>)}</div>{breakdown?.composite_score != null && <div className="final-verdict"><span>COMPOSITE</span><b>{breakdown.composite_score}</b></div>}</div>
        <div className="grounded-box"><div className="section-label">{isAi ? <><Sparkles size={13} /> AI EXPLANATION</> : 'ASSESSMENT SUMMARY · RULE-BASED, NOT AI'}</div><p>{record.verdict?.reasoning_summary || 'No summary was returned for this evaluation.'}</p>
          <div className="citation-row"><span>{citations.length ? `${citations.length} evidence reference${citations.length === 1 ? '' : 's'}` : olderEvaluation ? 'No evidence references in this older evaluation; re-evaluate to add them' : 'No figure here needs a reference'}</span></div>
          {citations.length > 0 && <div className="citation-list">{citations.map((citation, index) => <div key={index}><strong>{citation.claim}</strong><small>{citation.source_type === 'user_upload' ? 'your document' : citation.source_type} · {citation.source_reference}{citation.location ? ` · ${citation.location}` : ''}</small></div>)}</div>}
        </div></section>
      <section className={`satellite-section${satelliteIsDemo ? ' synthetic' : ''}`}>{satelliteIsDemo && <div className="demo-banner"><TriangleAlert size={15} /> <strong>DEMO DATA.</strong> This curve is invented to exercise the chart. It is not imagery and shows nothing about real vegetation or construction.</div>}<div className="section-head"><div><div className="section-label">SATELLITE SIGNAL · LAND COVER, NOT INVESTMENT GROWTH</div><h2>Change over time</h2></div>{satelliteIsDemo ? <div className="signal-summary"><strong>demo series</strong><span>no figure: series is invented</span></div> : <ChangeSummary record={record} observations={chart.length} />}</div>{chart.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={250}><LineChart data={chart}><CartesianGrid stroke="#25313a" vertical={false} /><XAxis dataKey="date" stroke="#71808b" tickLine={false} axisLine={false} tickFormatter={(value: string) => value.slice(0, 7)} /><YAxis stroke="#71808b" tickLine={false} axisLine={false} /><Tooltip contentStyle={{ background: '#11191d', border: '1px solid #2d3b42' }} /><Line type="monotone" dataKey="ndvi" stroke="#b8f36a" strokeWidth={2} dot={{ r: 3 }} name="NDVI" connectNulls={false} /><Line type="monotone" dataKey="ndbi" stroke="#f8c15c" strokeWidth={2} dot={{ r: 3 }} name="NDBI" connectNulls={false} /></LineChart></ResponsiveContainer></div> : <div className="chart-empty">{record.satellite?.collection?.status === 'timed_out' ? `Satellite collection did not finish within the ${record.satellite.collection.deadline_s ?? 35} s evidence deadline. The scene reads continue in the background and are cached: analyse this boundary again in a minute or two to reuse them.` : 'No usable satellite observations were found for this parcel and date range.'}</div>}
        <div className="signal-foot"><span>{record.satellite?.change_method ? record.satellite.change_method.reason : record.satellite?.change_type ? 'Classified by the superseded v1 method, which fitted one straight line through all seasons and filed unclear movement under “no change”. Re-run the analysis for the seasonal comparison.' : 'Satellite signal unavailable.'}</span><span>Analysis period · {record.metadata.analysis_date_from || '—'} to {record.metadata.analysis_date_to || '—'}</span></div>
        {lateStart ? <p className="muted window-note">The first usable image is {imagery[0]}, months after the window starts ({windowStart}): the scene search used for this report stopped at the newest 100 catalogue entries. New analyses read the whole catalogue.</p> : null}
        {record.satellite?.collection?.selection && <p className="muted window-note">{record.satellite.collection.selection}; {record.satellite.collection.scenes_matched} scenes matched under {record.satellite.collection.max_cloud_cover_pct ?? 35}% cloud, {record.satellite.collection.observations_rejected ?? 0} read but rejected (under {Math.round((record.satellite.collection.min_clear_fraction ?? 0.5) * 100)}% of the parcel cloud-free){record.satellite.collection.anchors_without_observation?.length ? `; no usable scene near ${record.satellite.collection.anchors_without_observation.length} season anchor(s)` : ''}. Method {record.satellite.collection.algorithm_version}.</p>}
      </section>
      <section className="evidence-section"><div className="section-head"><div><div className="section-label">EVIDENCE LEDGER</div><h2>Sources behind the findings</h2></div></div><div className="tabs">{(['Satellite', 'Infrastructure', 'Flood indicators', 'RERA', 'Uploaded Documents', 'Derived Scores'] as EvidenceTab[]).map(tab => <button className={tab === activeEvidenceTab ? 'active' : ''} key={tab} onClick={() => setActiveEvidenceTab(tab)}>{tab}</button>)}</div><div className="source-legend ledger-legend"><span><i className="dot live" /> LIVE</span><span><i className="dot cached" /> CACHED</span><span><i className="dot user_upload" /> YOUR UPLOAD</span><span><i className="dot derived" /> DERIVED</span><span><i className="dot seed" /> SEED DATA</span></div>{visibleEvidence.length ? visibleEvidence.map(item => <EvidenceRow key={item.evidence_id || item.title} title={item.title || item.source_type || 'Evidence'} refName={item.source_reference || 'TerraScope'} freshness={item.freshness || 'derived'} summary={item.summary || 'Collected evidence used in the evaluation.'} observedAt={item.observed_at} details={[item.observation_period && `observed ${item.observation_period}`, item.resolution, item.licence].filter(Boolean).join(' · ')} />) : <p className="muted evidence-empty">No {activeEvidenceTab.toLowerCase()} evidence is available for this parcel.</p>}</section>
    </div>
    {scenario && <Scenario settings={settings} verdict={verdict} before={breakdown?.composite_score ?? null} accessibility={breakdown?.accessibility_score ?? null} busy={busy} error={scenarioError} onClose={() => setScenario(false)} onRun={(next, changed) => rerun(next, changed).catch(() => undefined)} />}
    {historyOpen && <div className="drawer-backdrop" onClick={() => setHistoryOpen(false)}><aside className="history-drawer" onClick={event => event.stopPropagation()}><div className="drawer-header"><div><div className="panel-kicker">DECISION TRAIL</div><h2>Scenario history</h2></div><button className="icon-button" aria-label="Close" onClick={() => setHistoryOpen(false)}><X size={18} /></button></div><div className="history-list">{history.length ? history.map((item, index) => <div className="history-item" key={index}><div><strong>{item.profile}</strong><span>{item.changed}</span></div><b>{item.verdict}</b></div>) : <p className="muted">No alternate lenses explored yet. The immutable evidence stays fixed while you test assumptions.</p>}</div></aside></div>}
  </main>
}

function Scenario({ settings, verdict, before, accessibility, onClose, onRun, busy, error }: { settings: EvaluationSettings; verdict: string; before: number | null; accessibility: number | null; onClose: () => void; onRun: (settings: EvaluationSettings, changed: string) => void; busy: boolean; error: string }) {
  const [local, setLocal] = useState(settings)
  const flood = local.weights.flood_safety_pct
  const maxFlood = Math.max(0, 100 - local.weights.legal_safety_pct - local.weights.accessibility_pct)
  const change = (value: number) => setLocal(current => ({ ...current, weights: { ...current.weights, flood_safety_pct: value, growth_pct: 100 - value - current.weights.legal_safety_pct - current.weights.accessibility_pct } }))
  const pref = <K extends keyof EvaluationSettings['preferences']>(key: K, value: EvaluationSettings['preferences'][K]) => setLocal(current => ({ ...current, preferences: { ...current.preferences, [key]: value } }))
  const p = local.preferences, s = settings.preferences
  const changed = [
    flood !== settings.weights.flood_safety_pct && `Flood Safety weight ${flood}%`,
    p.max_road_distance_m !== s.max_road_distance_m && `road limit ${p.max_road_distance_m} m`,
    p.max_school_distance_m !== s.max_school_distance_m && `school limit ${p.max_school_distance_m} m`,
    p.road_importance !== s.road_importance && `road importance ${p.road_importance}`,
    p.school_importance !== s.school_importance && `school importance ${p.school_importance}`,
  ].filter(Boolean).join(', ') || 'no change'
  return <div className="drawer-backdrop" onClick={onClose}><aside className="scenario-drawer" onClick={event => event.stopPropagation()}><div className="drawer-header"><div><div className="panel-kicker">SCENARIO MODE</div><h2>Explore scenarios</h2></div><button className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button></div><div className="drawer-scroll"><p className="drawer-intro flush">Change an assumption and re-evaluate the same evidence. Nothing is collected again, and the land price does not change.</p><div className="scenario-score flush"><div><span>BEFORE</span><strong>{verdict === 'INSUFFICIENT_EVIDENCE' ? 'INSUFFICIENT EVIDENCE' : verdict} · {before ?? '—'}</strong></div><div><span>ACCESSIBILITY</span><strong>{accessibility ?? '—'}</strong></div></div>
    <label className="field-label">FLOOD SAFETY WEIGHT <strong>{flood}%</strong></label><input className="scenario-range flush" aria-label="Flood safety weight (percent)" type="range" min="0" max={maxFlood} value={Math.min(flood, maxFlood)} onChange={event => change(Number(event.target.value))} />
    <label className="field-label">ACCESSIBILITY LIMITS <span>score reaches 0 at the limit</span></label>
    <div className="slider-row"><span>Road within</span><strong>{p.max_road_distance_m.toLocaleString()} m</strong><input type="range" min="100" max="5000" step="100" value={p.max_road_distance_m} onChange={e => pref('max_road_distance_m', Number(e.target.value))} aria-label="Maximum road distance in metres" /></div>
    <div className="slider-row"><span>School within</span><strong>{p.max_school_distance_m.toLocaleString()} m</strong><input type="range" min="100" max="5000" step="100" value={p.max_school_distance_m} onChange={e => pref('max_school_distance_m', Number(e.target.value))} aria-label="Maximum school distance in metres" /></div>
    <div className="two-col"><label>Road importance<select value={p.road_importance} onChange={e => pref('road_importance', e.target.value as EvaluationSettings['preferences']['road_importance'])}><option>low</option><option>medium</option><option>high</option></select></label><label>School importance<select value={p.school_importance} onChange={e => pref('school_importance', e.target.value as EvaluationSettings['preferences']['school_importance'])}><option>low</option><option>medium</option><option>high</option></select></label></div>
    <p className="field-hint">Distances are straight lines from the parcel boundary (older reports: from its centroid) to OpenStreetMap features. They are not travel distances and not proof of legal access.</p>
    {error && <p className="form-error">{error}</p>}</div><div className="drawer-footer"><button className="primary-button scenario-apply" disabled={busy || changed === 'no change'} onClick={() => onRun(local, changed)}>{busy ? 'Re-evaluating…' : 'Apply scenario'}</button></div></aside></div>
}
