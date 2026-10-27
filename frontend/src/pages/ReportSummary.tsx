import { ReactNode } from 'react'
import { CircleCheck, CircleHelp, MapPin, Route, Scale, ShieldAlert, TriangleAlert, Waves } from 'lucide-react'
import { GeoJSON, MapContainer, TileLayer } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Finding, ParcelRecord } from '../lib/api'

/** good / warn / bad / unknown: always shown with a text label and an icon, never by colour alone. */
export type Tone = 'good' | 'warn' | 'bad' | 'unknown'
type KeyFinding = { key: string; title: string; icon: ReactNode; status: string; tone: Tone; text: string; why: string }

const TONE_ICON: Record<Tone, ReactNode> = {
  good: <CircleCheck size={15} aria-hidden="true" />, warn: <TriangleAlert size={15} aria-hidden="true" />,
  bad: <ShieldAlert size={15} aria-hidden="true" />, unknown: <CircleHelp size={15} aria-hidden="true" />,
}
const km = (m: number) => m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
const firstSentence = (text: string) => (text.match(/^.*?[.!?](\s|$)/)?.[0] || text).trim()

function legalVerified(record: ParcelRecord) {
  const r = record.land_records as unknown as Record<string, unknown> | null
  return !!r && r.title_clear === true && r.encumbrance_flag === false && r.zoning_verified === true && r.approvals_verified === true
}

/** The decision in plain words: the backend's recommendation, never re-decided here. */
export function plainAssessment(record: ParcelRecord): { label: string; tone: Tone; sentence: string } {
  const v = record.verdict
  const rec = v?.recommendation
  const gov = v?.government_land
  const developing = v?.development_outlook?.status === 'growing_fast' || v?.development_outlook?.status === 'growing_slowly'
  if (!v || !rec) return { label: 'Not evaluated', tone: 'unknown', sentence: 'This report has no assessment yet. Re-evaluate it to see one.' }
  if (rec === 'RESTRICTED') return { label: 'Verify restriction', tone: 'bad', sentence: 'The boundary overlaps mapped restricted land (listed below). TerraScope does not assess restricted land for purchase; check the official land records.' }
  if (rec === 'AVOID') return { label: 'Walk away', tone: 'bad', sentence: `A serious problem was found: ${firstSentence((v.red_flags?.[0] || v.reasoning_summary).replace(/^WALK AWAY:\s*/, ''))} Do not pay unless it is explained.` }
  // A built-out area's growth is measured but deliberately unscored ("established"): only an unavailable factor is missing.
  const missing = (record.score_breakdown?.factors || []).filter(f => (f.factor === 'growth' || f.factor === 'accessibility') && f.status === 'unavailable')
    .map(f => f.factor === 'growth' ? 'the area’s development history' : 'road access')
  // Missing location evidence is a Wait, never a Buy; older reports stored it as INSUFFICIENT_EVIDENCE.
  if (rec === 'INSUFFICIENT_EVIDENCE' || (rec === 'WAIT' && missing.length)) return { label: 'Wait', tone: 'warn', sentence: `TerraScope could not measure ${missing.length ? missing.join(' or ') : 'all of the location'} for this plot, so it cannot recommend buying yet. Re-analyse once the data is available, and complete the legal checks below.` }
  if (rec === 'BUY' && legalVerified(record)) return { label: 'Buy', tone: 'good', sentence: 'The location is strong and the legal checks are verified from official records. Still confirm everything with a lawyer before paying.' }
  if (rec === 'BUY') return { label: 'Buy after checks', tone: 'warn', sentence: `The location is strong${developing ? ' and the area has been developing' : ''}, but ownership, loans on the land and approvals have not been verified. Buy only once the checks below are complete.` }
  if (gov?.hold) return { label: 'Wait', tone: 'warn', sentence: 'The plot may overlap public or restricted land on the map. Rule this out with official records before going further.' }
  return { label: 'Wait', tone: 'warn', sentence: 'The location evidence is not strong enough yet, and ownership and approvals have not been verified. Look at the details below before committing money.' }
}

export function keyFindings(record: ParcelRecord): KeyFinding[] {
  const findings = record.verdict?.findings || []
  const row = (area: string): Finding | undefined => findings.find(f => f.area === area)
  const title = row('Title and ownership'), river = row('River flooding'), coastal = row('Coastal flooding'), water = row('Water on the plot, 1984-2021')
  const recorded = Object.keys((record as unknown as { user_legal_checks?: Record<string, unknown> }).user_legal_checks || {}).length
  const access = record.score_breakdown?.factors?.find(f => f.factor === 'accessibility')
  const infra = record.infrastructure
  const road = infra?.nearest_road_distance_from_boundary_m ?? infra?.nearest_road_distance_m
  const school = infra?.nearest_school_distance_from_boundary_m ?? infra?.nearest_school_distance_m
  const gov = record.verdict?.government_land
  const flags = record.verdict?.red_flags || []

  const legal: KeyFinding = title?.assessment === 'red_flag'
    ? { key: 'legal', title: 'Legal verification', icon: <Scale size={18} />, status: 'Problem recorded', tone: 'bad', text: title.finding, why: '' }
    : legalVerified(record)
      ? { key: 'legal', title: 'Legal verification', icon: <Scale size={18} />, status: 'Verified', tone: 'good', text: 'Ownership, loans on the land, zoning and approvals match official records.', why: '' }
      : { key: 'legal', title: 'Legal verification', icon: <Scale size={18} />, status: 'Not verified', tone: 'warn', why: '',
          text: `Ownership, outstanding loans and approvals have not been checked against official records.${recorded ? ` You have recorded ${recorded} check${recorded === 1 ? '' : 's'}; these are your records, not verification.` : ' TerraScope cannot read land records.'}` }
  legal.why = 'Most land disputes come from an unclear owner, an unpaid loan on the land, or a layout without approval. Only official records and a lawyer can rule these out.'

  const coastalNote = coastal && /km from the sea/.test(coastal.finding) ? ` It is ${coastal.finding.match(/([\d.]+ km) from the sea/)?.[1]} from the sea; coastal flooding is not assessed.` : ''
  const flood: KeyFinding = river?.assessment === 'red_flag'
    ? { key: 'flood', title: 'Flood risk', icon: <Waves size={18} />, status: 'Serious risk', tone: 'bad', text: river.finding, why: '' }
    : river?.assessment === 'caution'
      ? { key: 'flood', title: 'Flood risk', icon: <Waves size={18} />, status: 'Some risk', tone: 'warn', text: `${river.finding} Rainwater flooding has not been assessed.${coastalNote}`, why: '' }
      : river?.assessment === 'ok'
        ? { key: 'flood', title: 'Flood risk', icon: <Waves size={18} />, status: 'Partly assessed', tone: 'unknown', text: `The available river-flood model did not identify flooding here. Rainwater flooding and local drainage have not been assessed.${coastalNote}`, why: '' }
        : { key: 'flood', title: 'Flood risk', icon: <Waves size={18} />, status: 'Not assessed', tone: 'unknown', text: `River flood maps could not be read for this plot, and rainwater flooding is not assessed.${coastalNote} Unknown is not safe.`, why: '' }
  flood.why = 'Flooding damages buildings and cuts off roads. The river model covers large rivers only (about 90 m detail); waterlogging after heavy rain depends on local drainage, which TerraScope does not check. Ask neighbours how the area fares in the monsoon.'

  const roadsMissing = infra?.layer_status?.road === 'not_installed'
  const score = access?.score
  const distances = [road != null ? `nearest mapped road ${km(road)}` : null, school != null ? `school ${km(school)}` : null].filter(Boolean).join(', ')
  const reach: KeyFinding = score == null
    ? { key: 'access', title: 'Roads and facilities', icon: <Route size={18} />, status: 'Unknown', tone: 'unknown', why: '',
        text: roadsMissing ? 'Road data is not installed for this region, so access was not assessed. Unknown is not the same as no road.' : 'Access could not be assessed for this plot.' }
    : { key: 'access', title: 'Roads and facilities', icon: <Route size={18} />, status: score >= 75 ? 'Good access' : score >= 50 ? 'Fair access' : 'Limited access', tone: score >= 75 ? 'good' : 'warn', why: '',
        text: `Based on mapped roads and schools${distances ? ` (${distances}, straight line)` : ''}. Actual travel routes and legal road access have not been verified.` }
  reach.why = 'A plot without a usable road is hard to build on and to resell. A mapped road nearby does not prove a legal right of way to your plot: check the access road in the sale documents.'

  const restrict: KeyFinding = gov?.walk_away || record.verdict?.recommendation === 'RESTRICTED'
    ? { key: 'restrict', title: 'Restrictions and hazards', icon: <ShieldAlert size={18} />, status: 'Serious problem', tone: 'bad', text: gov?.warning || '', why: '' }
    : flags.length
      ? { key: 'restrict', title: 'Restrictions and hazards', icon: <ShieldAlert size={18} />, status: 'Red flag', tone: 'bad', text: flags[0], why: '' }
      : gov?.hold
        ? { key: 'restrict', title: 'Restrictions and hazards', icon: <ShieldAlert size={18} />, status: 'Check needed', tone: 'warn', text: gov.warning.replace(/^WARNING:\s*/, ''), why: '' }
        : water && (water.assessment === 'caution' || water.assessment === 'red_flag')
          ? { key: 'restrict', title: 'Restrictions and hazards', icon: <ShieldAlert size={18} />, status: 'Check needed', tone: 'warn', text: water.finding, why: '' }
          : { key: 'restrict', title: 'Restrictions and hazards', icon: <ShieldAlert size={18} />, status: record.public_land?.status === 'assessed' ? 'None mapped' : 'Not checked', tone: 'unknown', why: '',
              text: record.public_land?.status === 'assessed' ? 'No mapped public facility, railway, defence area or water body overlaps this plot, but ownership is unverified and maps can be incomplete.' : 'Public land and restrictions were not checked for this report. Analyse the boundary again to add the check.' }
  restrict.why = 'Government land, water bodies (often poramboke land), railway and defence land usually cannot be bought or built on. A map can be incomplete or slightly off, so nothing on the map is not proof the land is free of restrictions.'
  return [legal, flood, reach, restrict]
}

/** A small, fixed map of the drawn boundary, for orientation only. */
function ParcelThumb({ geometry }: { geometry: NonNullable<ParcelRecord['geometry']> }) {
  const bounds = L.geoJSON(geometry as GeoJSON.GeoJsonObject).getBounds().pad(0.6)
  return <figure className="parcel-thumb" aria-label="Map of the selected plot">
    <MapContainer bounds={bounds} zoomControl={false} dragging={false} scrollWheelZoom={false} doubleClickZoom={false} touchZoom={false} boxZoom={false} keyboard={false} attributionControl={false}>
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />
      <GeoJSON data={geometry as GeoJSON.GeoJsonObject} style={{ color: '#b8f36a', weight: 2.5, fillOpacity: 0.18 }} />
    </MapContainer>
    <figcaption>Your drawn boundary · map © OpenStreetMap contributors</figcaption>
  </figure>
}

/** Where the plot is: the drawn centre's coordinates, and the survey number only as the buyer entered it. */
function PlotIds({ record }: { record: ParcelRecord }) {
  const { latitude: lat, longitude: lon } = record.location || {}
  const land = record.user_land_details
  const survey = land?.survey_number ? `${land.survey_number}${land.subdivision ? `/${land.subdivision}` : ''}` : null
  return <dl className="plot-ids">
    <div><dt>Coordinates (centre of the drawn plot)</dt><dd>{lat != null && lon != null ? `${lat.toFixed(6)}° N, ${lon.toFixed(6)}° E` : 'Not recorded'}</dd></div>
    <div><dt>Survey number</dt><dd>{survey
      ? <>{survey}{land?.village ? `, ${land.village}` : ''}{land?.taluk ? `, ${land.taluk} taluk` : ''} <small>entered by you, not verified</small></>
      : <small>Not entered. TerraScope cannot look it up: add it under “Parcel identifiers” below, then verify it through the official source.</small>}</dd></div>
  </dl>
}

/** The first screen: where, how big, when, the decision in one sentence, and the four things that matter most. */
export function SummaryCard({ record, place, areaControl, period }: { record: ParcelRecord; place: string; areaControl: ReactNode; period: string }) {
  const a = plainAssessment(record)
  const restricted = record.verdict?.recommendation === 'RESTRICTED'
  const access = record.score_breakdown?.factors?.find(f => f.factor === 'accessibility')?.score
  const river = record.verdict?.findings?.find(f => f.area === 'River flooding')
  return <section className="summary-card" aria-label="Assessment summary">
    <div className="summary-place">
      <p className="summary-kicker"><MapPin size={14} aria-hidden="true" /> Property location</p>
      <h1>{place}</h1>
      {record.location?.address && <p className="summary-address">{record.location.address}</p>}
      <p className="summary-meta">{areaControl}<span aria-hidden="true">·</span><span>Analysed for {period}</span></p>
      {record.geometry && <ParcelThumb geometry={record.geometry} />}
      <PlotIds record={record} />
    </div>
    <div className={`summary-verdict ${a.tone}`}>
      <p className="summary-kicker">Current assessment</p>
      <p className="summary-status">{TONE_ICON[a.tone]} {a.label}</p>
      <p className="summary-sentence">{a.sentence}</p>
    </div>
    {!restricted && record.verdict && <>
      <ul className="key-findings" aria-label="Key findings">{keyFindings(record).map(f => <li key={f.key} className={`key-finding ${f.tone}`}>
        <div className="key-head">{f.icon}<strong>{f.title}</strong><span className={`status-pill ${f.tone}`}>{TONE_ICON[f.tone]} {f.status}</span></div>
        <p>{f.text}</p>
        <details><summary>Why does this matter?</summary><p>{f.why}</p></details>
      </li>)}</ul>
      <dl className="at-a-glance">
        <div><dt>Accessibility</dt><dd>{access == null ? 'Unknown' : `${Math.round(access)} / 100`}</dd></div>
        <div><dt>Legal checks</dt><dd>{legalVerified(record) ? 'Complete' : 'Incomplete'}</dd></div>
        <div><dt>Flood assessment</dt><dd>{river && river.assessment !== 'unknown' ? 'Partial (rivers only)' : 'Not assessed'}</dd></div>
        <div><dt>Overall</dt><dd>{a.label}</dd></div>
      </dl>
    </>}
  </section>
}
