import { useEffect, useState } from 'react'
import { ParcelRecord } from '../lib/api'

/** The evidence collectors stop at this many seconds (EVIDENCE_COLLECTION_DEADLINE_SECONDS, data-pipeline default). */
const HISTORY_KEY = 'terrascope.analysisSeconds'

type Layer = { key: string; label: string; found: boolean; detail: string; ms: number | null }

const m = (v: number | null | undefined) => v == null ? null : v >= 1000 ? `${(v / 1000).toFixed(1)} km` : `${Math.round(v)} m`

/** What each collector actually returned, in the order the backend measured them finishing. Nothing here is inferred. */
export function collectedLayers(s: ParcelRecord): Layer[] {
  const t = s.metadata.collection_timings_ms || {}
  const infra = s.infrastructure
  const roadsMissing = infra?.layer_status?.road === 'not_installed'
  const road = infra?.nearest_road_distance_from_boundary_m ?? infra?.nearest_road_distance_m
  const images = (s.satellite?.imagery_dates || []).filter(Boolean).length
  const river = s.flood_indicators?.river_flood as { status?: string } | null | undefined
  const layers: Layer[] = [
    { key: 'geocoding', label: 'Location', found: Boolean(s.location?.state), detail: [s.location?.district, s.location?.state].filter(Boolean).join(', ') || 'no address found', ms: t.geocoding ?? null },
    { key: 'satellite', label: 'Satellite images', found: images > 0,
      // A provider failure is not "no clear images": say which happened.
      detail: images ? `${images} clear image date${images === 1 ? '' : 's'}`
        : s.satellite?.collection?.status === 'timed_out' ? 'imagery service too slow; run the analysis again'
        : s.satellite?.collection?.error ? 'imagery service did not respond; run the analysis again'
        : 'no clear images in the window', ms: t.satellite ?? null },
    { key: 'accessibility', label: 'Roads, schools, hospitals', found: road != null || infra?.nearest_school_distance_m != null,
      detail: [roadsMissing ? 'roads not installed for this region' : road != null ? `road ${m(road)}` : 'no road mapped nearby',
               infra?.nearest_school_distance_m != null ? `school ${m(infra.nearest_school_distance_m)}` : null].filter(Boolean).join(' · '), ms: t.accessibility ?? null },
    { key: 'terrain', label: 'Elevation', found: s.risk?.elevation_m != null, detail: s.risk?.elevation_m != null ? `${s.risk.elevation_m.toFixed(1)} m` : 'not available', ms: t.terrain ?? null },
    { key: 'river_flood', label: 'River flood maps', found: river?.status === 'assessed' || river?.status === 'partial', detail: river?.status ? river.status.replace('_', ' ') : 'not available', ms: t.river_flood ?? null },
    { key: 'flood_indicators', label: 'Surface water history', found: Boolean(s.flood_indicators?.surface_water), detail: s.flood_indicators?.surface_water ? '1984-2021 read' : 'not available', ms: t.flood_indicators ?? null },
    { key: 'land_cover', label: 'Area development 2017-2023', found: s.land_cover_history?.status === 'assessed', detail: s.land_cover_history?.status || 'not available', ms: t.land_cover ?? null },
  ]
  return layers.sort((a, b) => (a.ms ?? Infinity) - (b.ms ?? Infinity))
}

function recentSeconds(): number[] {
  try { return (JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]') as number[]).filter(n => typeof n === 'number') } catch { return [] }
}

/** Remember how long collection took in this browser, to estimate the next one (never shared, never required). */
export function rememberCollection(seconds: number) {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify([...recentSeconds(), seconds].slice(-5))) } catch { /* not remembered */ }
}

export function AnalysisOverlay({ stage, stages, startedAt, collected, onOpen }: {
  stage: number; stages: string[]; startedAt: number; collected: ParcelRecord | null; onOpen: () => void
}) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 250); return () => clearInterval(id) }, [])
  const elapsed = (now - startedAt) / 1000
  const ready = stage === stages.length - 1
  const layers = collected ? collectedLayers(collected) : []
  const timeLine = collected
    ? `Evidence collected in ${((collected.metadata.collection_timings_ms && Math.max(0, ...Object.values(collected.metadata.collection_timings_ms).map(v => v ?? 0)) || 0) / 1000).toFixed(1)} s${ready ? '' : ' · scoring'}`
    : `${Math.floor(elapsed)} s elapsed · evidence collectors are running in parallel`
  return <div className="analysis-overlay"><div className="analysis-card">
    <div className="scanner" aria-hidden="true"><span className="scan-grid" /><span className="scan-line" /><span className="scan-blip b1" /><span className="scan-blip b2" /><span className="scan-blip b3" /></div>
    <div className="eyebrow"><span className="pulse" /> {ready ? 'ANALYSIS READY' : 'LIVE EVIDENCE COLLECTION'}</div>
    <h2>{ready ? 'Found what the data holds.' : collected ? 'Evidence found. Scoring…' : 'Reading this parcel.'}</h2>
    <p className="analysis-time" role="status">{timeLine}</p>
    <div className="analysis-progress" role="progressbar" aria-valuemin={0} aria-valuemax={stages.length - 1} aria-valuenow={Math.max(0, stage)}><i style={{ width: `${collected ? Math.round((Math.max(1, stage) / (stages.length - 1)) * 100) : 18}%` }} /></div>
    {collected
      ? <div className="stage-list found-list">{layers.map((l, i) => <div className={l.found ? 'done reveal' : 'missing reveal'} style={{ animationDelay: `${i * 120}ms` }} key={l.key}><span>{l.found ? '✓' : '–'}</span><strong>{l.found ? 'Found' : 'Not available'}</strong>&nbsp;{l.label}: {l.detail}{l.ms != null && <small> · {(l.ms / 1000).toFixed(1)} s</small>}</div>)}</div>
      : <div className="stage-list">{stages.map((x, i) => <div className={i === stage ? 'current' : ''} key={x}><span>{i === stage ? <i className="stage-spinner" /> : '·'}</span>{x}</div>)}</div>}
    {ready && <button className="primary-button" onClick={onOpen}>Open evidence report</button>}
  </div></div>
}
