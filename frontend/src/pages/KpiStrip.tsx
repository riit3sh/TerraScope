import { ParcelRecord } from '../lib/api'

type Tone = 'ok' | 'caution' | 'red_flag' | 'unknown'
type Tile = { label: string; value: string; sub: string; tone: Tone; meter?: number }

const metres = (v: number | null | undefined) => v == null ? null : v >= 1000 ? `${(v / 1000).toFixed(1)} km` : `${Math.round(v)} m`

/** The report's headline numbers in one row. Every value is read from the evaluation; unknowns stay unknown. */
export function tiles(record: ParcelRecord): Tile[] {
  const breakdown = record.score_breakdown
  const findings = record.verdict?.findings || []
  const row = (area: string) => findings.find(f => f.area === area)
  const score = breakdown?.composite_score
  const trend = record.land_cover_history?.trend_within_1km
  const infra = record.infrastructure
  const road = infra?.nearest_road_distance_from_boundary_m ?? infra?.nearest_road_distance_m
  const school = infra?.nearest_school_distance_from_boundary_m ?? infra?.nearest_school_distance_m
  const roadsMissing = infra?.layer_status?.road === 'not_installed'
  const river = row('River flooding')
  const title = row('Title and ownership')
  const records = record.land_records as unknown as Record<string, unknown> | null | undefined
  const verifiedChecks = records ? [records.title_clear === true, records.encumbrance_flag === false, records.zoning_verified === true, records.approvals_verified === true].filter(Boolean).length : 0
  const gov = record.verdict?.government_land
  const outlook = record.verdict?.development_outlook
  const y2030 = outlook?.projections?.find(p => p.year === 2030)
  const pct = (v: number) => `${Math.round(v * 100)}%`
  return [
    { label: 'LOCATION SCORE', value: score == null ? 'Not scored' : `${Math.round(score)}`, meter: score ?? undefined,
      sub: score == null ? 'missing evidence withholds it' : `of 100 · strong from 75 · rule-based, not a probability`,
      tone: score == null ? 'unknown' : score >= 75 ? 'ok' : 'caution' },
    { label: 'AREA DEVELOPMENT', value: trend ? (y2030 ? `${pct(trend.last_share)} → ~${pct(y2030.share)}` : `${pct(trend.last_share)} built`) : 'Unknown',
      sub: trend ? (y2030 ? `built within 1 km: ${trend.last_year} measured, 2030 projected (${pct(y2030.low)}–${pct(y2030.high)}); a trend, not a guarantee`
                          : `within 1 km in ${trend.last_year}; ${trend.slope_pts_per_year >= 0 ? '+' : ''}${trend.slope_pts_per_year.toFixed(1)} pts a year since ${trend.first_year} (history)`) : 'no land-cover history in this report',
      tone: trend ? (outlook?.status === 'flat' ? 'caution' : 'ok') : 'unknown' },
    { label: 'ROAD AND SCHOOL', value: roadsMissing ? 'Roads unknown' : road != null ? `Road ${metres(road)}` : 'No road mapped',
      sub: roadsMissing ? 'road data not installed for this region' : `${school != null ? `school ${metres(school)}` : 'no school mapped nearby'} · straight line, not legal access`,
      tone: roadsMissing ? 'unknown' : road != null && road <= 500 ? 'ok' : 'caution' },
    { label: 'RIVER FLOODING', value: !river ? 'Unknown' : river.assessment === 'red_flag' ? 'Red flag' : river.assessment === 'caution' ? 'Caution' : river.assessment === 'ok' ? 'None modelled' : 'Unknown',
      sub: 'modelled river floods only; rainfall and coastal not assessed', tone: (river?.assessment as Tone) || 'unknown' },
    { label: 'LEGAL CHECKS', value: `${verifiedChecks} of 4 verified`,
      sub: verifiedChecks === 4 ? 'from matched official records' : 'title, EC, zoning, approvals: check before paying',
      tone: title?.assessment === 'red_flag' ? 'red_flag' : verifiedChecks === 4 ? 'ok' : 'caution' },
    { label: 'GOVERNMENT LAND', value: gov ? (gov.walk_away ? 'Problem' : gov.hold ? 'Check needed' : 'Unverified') : 'Not checked',
      sub: gov ? gov.label : 're-evaluate to add this check', tone: gov?.walk_away ? 'red_flag' : gov?.hold ? 'caution' : 'unknown' },
  ]
}

export function KpiStrip({ record }: { record: ParcelRecord }) {
  return <section className="kpi-strip" aria-label="Key figures">{tiles(record).map(t => <div className={`kpi ${t.tone}`} key={t.label}>
    <span className="kpi-label">{t.label}</span>
    <strong>{t.value}</strong>
    {t.meter != null && <i className="kpi-meter" aria-hidden="true"><b style={{ width: `${Math.max(0, Math.min(100, t.meter))}%` }} /><em style={{ left: '75%' }} /></i>}
    <small>{t.sub}</small>
  </div>)}</section>
}
