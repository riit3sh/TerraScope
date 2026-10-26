import { Fragment, useEffect, useMemo, useState } from 'react'
import { KpiStrip } from './KpiStrip'
import { acresToM2, AREA_UNIT_LABEL, AREA_UNITS, AreaUnit, formatArea, useAreaUnit } from '../lib/area'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowLeft, FileText, FlaskConical, History, Printer, RefreshCw, Sparkles, TriangleAlert, Upload, X } from 'lucide-react'
import { DOC_TYPE_LABEL, DocType, evaluateParcel, EvaluationSettings, FactorAssessment, Finding, FloodIndicators, LandCoverHistory, LandDetails, ParcelRecord, saveLandDetails, uploadEvidence, AreaNews, NewsItem, getAreaNews, PublicFacility, LegalChecklist, LegalCheckInput, getLegalChecks, recordLegalCheck, DevelopmentClaim, DevelopmentClaimInput, ProjectType, listClaims, addClaim, deleteClaim } from '../lib/api'

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
  for (const mechanism of ['rainfall_waterlogging', 'coastal_flooding']) if (byMechanism[mechanism] && byMechanism[mechanism].status !== 'not_applicable') lines.push({ mechanism, status: byMechanism[mechanism].status, text: byMechanism[mechanism].status === 'not_assessed' ? 'No dataset integrated. Unknown, not safe.' : sentence(byMechanism[mechanism].summary) })
  return lines
}

function FloodPanel({ indicators, latitude }: { indicators?: FloodIndicators | null; latitude: number | null | undefined }) {
  if (!indicators?.components?.length) return null
  const river = indicators.river_flood
  const cellArea = river?.model_cell_area_m2 ?? (latitude == null ? null : (3 / 3600) * 111320 * Math.cos(latitude * Math.PI / 180) * (3 / 3600) * 110574)
  const parcelArea = river?.parcel_area_m2
  const cells = river?.model_cells_overlapping_parcel
  return <section className="flood-section"><div className="section-head"><div><div className="section-label">FLOOD EVIDENCE · RED FLAGS ONLY, NO FLOOD SCORE</div><h2>{floodHeadline(indicators)}</h2></div><span className="completeness">No overall flood score or safety percentage: mechanisms that are not assessed are unknown, not safe.</span></div>
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
  const headline = growth && ['indicative', 'built_out', 'established'].includes(growth.status) ? growth.basis.split(':')[0] : 'No area history in this report'
  return <section className="decision-section">
    <div>
      <div className="section-label">PAST DEVELOPMENT AROUND THE PLOT · 2017-2023 · HISTORICAL, NOT A FORECAST</div>
      <h2>{headline}</h2>
      {data.length > 1 && <p className="chart-subtitle">Share of land mapped as built-up each year, within 1 km of the plot and 1–3 km away. Each point is one annual map (2017–2023). This is past development; it does not predict future building or prices.</p>}
      {flags.length > 0 && <div className="red-flags" role="alert"><strong><TriangleAlert size={14} /> Red flags: don’t buy unless these are explained</strong><ul>{flags.map(flag => <li key={flag}>{flag}</li>)}</ul></div>}
      {data.length > 1 ? <div className="chart-wrap history-chart"><ResponsiveContainer width="100%" height={210}><LineChart data={data}><CartesianGrid stroke="#25313a" vertical={false} /><XAxis dataKey="year" stroke="#71808b" tickLine={false} axisLine={false} /><YAxis domain={[0, 100]} stroke="#71808b" tickLine={false} axisLine={false} unit="%" width={52} label={{ value: 'Built-up land (%)', angle: -90, position: 'insideLeft', fill: '#71808b', fontSize: 11 }} /><Tooltip contentStyle={{ background: '#11191d', border: '1px solid #2d3b42' }} formatter={value => `${value}%`} /><Line type="monotone" dataKey="near" stroke="#b8f36a" strokeWidth={2} dot={{ r: 3 }} name="Built up within 1 km" connectNulls={false} /><Line type="monotone" dataKey="far" stroke="#77d8ff" strokeWidth={2} dot={{ r: 3 }} name="Built up 1–3 km away" connectNulls={false} /></LineChart></ResponsiveContainer></div>
        : <p className="muted">{history ? `Area history unavailable: ${history.error || 'too few years were classified around the plot.'}` : 'This report was made before TerraScope read the area history. Analyse the same boundary again to add it.'}</p>}
      {data.length > 1 && <p className="history-legend"><span><i className="dot near" /> built up within 1 km of the plot</span><span><i className="dot far" /> 1–3 km away</span></p>}
      {history?.parcel?.length ? <p className="muted window-note"><strong>The plot itself:</strong> {plotStory(history.parcel)}.</p> : null}
      {data.length > 1 && <p className="muted window-note">{history?.dataset || 'Annual land cover'}, 10 m, one map a year. A modelled classification: a single year can be off, so the decision uses the trend over every year. It shows building on the ground, not prices or approvals.</p>}
      {data.length > 1 && <details className="explain"><summary>What does this graph mean?</summary><p><strong>Land-cover map:</strong> a computer model looks at each year's satellite images and labels every 10 m square of ground as built-up, crops, trees, water and so on. The graph shows what share of the land around the plot was labelled built-up each year.</p><p><strong>Reading it:</strong> a rising line means more land around the plot was built on over 2017–2023; a flat line high up means an already developed neighbourhood; a flat line near the bottom means little building nearby. Example: 63% → 73% within 1 km means roughly one more tenth of the surrounding land was built on.</p><p><strong>Limits:</strong> it is a model's estimate, not a survey or a land record. Small buildings, roads under trees and mixed squares (half house, half field) can be mislabelled, and single years can wobble, so TerraScope uses the trend across all years. It is history: it does not show approved future projects or prices.</p></details>}
    </div>
    <div>
      <div className="section-label">BEFORE YOU PAY</div>
      {checks == null ? <p className="muted">This evaluation predates the checklist. Re-evaluate the report to list it.</p> : checks.length ? <ul className="checklist">{checks.map(check => <li key={check}>{check}</li>)}</ul> : <p className="muted">Nothing outstanding.</p>}
      <p className="field-hint">TerraScope cannot read land records, so title, encumbrance and approvals are never verified here. Get them from the sub-registrar office and the seller.</p>
      {record.verdict?.would_change?.length ? <><div className="section-label would-change-label">WHAT WOULD CHANGE THIS RECOMMENDATION</div><ul className="checklist">{record.verdict.would_change.map(item => <li key={item}>{item}</li>)}</ul></> : null}
    </div>
  </section>
}

const ASSESSMENT_LABEL: Record<Finding['assessment'], string> = { red_flag: 'Red flag', caution: 'Caution', ok: 'OK', unknown: 'Unknown' }
const BASIS_LABEL: Record<Finding['basis'], string> = { measured: 'measured', modelled: 'model scenario', mapped: 'mapped (OpenStreetMap), not ownership', user_provided: 'your claim, not verified', not_verified: 'not verified', unavailable: 'source unavailable' }

function FindingsTable({ findings }: { findings?: Finding[] | null }) {
  if (!findings?.length) return <section className="findings-section"><div className="section-label">WHAT WE FOUND</div><p className="muted">This evaluation predates the findings list. Use “Re-evaluate with current methods” above to add it.</p></section>
  const rows = findings.filter(f => f.assessment !== 'unknown')
  const unknownCount = findings.length - rows.length
  const counts = rows.reduce<Record<string, number>>((n, f) => ({ ...n, [f.assessment]: (n[f.assessment] || 0) + 1 }), {})
  return <section className="findings-section">
    <div className="section-head"><div><div className="section-label">EVIDENCE-BACKED FINDINGS</div><h2>{counts.red_flag ? `${counts.red_flag} red flag${counts.red_flag > 1 ? 's' : ''}` : 'No red flags'}{counts.caution ? `, ${counts.caution} to check` : ''}</h2><p className="muted">Only findings supported by collected evidence are shown here.{unknownCount ? ` ${unknownCount} unverified checks are listed below under what you still need to verify.` : ''}</p></div></div>
    {rows.length ? <div className="finding-list">{rows.map(f => <div className={`finding ${f.assessment}`} key={f.area}>
      <div className="finding-what"><strong>{f.area}</strong><span className={`finding-badge ${f.assessment}`}>{ASSESSMENT_LABEL[f.assessment]}</span></div>
      <div className="finding-body"><p>{f.finding}</p><small>{BASIS_LABEL[f.basis]}{f.source ? ` · ${f.source}` : ''}{f.as_of ? ` · as of ${f.as_of}` : ''}</small></div>
      <div className="finding-next"><span>NEXT STEP</span><p>{f.next_step}</p></div>
    </div>)}</div> : <p className="muted">No collected finding is strong enough to report yet.</p>}
  </section>
}

/** The four answers in buyer words. The stored codes (AVOID, INSUFFICIENT_EVIDENCE) are unchanged so saved reports still read. */
const VERDICT_LABEL: Record<string, string> = { BUY: 'BUY', WAIT: 'WAIT', AVOID: 'WALK AWAY', INSUFFICIENT_EVIDENCE: 'INSUFFICIENT DATA', RESTRICTED: 'VERIFY RESTRICTION', UNAVAILABLE: 'NOT EVALUATED' }

const LAYER_OF: Record<string, string> = { Road: 'road', School: 'school', Hospital: 'hospital', 'Bus stop or station': 'bus', 'Railway station': 'rail_station' }

/** Nearby facilities, exactly as the regional OpenStreetMap store returned them: distance, name, nothing inferred. */
function FacilitiesTable({ record }: { record: ParcelRecord }) {
  const i: NonNullable<ParcelRecord['infrastructure']> = record.infrastructure || { nearest_road_distance_m: null, nearest_road_type: null, nearest_school_distance_m: null }
  const osm = (record.evidence || []).find(e => e.source_type === 'openstreetmap')
  const rows: [string, number | null | undefined, string | null | undefined, string][] = [
    ['Road', i.nearest_road_distance_from_boundary_m ?? i.nearest_road_distance_m, [i.nearest_road_name, i.nearest_road_type].filter(Boolean).join(' · '), i.nearest_road_distance_from_boundary_m != null ? 'from the boundary' : 'from the centre'],
    ['School', i.nearest_school_distance_from_boundary_m ?? i.nearest_school_distance_m, i.nearest_school_name, i.nearest_school_distance_from_boundary_m != null ? 'from the boundary' : 'from the centre'],
    ['Hospital', i.nearest_hospital_distance_m, i.nearest_hospital_name, 'from the centre'],
    ['Bus stop or station', i.nearest_bus_distance_m, [i.nearest_bus_name, i.nearest_bus_type?.replace('_', ' ')].filter(Boolean).join(' · '), 'from the centre'],
    ['Railway station', i.nearest_rail_station_distance_m, [i.nearest_rail_station_name, i.nearest_rail_station_type].filter(Boolean).join(' · '), 'from the centre'],
  ]
  const collected = i.search_radius_m != null
  return <section className="facilities-section"><div className="section-label">NEARBY FACILITIES · STRAIGHT-LINE DISTANCES FROM OPENSTREETMAP</div>
    {collected ? <div className="flood-table-wrap"><table className="flood-table"><thead><tr><th>Facility</th><th>Distance</th><th>Name / type</th><th>Measured</th></tr></thead><tbody>{rows.map(([name, d, label, from]) => <tr key={name}><td>{name}</td><td>{d == null ? (i.layer_status?.[LAYER_OF[name]] === 'not_installed' ? 'not installed for this region (unknown)' : `none mapped within ${m(i.search_radius_m)}`) : m(d)}</td><td>{d == null ? '—' : label || 'unnamed'}</td><td>{d == null ? '—' : from}</td></tr>)}</tbody></table></div>
      : <p className="muted">{osm?.summary || 'No facility data was collected for this parcel.'}</p>}
    {Object.entries(i.layer_status || {}).some(([, s]) => s === 'not_installed') && <p className="older-note" role="note"><TriangleAlert size={15} /><span>Not installed for this region: {Object.entries(i.layer_status || {}).filter(([, s]) => s === 'not_installed').map(([l]) => l.replace('_', ' ')).join(', ')}. These are unknown, not absent; accessibility is not assessed without roads.</span></p>}
    <p className="field-hint">{osm ? `${osm.source_reference} · data as of ${(osm.observed_at || '').slice(0, 10)}. ` : ''}Straight lines, not travel routes; a mapped road is not proof of legal access. “None mapped” means OpenStreetMap has nothing there, not that none exists: check locally. Colleges, markets and shops are not collected in this version.</p>
  </section>
}

/** The strongest points each way, taken from the findings (nothing new is computed here). */
function Highlights({ findings }: { findings?: Finding[] | null }) {
  if (!findings?.length) return null
  const good = findings.filter(f => f.assessment === 'ok' && f.next_step !== 'No action from this source.').slice(0, 3)
  const bad = findings.filter(f => f.assessment === 'red_flag' || f.assessment === 'caution').slice(0, 3)
  const known = findings.filter(f => f.assessment !== 'unknown').length
  return <section className="highlights"><div><div className="section-label">STRONGEST POSITIVES</div>{good.length ? <ul>{good.map(f => <li key={f.area}><strong>{f.area}:</strong> {f.finding}</li>)}</ul> : <p className="muted">None the evidence supports.</p>}</div>
    <div><div className="section-label">STRONGEST NEGATIVES</div>{bad.length ? <ul>{bad.map(f => <li key={f.area} className={f.assessment}><strong>{f.area}:</strong> {f.finding}</li>)}</ul> : <p className="muted">No red flag or caution in the evidence.</p>}</div>
    <div className="evidence-meter"><div className="section-label">EVIDENCE COMPLETENESS</div><strong>{known} of {findings.length}</strong><small>checks have evidence; the rest are Unknown (not verified), never assumed safe.</small></div>
  </section>
}

const NEWS_STATUS: Record<NewsItem['verification'], string> = { official_source: 'Official source', corroborated: 'Reported by 2+ outlets', single_report: 'Single news report' }
const PROJECT_STATUS_LABEL: Record<NonNullable<NewsItem['project_status']>, string> = { proposed: 'proposed', approved: 'approved', under_construction: 'under construction', completed: 'completed', cancelled: 'cancelled', unknown: 'status unknown' }
const NEWS_WHY: Record<NewsItem['topic'], string> = {
  hazards: 'A reported flood, waterlogging or road closure in this locality. Ask neighbours and the local body whether this plot or its access road was affected.',
  legal_planning: 'A reported dispute, encroachment, demolition or planning action in this locality. Check whether it involves this survey number before paying.',
  development: 'A reported project near this locality. Confirm its sanction and status with the authority; it is not assumed to happen.',
}

/** Local news, searched on demand and cached for a day. Discovery evidence: it never changes the decision or verifies title. */
function LocalNews({ parcelId }: { parcelId: string }) {
  const [news, setNews] = useState<AreaNews | null>(null)
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [error, setError] = useState('')
  async function load(refresh = false) {
    setState('loading'); setError('')
    try { setNews(await getAreaNews(parcelId, refresh)); setState('idle') }
    catch (e) { setState('error'); setError(e instanceof Error ? e.message : 'The news search could not be run.') }
  }
  useEffect(() => { load() }, [parcelId])
  const place = news?.place
  return <section className="news-section"><div className="section-head"><div><div className="section-label">LOCAL NEWS AND DEVELOPMENT · DISCOVERY EVIDENCE, NOT VERIFICATION</div>
    <h2>{state === 'loading' ? 'Searching local news…' : !news ? 'Local news not searched' : news.status === 'results' ? `${news.items.length} reported item${news.items.length === 1 ? '' : 's'} for ${place?.locality}` : news.status === 'no_results' ? `No indexed news found for ${place?.locality}` : news.status === 'unavailable' ? 'News search unavailable right now' : 'Not searched'}</h2></div>
    <button className="quiet-button" disabled={state === 'loading'} onClick={() => load(true)}><RefreshCw size={14} /> {state === 'loading' ? 'Searching (up to a minute)…' : 'Search again'}</button></div>
    {state === 'error' && <p className="form-error" role="alert">{error}</p>}
    {news && <p className="field-hint">{news.status === 'unavailable' ? 'Tried to search' : 'Searched'} {news.provider} for “{place?.variants.join('”, “')}” together with “{place?.district}”, {news.searched_from} to {news.retrieved_at.slice(0, 10)}{news.cached ? ` · cached result from ${news.retrieved_at.replace('T', ' ').slice(0, 16)} UTC` : ' · searched just now'}.</p>}
    {news?.status === 'unavailable' && <p className="muted">Temporarily unavailable: {news.reason}. Nothing is assumed from a failed search; it says nothing about the area either way.</p>}
    {news?.status === 'no_results' && <p className="muted">Nothing indexed mentions this locality and district with flooding, disputes, demolition or development words. That is not evidence that nothing happened: small local reports are often not indexed.</p>}
    {news?.status === 'not_searched' && <p className="muted">{news.reason}</p>}
    {news?.truncated_topics?.length ? <p className="muted">Some topics reached the provider's limit of 250 articles, so older items may be missing from the timeline.</p> : null}
    {news && news.items.length > 0 && <div className="news-list">{news.items.slice(0, 40).map((item, index, shown) => <Fragment key={item.url}>{(index === 0 || (shown[index - 1].published || '').slice(0, 4) !== (item.published || '').slice(0, 4)) && <div className="section-label">{(item.published || '').slice(0, 4) || 'Date unknown'}</div>}<div className={`news-item ${item.topic}`}>
      <div className="news-meta"><span className={`finding-badge ${item.verification === 'single_report' ? 'unknown' : 'caution'}`}>{NEWS_STATUS[item.verification]}</span><span>{item.topic_label}</span>{item.project_status && <span className="news-flag">reported as {PROJECT_STATUS_LABEL[item.project_status]}</span>}{item.speculative && <span className="news-flag">proposal or speculation</span>}{item.stale && <span className="news-flag">older than 2 years</span>}{!item.locality_in_headline && <span className="news-flag">headline does not name the locality: check it is about this place</span>}</div>
      <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
      <small>{item.publisher} · {item.published || 'date unknown'}{item.language && item.language !== 'English' ? ` · ${item.language}` : ''}{item.outlets > 1 ? ` · ${item.outlets} outlets` : ''}</small>
      <p>{NEWS_WHY[item.topic]}</p>
    </div></Fragment>)}</div>}
    {news && news.items.length > 0 && <p className="field-hint">Dates are when the article was indexed, not when the event happened. “Reported as …” is the headline's wording, not an official record: confirm sanction and status with the authority. Distance from the plot is not known. None of this changes the decision.</p>}
    {news && <details className="flood-details"><summary>What was searched, and the limits</summary><p className="muted">{news.coverage}</p><p className="muted">{news.limitations}</p><ul className="method-notes">{news.queries.map(q => <li key={q.topic}><code>{q.query}</code></li>)}</ul></details>}
  </section>
}

const CLAIM_STATUS: Record<DevelopmentClaim['verification'], string> = { user_provided: 'Your information · not verified', link_provided: 'Link provided · not verified by TerraScope', official_link_provided: 'Official link provided · not read or verified by TerraScope' }
const PROJECT_LABEL: Record<ProjectType, string> = { road: 'Road', transport: 'Public transport', industrial: 'Industrial', residential_layout: 'Residential layout', school: 'School', hospital: 'Hospital', commercial: 'Shops / commercial', other: 'Other' }

/** What a resident, broker or the buyer has heard about upcoming projects: kept as claims, never scored. */
function FutureDevelopment({ parcelId }: { parcelId: string }) {
  const [claims, setClaims] = useState<DevelopmentClaim[]>([])
  const [form, setForm] = useState<DevelopmentClaimInput>({ claim: '', project_type: 'road', source: 'resident', checked_on: new Date().toLocaleDateString('en-CA') })
  const [message, setMessage] = useState('')
  useEffect(() => { listClaims(parcelId).then(setClaims).catch(() => setMessage('Could not load recorded claims.')) }, [parcelId])
  async function save() {
    setMessage('')
    try {
      const clean = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== '' && v != null)) as unknown as DevelopmentClaimInput
      const saved = await addClaim(parcelId, clean); setClaims(c => [...c, saved]); setForm(f => ({ ...f, claim: '', evidence_url: '', location_text: '', distance_m: null, expected_date: '' }))
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Could not save.') }
  }
  return <section className="claims-section"><div className="section-label">FUTURE DEVELOPMENT · YOUR INFORMATION, KEPT SEPARATE FROM THE EVIDENCE</div>
    <h2>{claims.length ? `${claims.length} recorded claim${claims.length === 1 ? '' : 's'}` : 'Heard about an upcoming project?'}</h2>
    <p className="field-hint">Record what a resident, broker or seller told you. It stays “not verified” until official evidence (a sanction order or notification) is checked, it never changes the recommendation, and no completion is assumed.</p>
    {claims.length > 0 && <div className="news-list">{claims.map(c => <div className="news-item development" key={c.id}><div className="news-meta"><span className="finding-badge unknown">{CLAIM_STATUS[c.verification]}</span><span>{PROJECT_LABEL[c.project_type]}</span><span>source: {c.source}</span></div>
      <strong>{c.claim}</strong><small>{[c.location_text, c.distance_m != null ? `about ${m(c.distance_m)} away` : null, c.expected_date ? `expected ${c.expected_date} (as claimed)` : null, c.checked_on ? `checked ${c.checked_on}` : null].filter(Boolean).join(' · ')}{c.evidence_url ? <> · <a href={c.evidence_url} target="_blank" rel="noreferrer">evidence link</a></> : null}</small>
      <p>{c.effect}</p><button className="quiet-button" onClick={() => deleteClaim(parcelId, c.id).then(() => setClaims(x => x.filter(y => y.id !== c.id)))}>Remove</button></div>)}</div>}
    <div className="claim-form">
      <label className="stacked-field">What did you hear?<input value={form.claim} placeholder="e.g. A ring road will pass about 1 km north" onChange={e => setForm(f => ({ ...f, claim: e.target.value }))} /></label>
      <div className="land-grid">
        <label className="stacked-field">Project type<select value={form.project_type} onChange={e => setForm(f => ({ ...f, project_type: e.target.value as ProjectType }))}>{(Object.keys(PROJECT_LABEL) as ProjectType[]).map(t => <option key={t} value={t}>{PROJECT_LABEL[t]}</option>)}</select></label>
        <label className="stacked-field">Source<select value={form.source} onChange={e => setForm(f => ({ ...f, source: e.target.value as DevelopmentClaimInput['source'] }))}>{['resident', 'broker', 'seller', 'news', 'official', 'other'].map(s => <option key={s}>{s}</option>)}</select></label>
        <label className="stacked-field">Where (optional)<input value={form.location_text || ''} onChange={e => setForm(f => ({ ...f, location_text: e.target.value }))} /></label>
        <label className="stacked-field">Distance in metres (optional)<input type="number" min="0" value={form.distance_m ?? ''} onChange={e => setForm(f => ({ ...f, distance_m: e.target.value === '' ? null : Number(e.target.value) }))} /></label>
        <label className="stacked-field">Expected date, as claimed (optional)<input value={form.expected_date || ''} onChange={e => setForm(f => ({ ...f, expected_date: e.target.value }))} /></label>
        <label className="stacked-field">Evidence link (optional)<input type="url" value={form.evidence_url || ''} onChange={e => setForm(f => ({ ...f, evidence_url: e.target.value }))} /></label>
      </div>
      <button className="quiet-button" disabled={form.claim.trim().length < 5} onClick={save}>Record claim</button>
      {message && <p className="form-error" role="alert">{message}</p>}
    </div>
  </section>
}

function Bar({ label, value, color, status }: { label: string; value: number | null; color: string; status?: string }) {
  const available = typeof value === 'number'
  return <div className={`score-line${available ? '' : ' unassessed'}`}>
    <div><span>{label}</span><strong>{available ? value : status === 'partial' ? 'Partly assessed' : 'Not scored'}</strong></div>
    <div className="bar"><i style={{ width: available ? `${Math.max(0, Math.min(100, value))}%` : '0%', background: color }} /></div>
    {status && status !== 'assessed' && <small className="score-status">{status === 'indicative' ? 'indicative only' : status === 'partial' ? 'evidence shown · not scored' : status === 'built_out' || status === 'established' ? 'established area · not scored' : 'no supporting evidence'}</small>}
  </div>
}

function EvidenceRow({ title, refName, freshness, summary, observedAt, details }: { title: string; refName: string; freshness: string; summary: string; observedAt?: string | null; details?: string }) {
  return <div className="evidence-row"><div className="evidence-icon"><FileText size={16} /></div><div><strong>{title}</strong><p>{summary}{cutOff(summary) && <em className="cut-note"> … (cut off when this report was saved)</em>}</p><small>{refName} · {(observedAt || '').slice(0, 10) || 'date unavailable'}</small>{details && <small className="evidence-details">{details}</small>}</div><span className={`freshness ${freshness}`}>{freshness.replace('_', ' ')}</span></div>
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

const OUTCOME_LABEL: Record<LegalCheckInput['outcome'], string> = { confirmed: 'Record found and matches the seller', problem: 'Problem found', not_found: 'Could not find the record', not_applicable: 'Not applicable', government_non_transferable: 'Government land, not transferable', government_transfer_documented: 'Government land with a documented lawful auction or transfer', private_per_record: 'Private according to this record', restriction_prohibits_use: 'Restriction prohibits this use', restriction_with_conditions: 'Restriction allows this use on conditions (e.g. NOC)', records_unavailable: 'Record unavailable' }
const ADVERSE_OUTCOMES = new Set(['problem', 'government_non_transferable', 'restriction_prohibits_use'])
const CONTACT_LABEL: Record<PublicFacility['contact'], string> = { overlap: 'Overlaps the boundary', point_inside: 'Mapped as a point inside the boundary', edge: 'Touches it or within the map uncertainty', nearby: 'Nearby' }
const SIGNAL_LABEL: Record<PublicFacility['ownership_signal'], string> = { government_tagged: 'map tag suggests a public operator', private_tagged: 'map tag suggests a private operator', unknown: 'ownership not shown on the map' }

/** Government and restricted land: mapped facilities (never ownership) and the decision's status. */
function GovernmentLand({ record }: { record: ParcelRecord }) {
  const status = record.verdict?.government_land
  const mapped = record.public_land
  const tone = status?.walk_away ? 'red_flag' : status?.hold ? 'caution' : 'unknown'
  return <section className={`finding ${tone} gov-land`}>
    <div className="section-label">MAPPED RESTRICTION SIGNAL · NOT OWNERSHIP PROOF</div>
    <h2>{status?.walk_away ? 'Mapped overlap requires official verification' : status ? status.label : 'Not assessed in this evaluation: re-evaluate'}</h2>
    {status?.warning && <p><strong>{status.warning}</strong></p>}
    {!mapped ? <p className="muted">This report was analysed before TerraScope checked mapped public facilities. Analyse the same boundary again to add it. Until then, nothing is known either way.</p>
      : mapped.status !== 'assessed' ? <p className="muted">Public facilities not checked: {mapped.reason} This is not evidence that the land is private or unrestricted.</p>
      : <>
        {mapped.overlaps.length ? <>
          <div className="action-card restriction-action"><strong>Before you rely on this result</strong><p>This is a mapped overlap, not a legal ownership decision. First confirm that the drawn boundary does not accidentally include the lake, ground or public facility.</p><ol><li>Compare the boundary with the seller's survey sketch and FMB map.</li><li>Check Tamil Nadu e-Services, the A-register and the local authority for the same survey number.</li><li>Upload the official record and record the result under Legal checks before considering this parcel.</li></ol></div>
          <ul className="doc-list">{mapped.overlaps.map((f, i) => <li key={`${f.osm_id}-${i}`}><strong>{f.category_label}{f.name ? ` · ${f.name}` : ''}</strong> · {CONTACT_LABEL[f.contact]}{f.contact === 'overlap' && f.overlap_share ? ` (${Math.round(f.overlap_share * 100)}% of the plot)` : ''} · {SIGNAL_LABEL[f.ownership_signal]}{f.osm_id ? <> · <a href={`https://www.openstreetmap.org/${({ n: 'node', w: 'way', r: 'relation' } as Record<string, string>)[f.osm_id[0]]}/${f.osm_id.slice(1)}`} target="_blank" rel="noreferrer">OSM {f.osm_id}</a></> : null}</li>)}</ul>
        </>
          : <p className="muted">No mapped court, government office, stadium, park, railway, defence area or water body touches the boundary. That does not show the land is private or unrestricted: mapping is incomplete.</p>}
        {mapped.nearby.length > 0 && <p className="field-hint">Nearby (straight line, proximity only): {mapped.nearby.slice(0, 6).map(f => `${f.category_label.split(' (')[0]}${f.name ? ` ${f.name}` : ''} ${Math.round(f.distance_m)} m`).join(' · ')}.</p>}
        <p className="field-hint">OpenStreetMap ({mapped.licence}), data as of {mapped.data_as_of || 'unknown'}{mapped.stale ? ' (more than a year old)' : ''}; positions can be off by about {mapped.uncertainty_m} m. {mapped.limitations}</p>
      </>}
    {status?.checks?.length ? <p className="field-hint">Next: {status.checks[0]}. Record what you find under Legal checks → Government / poramboke land.</p> : null}
  </section>
}

/** The official source for each legal check, and the buyer's own record of checking it. A record is never verification. */
function LegalChecks({ record, onChanged }: { record: ParcelRecord; onChanged: () => Promise<void> }) {
  const parcelId = record.parcel_id || ''
  const [list, setList] = useState<LegalChecklist | null>(null)
  const [form, setForm] = useState<LegalCheckInput | null>(null)
  const [status, setStatus] = useState('')
  useEffect(() => { getLegalChecks(parcelId).then(setList).catch(() => setStatus('Could not load the legal checklist.')) }, [parcelId])
  async function save() {
    if (!form) return
    setStatus('Saving…')
    try {
      const clean = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, typeof v === 'string' ? v.trim() || null : v]).filter(([, v]) => v != null)) as unknown as LegalCheckInput
      setList(await recordLegalCheck(parcelId, clean)); setForm(null)
      await onChanged()
      setStatus('Recorded and re-evaluated. This is your record, not verification by TerraScope.')
    } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not save.') }
  }
  if (!list) return status ? <p className="muted">{status}</p> : null
  return <div className="land-evidence">
    <div className="field-label">LEGAL CHECKS <span>{list.state_guide === 'available' ? `official sources for ${list.state}` : list.state_guide === 'partial' ? `official links for ${list.state} (some checks only)` : `no state guide for ${list.state || 'this state'} yet`} · automated verification: none</span></div>
    <p className="field-hint">{list.notice}</p>
    <ul className="doc-list">{list.checks.map(c => <li key={c.check}>
      <strong>{c.label}</strong>{c.mandatory_for_buy ? ' · required for BUY' : ''} · <span className={`finding-badge ${c.record && ADVERSE_OUTCOMES.has(c.record.outcome) ? 'red_flag' : c.record ? 'caution' : 'unknown'}`}>{c.record ? `${OUTCOME_LABEL[c.record.outcome]} · recorded by you ${c.record.checked_on}` : 'Not checked'}</span>
      {(c.records?.length ?? 0) > 1 && <small> {c.records!.length} sources recorded: {c.records!.map(r => `${r.source}: ${OUTCOME_LABEL[r.outcome]}`).join(' · ')}</small>}
      {c.record && <small> {c.record.source}{c.record.survey_number ? ` · survey ${c.record.survey_number}` : ''}{c.record.reference ? ` · ref ${c.record.reference}` : ''}{c.record.evidence ? ` · evidence: ${c.record.evidence}` : ''}{c.record.notes ? ` · ${c.record.notes}` : ''}</small>}
      {c.guide ? <p className="muted">Where: <a href={c.guide.url} target="_blank" rel="noreferrer">{c.guide.authority}</a>. {c.guide.how} <em>{c.guide.access}</em></p> : <p className="muted">No official source has been researched for this state yet: ask a local lawyer which office holds this record.</p>}
      {form?.check !== c.check && <button className="quiet-button" onClick={() => setForm({ check: c.check, outcome: c.outcomes[0], survey_number: c.check === 'government_land' ? (record.user_land_details?.survey_number || '') : null, source: c.guide?.authority || '', checked_on: new Date().toLocaleDateString('en-CA'), reference: '', evidence: '', notes: '' })}>Record a check</button>}
      {form?.check === c.check && <div className="land-grid">
        <label className="stacked-field">What you found<select value={form.outcome} onChange={e => setForm({ ...form, outcome: e.target.value as LegalCheckInput['outcome'] })}>{c.outcomes.filter(o => o !== 'not_applicable' || c.check === 'rera').map(o => <option key={o} value={o}>{OUTCOME_LABEL[o]}</option>)}</select></label>
        {c.check === 'government_land' && <label className="stacked-field">Survey no. looked up<input value={form.survey_number || ''} onChange={e => setForm({ ...form, survey_number: e.target.value })} /></label>}
        <label className="stacked-field">Source consulted<input value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} /></label>
        <label className="stacked-field">Date checked<input type="date" value={form.checked_on} onChange={e => setForm({ ...form, checked_on: e.target.value })} /></label>
        <label className="stacked-field">Reference no.<input value={form.reference || ''} onChange={e => setForm({ ...form, reference: e.target.value })} /></label>
        <label className="stacked-field">Evidence (document)<input list="legal-evidence-docs" value={form.evidence || ''} onChange={e => setForm({ ...form, evidence: e.target.value })} /></label>
        <label className="stacked-field">Notes<input value={form.notes || ''} onChange={e => setForm({ ...form, notes: e.target.value })} /></label>
        <datalist id="legal-evidence-docs">{(record.user_land_details?.documents || []).map(d => <option key={d.filename} value={d.filename} />)}</datalist>
        <button className="quiet-button" disabled={form.source.trim().length < 3 || !form.checked_on || (form.check === 'government_land' && !(form.survey_number || '').trim())} onClick={save}>Save and re-evaluate</button><button className="quiet-button" onClick={() => setForm(null)}>Cancel</button>
      </div>}
    </li>)}</ul>
    {list.history_count > 0 && <p className="field-hint">{list.history_count} record{list.history_count === 1 ? '' : 's'} kept; the newest per check is shown. A record you could not find is not a clearance.</p>}
    {status && <p className="muted" role="status">{status}</p>}
  </div>
}

/** One or two sentences on what the Sentinel-2 comparison found, in plain words. */
function changeFinding(record: ParcelRecord) {
  const sat = record.satellite
  if (!sat?.change_type || sat.change_type === 'insufficient_evidence') return 'Too few clear images to say anything about change on the plot.'
  if (!sat.change_method) return 'This older report used a superseded method; analyse again for the same-season comparison.'
  return ({
    no_change: 'Same-season images a year apart agree: no material change on the plot over this period.',
    inconclusive: 'Inconclusive: the same-season comparisons disagree, so TerraScope draws no conclusion about change on the plot. This is not evidence of construction or of no change.',
    construction_growth: 'The same-season comparisons agree on a shift consistent with construction or clearing on the plot. Visit the plot to see what changed.',
    vegetation_loss: 'The same-season comparisons agree on vegetation loss on the plot (clearing, harvest pattern change or construction).',
    vegetation_gain: 'The same-season comparisons agree on vegetation gain on the plot.',
  } as Record<string, string>)[sat.change_type] || sat.change_type
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

export function Report({ initialSnapshot, initialSettings, onBack }: { initialSnapshot: ParcelRecord; initialSettings: EvaluationSettings; onBack: () => void }) {
  const [record, setRecord] = useState(initialSnapshot)
  const [areaUnit, setAreaUnit] = useAreaUnit()
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
  // Restricted land is not assessed for purchase: only the reason is shown (user decision, 2026-10-26).
  const restricted = verdict === 'RESTRICTED'
  const scored = factors.filter(f => f.score != null)
  const unscored = factors.filter(f => f.score == null && f.weight_pct > 0)
  const satelliteIsDemo = evidence.some(item => (item.source_type || '') === 'satellite' && /synthetic/i.test(`${item.source_reference || ''} ${item.title || ''}`))
  const tabMatch: Record<EvidenceTab, string[]> = { Satellite: ['satellite', 'land_cover'], Infrastructure: ['openstreetmap', 'infrastructure'], 'Flood indicators': ['jrc_gsw', 'jrc_flood_hazard', 'copernicus_dem', 'osm_water', 'open_elevation', 'elevation'], RERA: ['maharera_seed', 'rera'], 'Uploaded Documents': ['document', 'user_upload'], 'Derived Scores': ['derived'] }
  const visibleEvidence = evidence.filter(item => tabMatch[activeEvidenceTab].some(type => (item.source_type || '').toLowerCase().includes(type)))
  const fields = record.metadata.data_completeness_fields
  const fieldCount = fields ? Object.keys(fields).length : 12
  const collectedCount = fields ? Object.values(fields).filter(Boolean).length : Math.round(((record.metadata.data_completeness_pct ?? 0) / 100) * 12)
  const isAi = record.verdict?.explanation_source === 'ai'
  // Any evaluation missing the newest field (would_change) was made under older rules: offer a re-evaluation.
  const olderEvaluation = record.score_breakdown != null && (record.verdict?.explanation_source == null || record.verdict?.findings == null || record.verdict?.would_change == null)
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
      <section className="report-heading"><div><div className="eyebrow"><span className="pulse" /> ANALYSIS SNAPSHOT · {(record.metadata.analysis_snapshot_id || '—').slice(0, 8)}</div><h1>{placeName(address)}</h1>{address && <p className="full-address">{address}</p>}<p>{formatArea(record.geometry_metadata?.area_m2 ?? (record.geometry_metadata?.area_acres == null ? null : acresToM2(record.geometry_metadata.area_acres)), areaUnit)} <select className="area-unit" aria-label="Area unit" value={areaUnit} onChange={e => setAreaUnit(e.target.value as AreaUnit)}>{AREA_UNITS.map(u => <option key={u} value={u}>{AREA_UNIT_LABEL[u]}</option>)}</select> <span>·</span> {record.metadata.analysis_date_from || '—'} — {record.metadata.analysis_date_to || '—'}</p></div><div className={`verdict-badge ${verdict.toLowerCase()}`}><span>BUY, WAIT OR WALK AWAY?</span><strong>{VERDICT_LABEL[verdict] || verdict}</strong><small>{!record.verdict ? 'not evaluated yet' : restricted ? 'not assessed for purchase' : verdict === 'BUY' ? 'only after the legal checks below' : insufficient ? 'see what is missing below' : record.verdict.red_flags?.length ? 'red flags in the plot’s history' : 'rule-based · check title before paying'}</small></div></section>
      {!restricted && record.verdict && <KpiStrip record={record} />}
      {record.verdict && <p className="report-disclaimer" role="note"><TriangleAlert size={14} /><span><strong>Not perfect, and not advice.</strong> TerraScope's answer is a rule-based estimate from public map and satellite data. The development outlook extends the past trend and can be wrong; nothing here predicts prices or verifies ownership. Check title, encumbrance and approvals with official records and a lawyer before paying.</span></p>}
      {olderEvaluation && <div className="older-note" role="note"><TriangleAlert size={15} /><span>This saved evaluation was made with an earlier version of TerraScope, so it lacks the current checks (the findings list, the buy / wait rules and what would change the answer). Re-evaluating uses the same evidence; nothing is collected again.</span><button className="quiet-button" disabled={busy} onClick={() => rerun(settings).catch(() => undefined)}><RefreshCw size={14} /> {busy ? 'Re-evaluating…' : 'Re-evaluate with current methods'}</button></div>}
      {scenarioError && !scenario && <div className="older-note error-note" role="alert"><TriangleAlert size={15} /><span>{scenarioError}</span></div>}
      {record.verdict?.reasoning_summary && !restricted && <p className="decision-lede">{record.verdict.reasoning_summary}</p>}
      {!restricted && <Highlights findings={record.verdict?.findings} />}
      <GovernmentLand record={record} />
      <>
      <DecisionPanel record={record} growth={factorOf('growth')} />
      <FacilitiesTable record={record} />
      <FindingsTable findings={record.verdict?.findings} />
      <div className="section-label suitability-divider">SUITABILITY FOR YOU — scored from your weights</div>
      <section className="score-strip"><Bar label="Legal Safety" value={breakdown?.legal_safety_score ?? null} color="#77d8ff" status={factorOf('legal_safety')?.status} /><Bar label="Accessibility" value={breakdown?.accessibility_score ?? null} color="#f8c15c" status={factorOf('accessibility')?.status} /><Bar label="Flood Safety" value={breakdown?.flood_safety_score ?? null} color="#d49aff" status={factorOf('flood_safety')?.status} /><Bar label="Area growth" value={breakdown?.growth_score ?? null} color="#b8f36a" status={factorOf('growth')?.status} /></section>
      <section className="evidence-status"><div className="section-head"><div><div className="section-label">EVIDENCE BEHIND EACH FACTOR</div><h2>What is measured, and what is scored</h2></div></div>
        <div className="coverage-figures"><div><span>SCORED</span><strong>{assessedWeight}%</strong><small>of your weighting has a score{scored.length ? ` (${scored.map(f => FACTOR_LABEL[f.factor] || f.factor).join(', ')})` : ''}</small></div><div><span>MEASURED</span><strong>{collectedCount} of {fieldCount}</strong><small>evidence fields collected for this parcel</small></div></div>
        <details className="denominators"><summary>How these two figures are counted</summary><p><strong>Scored</strong> adds up the weights of factors that have a score. {unscored.length ? `${unscored.map(f => `${FACTOR_LABEL[f.factor] || f.factor} (${f.weight_pct}%)`).join(', ')} ${unscored.length === 1 ? 'has' : 'have'} no score and ${unscored.length === 1 ? 'is' : 'are'} never filled in with 50. The composite is shared over the scored factors only. Unscored legal safety becomes the checks before you pay, and flood history can raise red flags. An unscored location factor (area growth, accessibility) withholds the decision.` : 'Every weighted factor has a score.'}</p><p><strong>Measured</strong> counts the evidence fields TerraScope tries to collect for every parcel ({record.metadata.data_completeness_pct ?? '—'}%). A field can be collected without being enough to score a factor: flood evidence is measured but not combined into a score.</p>{fields && <ul className="field-checks">{Object.entries(fields).map(([key, ok]) => <li key={key} className={ok ? 'ok' : 'missing'}>{ok ? '✓' : '—'} {COMPLETENESS_LABEL[key] || key}</li>)}</ul>}</details>
        <div className="factor-list">{[...factors].sort((a, b) => Number(b.score != null) - Number(a.score != null)).map(f => <div className={`factor ${f.status}`} key={f.factor}><div className="factor-head"><strong>{FACTOR_LABEL[f.factor] || f.factor.replace(/_/g, ' ')}</strong><span className={`factor-badge ${f.status}`}>{f.score == null ? (f.status === 'partial' ? 'partly assessed · not scored' : f.status.replace(/_/g, ' ')) : `${f.score} · ${f.status}`}</span><em>{f.weight_pct}% weight</em></div>
          <p>{f.factor === 'flood_safety' && record.flood_indicators?.components?.length ? `${floodHeadline(record.flood_indicators)}. The measurements are in the flood section below.` : f.basis}</p>
          {f.factor === 'accessibility' && <AccessibilityDetails factor={f} />}
          <small>{f.factor === 'flood_safety' ? 'No overall Flood Safety score: no validated method combines the mechanisms.' : f.limitations}</small>
          {f.checklist && f.checklist.length > 0 && <ul className="checklist">{f.checklist.map(c => <li key={c}>{c}</li>)}</ul>}
          {f.factor === 'legal_safety' && record.parcel_id && <><LegalEvidence record={record} onChanged={() => rerun(settings, 'Survey details or documents updated')} /><LegalChecks record={record} onChanged={() => rerun(settings, 'Legal check recorded')} /></>}
        </div>)}</div>
      </section>
      <FloodPanel indicators={record.flood_indicators} latitude={record.location?.latitude} />
      <section className="why-grid"><div><div className="section-label">WHY THIS RECOMMENDATION?</div><h2>Scored contributions</h2><div className="contribution-list">{(breakdown?.weighted_contributions || []).map((item, index) => <div key={index}><span>{FACTOR_LABEL[item.factor || ''] || item.factor || 'Unnamed factor'}</span><strong className={(item.contribution || 0) < 0 ? 'negative' : ''}>{(item.contribution || 0) > 0 ? '+' : ''}{item.contribution ?? '—'}</strong></div>)}{unscored.map(f => <div key={f.factor} className="unscored-row"><span>{FACTOR_LABEL[f.factor] || f.factor}</span><strong>no score · {f.weight_pct}%</strong></div>)}</div>{breakdown?.composite_score != null && <div className="final-verdict"><span>LOCATION SCORE · RULE-BASED, NOT A PROBABILITY</span><b>{breakdown.composite_score}</b></div>}{breakdown?.composite_score != null && verdict !== 'BUY' && <p className="field-hint">This score describes the location only (development and access). It never overrides a red flag or pending legal checks, so a high score here is not approval to buy.</p>}</div>
        <div className="grounded-box"><div className="section-label">{isAi ? <><Sparkles size={13} /> AI EXPLANATION</> : 'ASSESSMENT SUMMARY · RULE-BASED, NOT AI'}</div><p>{record.verdict?.reasoning_summary || 'No summary was returned for this evaluation.'}</p>
          <div className="citation-row"><span>{citations.length ? `${citations.length} evidence reference${citations.length === 1 ? '' : 's'}` : olderEvaluation ? 'No evidence references in this older evaluation; re-evaluate to add them' : 'No figure here needs a reference'}</span></div>
          {citations.length > 0 && <div className="citation-list">{citations.map((citation, index) => <div key={index}><strong>{citation.claim}</strong><small>{citation.source_type === 'user_upload' ? 'your document' : citation.source_type} · {citation.source_reference}{citation.location ? ` · ${citation.location}` : ''}</small></div>)}</div>}
        </div></section>
      <section className={`satellite-section${satelliteIsDemo ? ' synthetic' : ''}`}>{satelliteIsDemo && <div className="demo-banner"><TriangleAlert size={15} /> <strong>DEMO DATA.</strong> This curve is invented to exercise the chart. It is not imagery and shows nothing about real vegetation or construction.</div>}<div className="section-head"><div><div className="section-label">THE PLOT ITSELF IN RECENT SATELLITE IMAGES · OBSERVED MEASUREMENTS</div><h2>Greenness and built-up signals on the plot</h2><p className="chart-subtitle">Sentinel-2 satellite (10 m), average over the drawn plot on each clear date, {record.metadata.analysis_date_from || '—'} to {record.metadata.analysis_date_to || '—'}. Index values have no unit and run from −1 to +1.</p><p className="chart-finding">{changeFinding(record)}</p></div>{satelliteIsDemo ? <div className="signal-summary"><strong>demo series</strong><span>no figure: series is invented</span></div> : <ChangeSummary record={record} observations={chart.length} />}</div>{chart.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={250}><LineChart data={chart}><CartesianGrid stroke="#25313a" vertical={false} /><XAxis dataKey="date" stroke="#71808b" tickLine={false} axisLine={false} tickFormatter={(value: string) => value.slice(0, 7)} /><YAxis stroke="#71808b" tickLine={false} axisLine={false} width={52} label={{ value: 'Index (−1 to +1)', angle: -90, position: 'insideLeft', fill: '#71808b', fontSize: 11 }} /><Tooltip contentStyle={{ background: '#11191d', border: '1px solid #2d3b42' }} /><Line type="monotone" dataKey="ndvi" stroke="#b8f36a" strokeWidth={2} dot={{ r: 3 }} name="NDVI (greenness)" connectNulls={false} /><Line type="monotone" dataKey="ndbi" stroke="#f8c15c" strokeWidth={2} dot={{ r: 3 }} name="NDBI (built-up / bare surface signal)" connectNulls={false} /></LineChart></ResponsiveContainer></div> : <div className="chart-empty">{record.satellite?.collection?.status === 'timed_out' ? `Satellite collection did not finish within the ${record.satellite.collection.deadline_s ?? 35} s evidence deadline. The scene reads continue in the background and are cached: analyse this boundary again in a minute or two to reuse them.` : 'No usable satellite observations were found for this parcel and date range.'}</div>}
        {chart.length > 0 && <p className="history-legend"><span><i className="dot near" /> NDVI: greenness</span><span><i className="dot ndbi" /> NDBI: built-up or bare surface signal</span><span>Image date on the horizontal axis</span></p>}
        <details className="explain"><summary>What do these graphs mean?</summary>
          <p><strong>NDVI (greenness):</strong> calculated from how strongly the ground reflects red and near-infrared light. Healthy plants reflect a lot of near-infrared, so crops and trees give high values (about 0.5 and above), bare soil and roofs low values (around 0.1–0.2), and water is negative. It is an indicator of greenness, not a measurement of plant health or land value.</p>
          <p><strong>NDBI (built-up / bare surface signal):</strong> calculated from short-wave infrared and near-infrared light. Roofs, concrete and also bare dry soil push it up; vegetation and water push it down. It is not a building detector: a ploughed field can look similar to a new building. NDVI and NDBI measure different things and are not interchangeable.</p>
          <p><strong>Change detection:</strong> TerraScope compares images from the same season a year apart (so monsoon green is not mistaken for a change). <em>No material change</em> means the same-season pairs agree within a small margin. A <em>change class</em> (for example consistent with construction or vegetation loss) means they agree on a direction. <em>Inconclusive</em> means the pairs disagree or too few clear images exist, so no conclusion is drawn either way.</p>
          <p><strong>Past development vs this chart:</strong> the 2017–2023 built-up graph above is history of the surroundings; this chart is the plot itself over the analysis window. Neither is a forecast, and neither says anything about future prices.</p>
          <p><strong>What can mislead it:</strong> cloud and haze (cloudy pixels are removed, which can leave few dates), seasons (crops green up and are harvested), the 10 m pixel size (a small plot is only a few pixels), and mixed pixels at the plot edge that include a road or a neighbour's roof.</p>
        </details>
        {chart.length > 0 && chart.length < 4 && <p className="muted window-note">Only {chart.length} clear image date{chart.length === 1 ? '' : 's'}: too few to draw a conclusion about change on the plot.</p>}
        <div className="signal-foot"><span>{record.satellite?.change_method ? record.satellite.change_method.reason : record.satellite?.change_type ? 'Classified by the superseded v1 method, which fitted one straight line through all seasons and filed unclear movement under “no change”. Re-run the analysis for the seasonal comparison.' : 'Satellite signal unavailable.'}</span><span>Analysis period · {record.metadata.analysis_date_from || '—'} to {record.metadata.analysis_date_to || '—'}</span></div>
        {lateStart ? <p className="muted window-note">The first usable image is {imagery[0]}, months after the window starts ({windowStart}): the scene search used for this report stopped at the newest 100 catalogue entries. New analyses read the whole catalogue.</p> : null}
        {record.satellite?.collection?.selection && <p className="muted window-note">{record.satellite.collection.selection}; {record.satellite.collection.scenes_matched} scenes matched under {record.satellite.collection.max_cloud_cover_pct ?? 35}% cloud, {record.satellite.collection.observations_rejected ?? 0} read but rejected (under {Math.round((record.satellite.collection.min_clear_fraction ?? 0.5) * 100)}% of the parcel cloud-free){record.satellite.collection.anchors_without_observation?.length ? `; no usable scene near ${record.satellite.collection.anchors_without_observation.length} season anchor(s)` : ''}. Method {record.satellite.collection.algorithm_version}.</p>}
      </section>
      <section className="evidence-section"><div className="section-head"><div><div className="section-label">EVIDENCE LEDGER</div><h2>Sources behind the findings</h2></div></div><div className="tabs">{(['Satellite', 'Infrastructure', 'Flood indicators', 'RERA', 'Uploaded Documents', 'Derived Scores'] as EvidenceTab[]).map(tab => <button className={tab === activeEvidenceTab ? 'active' : ''} key={tab} onClick={() => setActiveEvidenceTab(tab)}>{tab}</button>)}</div><div className="source-legend ledger-legend"><span><i className="dot live" /> LIVE</span><span><i className="dot cached" /> CACHED</span><span><i className="dot user_upload" /> YOUR UPLOAD</span><span><i className="dot derived" /> DERIVED</span><span><i className="dot seed" /> SEED DATA</span></div>{visibleEvidence.length ? visibleEvidence.map(item => <EvidenceRow key={item.evidence_id || item.title} title={item.title || item.source_type || 'Evidence'} refName={item.source_reference || 'TerraScope'} freshness={item.freshness || 'derived'} summary={item.summary || 'Collected evidence used in the evaluation.'} observedAt={item.observed_at} details={[item.observation_period && `observed ${item.observation_period}`, item.resolution, item.licence].filter(Boolean).join(' · ')} />) : <p className="muted evidence-empty">No {activeEvidenceTab.toLowerCase()} evidence is available for this parcel.</p>}</section>
      </>
    </div>
    {scenario && <Scenario settings={settings} verdict={verdict} before={breakdown?.composite_score ?? null} accessibility={breakdown?.accessibility_score ?? null} busy={busy} error={scenarioError} onClose={() => setScenario(false)} onRun={(next, changed) => rerun(next, changed).catch(() => undefined)} />}
    {historyOpen && <div className="drawer-backdrop" onClick={() => setHistoryOpen(false)}><aside className="history-drawer" onClick={event => event.stopPropagation()}><div className="drawer-header"><div><div className="panel-kicker">DECISION TRAIL</div><h2>Scenario history</h2></div><button className="icon-button" aria-label="Close" onClick={() => setHistoryOpen(false)}><X size={18} /></button></div><div className="history-list">{history.length ? history.map((item, index) => <div className="history-item" key={index}><div><strong>{item.profile}</strong><span>{item.changed}</span></div><b>{VERDICT_LABEL[item.verdict] || item.verdict}</b></div>) : <p className="muted">No alternate lenses explored yet. The immutable evidence stays fixed while you test assumptions.</p>}</div></aside></div>}
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
  return <div className="drawer-backdrop" onClick={onClose}><aside className="scenario-drawer" onClick={event => event.stopPropagation()}><div className="drawer-header"><div><div className="panel-kicker">SCENARIO MODE</div><h2>Explore scenarios</h2></div><button className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button></div><div className="drawer-scroll"><p className="drawer-intro flush">Change an assumption and re-evaluate the same evidence. Nothing is collected again.</p><div className="scenario-score flush"><div><span>BEFORE</span><strong>{VERDICT_LABEL[verdict] || verdict} · {before ?? '—'}</strong></div><div><span>ACCESSIBILITY</span><strong>{accessibility ?? '—'}</strong></div></div>
    <label className="field-label">FLOOD SAFETY WEIGHT <strong>{flood}%</strong></label><input className="scenario-range flush" aria-label="Flood safety weight (percent)" type="range" min="0" max={maxFlood} value={Math.min(flood, maxFlood)} onChange={event => change(Number(event.target.value))} />
    <label className="field-label">ACCESSIBILITY LIMITS <span>score reaches 0 at the limit</span></label>
    <div className="slider-row"><span>Road within</span><strong>{p.max_road_distance_m.toLocaleString()} m</strong><input type="range" min="100" max="5000" step="100" value={p.max_road_distance_m} onChange={e => pref('max_road_distance_m', Number(e.target.value))} aria-label="Maximum road distance in metres" /></div>
    <div className="slider-row"><span>School within</span><strong>{p.max_school_distance_m.toLocaleString()} m</strong><input type="range" min="100" max="5000" step="100" value={p.max_school_distance_m} onChange={e => pref('max_school_distance_m', Number(e.target.value))} aria-label="Maximum school distance in metres" /></div>
    <div className="two-col"><label>Road importance<select value={p.road_importance} onChange={e => pref('road_importance', e.target.value as EvaluationSettings['preferences']['road_importance'])}><option>low</option><option>medium</option><option>high</option></select></label><label>School importance<select value={p.school_importance} onChange={e => pref('school_importance', e.target.value as EvaluationSettings['preferences']['school_importance'])}><option>low</option><option>medium</option><option>high</option></select></label></div>
    <p className="field-hint">Distances are straight lines from the parcel boundary (older reports: from its centroid) to OpenStreetMap features. They are not travel distances and not proof of legal access.</p>
    {error && <p className="form-error">{error}</p>}</div><div className="drawer-footer"><button className="primary-button scenario-apply" disabled={busy || changed === 'no change'} onClick={() => onRun(local, changed)}>{busy ? 'Re-evaluating…' : 'Apply scenario'}</button></div></aside></div>
}
