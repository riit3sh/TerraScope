import { ArrowRight, Clock, FileText, MapPin, Search as SearchIcon, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { geocodeAddress, listSavedReports, PlaceSuggestion, SavedReport, suggestPlaces } from '../lib/api'
import { acresToM2, formatArea, useAreaUnit } from '../lib/area'

export function Search({ onSubmit, onOpenSaved, openingParcelId }: { onSubmit: (place: { lat: number; lon: number; label: string }) => void; onOpenSaved: (parcelId: string) => void; openingParcelId: string }) {
  const [query, setQuery] = useState('')
  const [areaUnit] = useAreaUnit()
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([])
  const [activeIndex, setActiveIndex] = useState(-1)
  const [selected, setSelected] = useState<PlaceSuggestion | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [suggestError, setSuggestError] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const [saved, setSaved] = useState<SavedReport[]>([])
  const [showAllSaved, setShowAllSaved] = useState(false)
  const RECENT_SAVED = 6

  useEffect(() => { listSavedReports().then(setSaved).catch(() => setSaved([])) }, [])

  // Suggestions come from the local place index (milliseconds), so a short debounce
  // is enough; a newer keystroke aborts the older request instead of racing it.
  useEffect(() => {
    const value = query.trim()
    if (value.length < 2 || selected) { setSuggestions([]); setSuggestError(''); return }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      try {
        setSuggestions(await suggestPlaces(value, controller.signal)); setSuggestError(''); setActiveIndex(-1)
      } catch (e) {
        if (controller.signal.aborted) return
        setSuggestions([]); setSuggestError(e instanceof Error ? e.message : 'Suggestions are unavailable.')
      }
    }, 120)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, selected])

  function choose(place: PlaceSuggestion) { setQuery(place.display_name); setSelected(place); setSuggestions([]); setActiveIndex(-1); setError(''); input.current?.focus() }
  function changeQuery(value: string) { setQuery(value); setSelected(null); setActiveIndex(-1); setError('') }
  function navigateSuggestions(event: React.KeyboardEvent<HTMLInputElement>) { if (!suggestions.length) return; if (event.key === 'ArrowDown') { event.preventDefault(); setActiveIndex(index => (index + 1) % suggestions.length) } else if (event.key === 'ArrowUp') { event.preventDefault(); setActiveIndex(index => (index - 1 + suggestions.length) % suggestions.length) } else if (event.key === 'Enter' && activeIndex >= 0) { event.preventDefault(); choose(suggestions[activeIndex]) } else if (event.key === 'Escape') setSuggestions([]) }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    setLoading(true); setError('')
    try {
      const result = selected || await geocodeAddress(query.trim())
      if (!result) throw new Error('No location found. Try Vellore, Chennai, or a more specific address.')
      onSubmit({ lat: result.lat, lon: result.lon, label: result.display_name })
    } catch (e) { setError(e instanceof Error ? e.message : 'Search failed') } finally { setLoading(false) }
  }

  return <main className="search-screen"><div className="search-grid" /><div className="locator" aria-hidden="true"><span className="locator-ring" /><span className="locator-ring" /><span className="locator-ring" /><span className="locator-sweep" /><span className="locator-pin p1"><MapPin size={14} /></span><span className="locator-pin p2"><MapPin size={14} /></span><span className="locator-pin p3"><MapPin size={14} /></span><span className="locator-pin p4"><MapPin size={14} /></span></div><header className="wordmark"><span className="mark"><Sparkles size={15} /></span> TERRASCOPE</header><section className="search-hero"><div className="eyebrow"><span className="pulse" /> LAND DUE DILIGENCE, WITH CONTEXT</div><h1>See the land<br /><em>before you commit.</em></h1><p className="hero-copy">A clear, evidence-led read on the parcel beneath the promise. Start with a place.</p><div className="search-combobox"><form className="search-form" onSubmit={submit}><SearchIcon size={19} /><input ref={input} value={query} onChange={e => changeQuery(e.target.value)} onKeyDown={navigateSuggestions} placeholder="Search a town, locality, PIN code or address" aria-label="Search a town, locality, PIN code or address" role="combobox" aria-expanded={suggestions.length > 0} aria-autocomplete="list" aria-controls="place-suggestions" aria-activedescendant={activeIndex >= 0 ? `place-${activeIndex}` : undefined} autoComplete="off" /><button className="icon-button submit-button" disabled={loading} aria-label="Search">{loading ? <span className="search-spinner" /> : <ArrowRight size={19} />}</button></form>{suggestions.length > 0 && <div className="suggestions" id="place-suggestions" role="listbox">{suggestions.map((place, index) => <button type="button" id={`place-${index}`} className={`suggestion ${activeIndex === index ? 'active' : ''}`} role="option" aria-selected={activeIndex === index} key={`${place.lat}-${place.lon}-${index}`} onClick={() => choose(place)}><MapPin size={16} /><span>{place.display_name}{(place.kind || place.precision?.startsWith('approximate')) && <small className="suggestion-kind">{[place.kind, place.precision?.startsWith('approximate') ? 'approximate location' : null].filter(Boolean).join(' · ')}</small>}</span></button>)}</div>}</div>{suggestError && <p className="form-error" role="status">{suggestError}</p>}{loading && <p className="search-status">Opening parcel workspace...</p>}{error && <p className="form-error">{error}</p>}<div className="search-note"><MapPin size={14} /><span>Any town, locality, PIN code or address in India, union territories included. Place names © <a href="https://www.geonames.org/" target="_blank" rel="noreferrer">GeoNames</a> (CC BY 4.0); full addresses via OpenStreetMap Nominatim only when you press Search.</span></div></section>{saved.length > 0 && <section className="saved-reports"><div className="section-label"><Clock size={13} /> SAVED REPORTS</div><div className="saved-list">{(showAllSaved ? saved : saved.slice(0, RECENT_SAVED)).map((item, index) => <button type="button" className="saved-card" style={{ animationDelay: `${index * 70}ms` }} key={item.parcel_id} disabled={openingParcelId === item.parcel_id} onClick={() => onOpenSaved(item.parcel_id)}><FileText size={15} /><span className="saved-main"><strong>{item.address || item.district || 'Unnamed parcel'}</strong><small>{item.area_acres == null ? 'area unavailable' : formatArea(acresToM2(item.area_acres), areaUnit)}{item.document_count > 0 ? ` · ${item.document_count} document${item.document_count === 1 ? '' : 's'}` : ''}{item.has_evaluation ? '' : ' · not yet evaluated'} · {(item.created_at || '').slice(0, 10)}</small></span><span className="saved-open">{openingParcelId === item.parcel_id ? 'Opening…' : 'Open'}</span></button>)}</div>{saved.length > RECENT_SAVED && <button type="button" className="saved-more" onClick={() => setShowAllSaved(open => !open)}>{showAllSaved ? 'Show fewer' : `Show all ${saved.length} reports`}</button>}</section>}<footer className="search-footer"><span>Satellite signals</span><span>Land records</span><span>Infrastructure</span><span>One decision surface</span></footer></main>
}
