import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import { Search } from './pages/Search'
import { ParcelWorkspace, Point } from './pages/ParcelWorkspace'
import { Report } from './pages/Report'
import { EvaluationSettings, getSavedParcel, ParcelRecord } from './lib/api'

type OpenReport = { snapshot: ParcelRecord; settings: EvaluationSettings }

const fallbackSettings: EvaluationSettings = {
  profile: 'homebuyer', property_type: 'residential', investment_horizon: '1_to_3y',
  weights: { growth_pct: 20, legal_safety_pct: 35, accessibility_pct: 25, flood_safety_pct: 20 },
  preferences: { road_importance: 'medium', school_importance: 'high', max_road_distance_m: 3000, max_school_distance_m: 5000, rera_requirement: 'important' },
}

function App() {
  const [place, setPlace] = useState<{ lat: number; lon: number; label: string } | null>(null)
  const [boundary, setBoundary] = useState<Point[]>([])
  const [report, setReport] = useState<OpenReport | null>(null)
  const [opening, setOpening] = useState('')

  // The open report is in the URL, so a browser refresh reopens it instead of dropping to search.
  useEffect(() => {
    const match = window.location.hash.match(/^#report\/([\w-]+)$/)
    if (match) openSaved(match[1])
  }, [])
  useEffect(() => {
    const next = report?.snapshot.parcel_id ? `#report/${report.snapshot.parcel_id}` : ''
    if (window.location.hash !== next) window.history.replaceState(null, '', next || window.location.pathname)
  }, [report])

  async function openSaved(parcelId: string) {
    setOpening(parcelId)
    try {
      const saved = await getSavedParcel(parcelId)
      const snapshot = saved.latest_evaluation || saved.evidence_snapshot
      setReport({ snapshot, settings: snapshot.evaluation || fallbackSettings })
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'That saved report could not be opened.')
    } finally {
      setOpening('')
    }
  }

  if (report) return <Report initialSnapshot={report.snapshot} initialSettings={report.settings} onBack={() => setReport(null)} />
  if (!place) return <Search onSubmit={next => { setPlace(next); setBoundary([]) }} onOpenSaved={openSaved} openingParcelId={opening} />
  return <ParcelWorkspace search={place} points={boundary} onPointsChange={setBoundary} onBack={() => setPlace(null)} onReport={(snapshot, settings) => setReport({ snapshot, settings })} />
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
