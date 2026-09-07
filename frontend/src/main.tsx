import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import { Search } from './pages/Search'
import { ParcelWorkspace } from './pages/ParcelWorkspace'
import { Report } from './pages/Report'
import { EvaluationSettings, ParcelRecord } from './lib/api'

function App() { const [place, setPlace] = useState<{ lat: number; lon: number; label: string } | null>(null); const [report, setReport] = useState<{ snapshot: ParcelRecord; settings: EvaluationSettings } | null>(null); if (report) return <Report initialSnapshot={report.snapshot} initialSettings={report.settings} onBack={() => setReport(null)} />; if (!place) return <Search onSubmit={setPlace} />; return <ParcelWorkspace search={place} onReport={(snapshot, settings) => setReport({ snapshot, settings })} /> }
createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
