import { ArrowRight, MapPin, Search as SearchIcon, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { geocodeAddress, geocodeSuggestions, PlaceSuggestion } from '../lib/api'

export function Search({ onSubmit }: { onSubmit: (place: { lat: number; lon: number; label: string }) => void }) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([])
  const [activeIndex, setActiveIndex] = useState(-1)
  const [selected, setSelected] = useState<PlaceSuggestion | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const requestId = useRef(0)

  useEffect(() => {
    const value = query.trim()
    if (value.length < 2 || selected) { setSuggestions([]); return }
    const id = ++requestId.current
    const timer = window.setTimeout(async () => {
      try {
        const results = await geocodeSuggestions(value)
        if (id === requestId.current) setSuggestions(results)
      } catch { if (id === requestId.current) setSuggestions([]) }
    }, 650)
    return () => window.clearTimeout(timer)
  }, [query, selected])

  function choose(place: PlaceSuggestion) { setQuery(place.display_name); setSelected(place); setSuggestions([]); setActiveIndex(-1); setError('') }
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

  return <main className="search-screen"><div className="search-grid" /><header className="wordmark"><span className="mark"><Sparkles size={15} /></span> TERRASCOPE <span className="wordmark-rule" /> REVIEW 02</header><section className="search-hero"><div className="eyebrow"><span className="pulse" /> LAND DUE DILIGENCE, WITH CONTEXT</div><h1>See the land<br /><em>before you commit.</em></h1><p className="hero-copy">A clear, evidence-led read on the parcel beneath the promise. Start with a place.</p><div className="search-combobox"><form className="search-form" onSubmit={submit}><SearchIcon size={19} /><input value={query} onChange={e => changeQuery(e.target.value)} onKeyDown={navigateSuggestions} placeholder="Search Vellore, Chennai, or an address" aria-label="Search an address, locality or coordinates" aria-autocomplete="list" aria-controls="place-suggestions" aria-activedescendant={activeIndex >= 0 ? `place-${activeIndex}` : undefined} /><button className="icon-button submit-button" disabled={loading} aria-label="Search">{loading ? <span className="search-spinner" /> : <ArrowRight size={19} />}</button></form>{suggestions.length > 0 && <div className="suggestions" id="place-suggestions" role="listbox">{suggestions.map((place, index) => <button type="button" id={`place-${index}`} className={`suggestion ${activeIndex === index ? 'active' : ''}`} role="option" aria-selected={activeIndex === index} key={`${place.lat}-${place.lon}-${index}`} onClick={() => choose(place)}><MapPin size={16} /><span>{place.display_name}</span></button>)}</div>}</div>{loading && <p className="search-status">Opening parcel workspace...</p>}{error && <p className="form-error">{error}</p>}<div className="search-note"><MapPin size={14} /> Search India locations, with Tamil Nadu ready for review</div></section><footer className="search-footer"><span>Satellite signals</span><span>Land records</span><span>Infrastructure</span><span>One decision surface</span></footer></main>
}
