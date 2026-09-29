import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import { Search } from './pages/Search'
import { ParcelWorkspace, SQFT_PER_SQM } from './pages/ParcelWorkspace'
import { Report } from './pages/Report'
import { estimateValuation, EvaluationSettings, getSavedParcel, ParcelRecord, PropertyDetails, Valuation } from './lib/api'

type OpenReport = { snapshot: ParcelRecord; settings: EvaluationSettings; property: PropertyDetails | null; valuation: Valuation | null }

const fallbackSettings: EvaluationSettings = {
  profile: 'homebuyer', property_type: 'residential', investment_horizon: '1_to_3y',
  weights: { growth_pct: 20, legal_safety_pct: 35, accessibility_pct: 25, flood_safety_pct: 20 },
  preferences: { road_importance: 'medium', school_importance: 'high', max_road_distance_m: 3000, max_school_distance_m: 5000, rera_requirement: 'important' },
}

/** Re-price a reopened report against the current model, rather than showing a stale number. */
async function revalue(snapshot: ParcelRecord, property: PropertyDetails): Promise<Valuation | null> {
  const latitude = snapshot.location?.latitude, longitude = snapshot.location?.longitude
  const areaM2 = snapshot.geometry_metadata?.area_m2
  const areaSqft = property.area_sqft_override ?? (typeof areaM2 === 'number' ? areaM2 * SQFT_PER_SQM : null)
  if (typeof latitude !== 'number' || typeof longitude !== 'number' || !areaSqft || areaSqft <= 0) return null
  try {
    return await estimateValuation({ latitude, longitude, area_sqft: areaSqft, land_use: property.land_use, price_basis: property.price_basis })
  } catch (error) {
    return { status: 'unavailable', reason: 'request_failed', detail: error instanceof Error ? error.message : 'The valuation service could not be reached.' }
  }
}

function App() {
  const [place, setPlace] = useState<{ lat: number; lon: number; label: string } | null>(null)
  const [report, setReport] = useState<OpenReport | null>(null)
  const [opening, setOpening] = useState('')

  async function openSaved(parcelId: string) {
    setOpening(parcelId)
    try {
      const saved = await getSavedParcel(parcelId)
      const snapshot = saved.latest_evaluation || saved.evidence_snapshot
      const property: PropertyDetails = {
        land_use: (snapshot.evaluation?.property_type === 'mixed_use' ? 'mixed_use' : snapshot.evaluation?.property_type) as PropertyDetails['land_use'] || 'residential',
        price_basis: 'transaction',
        area_sqft_override: null,
      }
      setReport({ snapshot, settings: snapshot.evaluation || fallbackSettings, property, valuation: await revalue(snapshot, property) })
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'That saved report could not be opened.')
    } finally {
      setOpening('')
    }
  }

  if (report) return <Report initialSnapshot={report.snapshot} initialSettings={report.settings} valuation={report.valuation} property={report.property} onBack={() => setReport(null)} />
  if (!place) return <Search onSubmit={setPlace} onOpenSaved={openSaved} openingParcelId={opening} />
  return <ParcelWorkspace search={place} onBack={() => setPlace(null)} onReport={(snapshot, settings, property, valuation) => setReport({ snapshot, settings, property, valuation })} />
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
