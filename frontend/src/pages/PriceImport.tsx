import { useEffect, useState } from 'react'
import { ArrowLeft, IndianRupee, Sparkles, Upload } from 'lucide-react'
import { commitPriceImport, ImportPreview, previewPriceImport, valuationDataStatus } from '../lib/api'

const REASON: Record<string, string> = {
  missing_source_or_record_id: 'no source or record id', missing_reuse_basis: 'no reuse permission stated', unknown_price_type: 'price type is not asking / transaction / guideline',
  currency_not_inr: 'not in INR (never converted)', unsupported_price_unit: 'unsupported price unit', not_vacant_land: 'built property (house, flat, building)', unknown_property_category: 'unknown property category',
  unknown_land_use: 'unknown land use', category_land_use_mismatch: 'category and land use disagree', unknown_location_precision: 'unknown location precision', missing_coordinates: 'no coordinates',
  coordinates_outside_india: 'coordinates outside India', unparseable_date: 'date not readable', retrieved_before_observed: 'retrieved before it was observed', non_positive_price: 'price is zero or negative',
  invalid_area: 'area or unit invalid (bigha/katha are not converted)', total_price_without_area: 'total price without an area', implausible_price_per_sqft: 'price per sq ft implausible (lakh/crore or unit slip?)', implausible_area: 'area implausible',
}
const KIND: Record<string, string> = { same_record_repeated: 'same record delivered twice', relisting_of_same_plot: 're-listing of the same plot' }

/** Owner/broker-supplied or licensed price rows: preview every row's fate, then add the valid ones. Nothing is written until you confirm. */
export function PriceImport({ onBack }: { onBack: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [permission, setPermission] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [loaded, setLoaded] = useState('')
  const refresh = () => valuationDataStatus().then(status => setLoaded(status.available && status.data ? `${status.data.rows} observations loaded from ${status.data.sources.join(', ')} (${status.data.observed_from} to ${status.data.observed_to}).` : 'No price observations are loaded yet.')).catch(() => setLoaded('The valuation service could not be reached.'))
  useEffect(() => { refresh() }, [])

  async function run(action: 'preview' | 'commit') {
    if (!file) return
    setBusy(true); setMessage('')
    try {
      if (action === 'preview') { setPreview(await previewPriceImport(file)); setPermission(false) }
      else { const result = await commitPriceImport(file); setMessage(`Added ${result.rows_added} rows (${result.rows_rejected} rejected). The file now holds ${result.rows_in_file} rows${result.backup ? `; the previous file was kept as ${result.backup}` : ''}.`); setPreview(null); setFile(null); refresh() }
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Import failed.') } finally { setBusy(false) }
  }

  return <main className="report-shell"><header className="report-topbar"><button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Search</button><div className="wordmark"><span className="mark"><Sparkles size={14} /></span> TERRASCOPE</div><div /></header>
    <div className="report-content import-page">
      <section className="valuation-section"><div className="section-label"><IndianRupee size={13} /> PRICE DATA</div><h2>Import permitted price observations</h2>
        <p className="valuation-reason">{loaded}</p>
        <p className="muted valuation-detail">Use rows you are allowed to use: an owner's or broker's own listings or sales with their written permission, or a licensed feed. Each row names its permission in <code>reuse_basis</code>. Columns are in <code>valuation/README.md</code>. Asking prices, registered sale prices and guideline values stay separate and are never pooled or converted into each other.</p>
        <div className="land-upload"><label className="upload-row"><input type="file" accept=".csv,text/csv" onChange={e => { setFile(e.target.files?.[0] || null); setPreview(null); setMessage('') }} /><Upload size={14} /><span>{file ? file.name : 'Choose a CSV file'}</span></label><button className="quiet-button" disabled={!file || busy} onClick={() => run('preview')}>{busy && !preview ? 'Checking…' : 'Preview'}</button></div>
        {message && <p className="muted" role="status">{message}</p>}
      </section>
      {preview && !preview.ok && <section className="evidence-status"><h2>This file cannot be imported</h2><p className="form-error">{preview.error}</p></section>}
      {preview?.ok && <section className="evidence-status"><div className="section-head"><div><div className="section-label">PREVIEW · NOTHING WRITTEN YET</div><h2>{preview.rows_valid} of {preview.rows_read} rows valid</h2></div><span className="completeness">{preview.usable_as_comparables_today} usable as comparables today</span></div>
        <table className="flood-table"><caption>Groups (never pooled)</caption><thead><tr><th>Price basis</th><th>Land use</th><th>Category</th><th>Rows</th><th>Usable now</th><th>Median ₹/sq ft</th><th>Observed</th></tr></thead><tbody>{preview.groups?.map(g => <tr key={`${g.price_type}-${g.land_use}-${g.property_category}`}><td>{g.price_type}</td><td>{g.land_use}</td><td>{g.property_category.replace('_', ' ')}</td><td>{g.rows}</td><td>{g.usable_now}</td><td>₹{Math.round(g.median_inr_per_sqft).toLocaleString('en-IN')}</td><td>{g.observed_from} – {g.observed_to}</td></tr>)}</tbody></table>
        <p className="muted">Sources: {preview.sources?.map(s => `${s.source} (${s.rows} rows; permission: ${s.reuse_basis.join('; ')})`).join(' · ')}. Location precision: {Object.entries(preview.location_precision || {}).map(([k, v]) => `${k} ${v}`).join(', ')}.</p>
        {(preview.rejected?.length || 0) > 0 && <details className="denominators" open><summary>{preview.rejected!.length} rejected rows and why</summary><table className="flood-table"><thead><tr><th>CSV line</th><th>Record</th><th>Reason</th></tr></thead><tbody>{[...preview.rejected!].sort((a, b) => a.row - b.row).map(r => <tr key={r.row}><td>{r.row}</td><td>{r.source} · {r.source_record_id}</td><td>{REASON[r.reason] || r.reason}</td></tr>)}</tbody></table></details>}
        {(preview.duplicates?.length || 0) > 0 && <details className="denominators"><summary>{preview.duplicates!.length} duplicate{preview.duplicates!.length === 1 ? '' : 's'} (kept in the file, counted once)</summary><ul className="doc-list">{preview.duplicates!.map(d => <li key={d.row}>line {d.row}: {KIND[d.kind] || d.kind} of line {d.kept_row}</li>)}</ul></details>}
        {((preview.stale_rows?.length || 0) + (preview.coarse_location_rows?.length || 0) + (preview.future_rows?.length || 0)) > 0 && <p className="muted">Kept but not used as comparables today: {preview.stale_rows?.length || 0} stale (asking older than 18 months, sale or guideline older than 3 years), {preview.coarse_location_rows?.length || 0} located only to a PIN code or district, {preview.future_rows?.length || 0} dated in the future.</p>}
        <details className="denominators"><summary>First {preview.rows?.length} valid rows, normalised</summary><table className="flood-table"><thead><tr><th>Line</th><th>Record</th><th>Basis</th><th>Use</th><th>Observed</th><th>₹/sq ft</th><th>Area (sq ft)</th><th>Location</th><th>Flags</th></tr></thead><tbody>{preview.rows?.map(r => <tr key={r.row}><td>{r.row}</td><td>{r.source} · {r.source_record_id}</td><td>{r.price_type}</td><td>{r.land_use}</td><td>{r.observed_date}</td><td>₹{Math.round(r.price_inr_per_sqft).toLocaleString('en-IN')}</td><td>{r.area_sqft == null ? '—' : Math.round(r.area_sqft).toLocaleString('en-IN')}</td><td>{r.location_precision}{r.locality ? ` · ${r.locality}` : ''}</td><td>{r.flags.join(', ') || '—'}</td></tr>)}</tbody></table></details>
        <label className="permission-check"><input type="checkbox" checked={permission} onChange={e => setPermission(e.target.checked)} /> I have permission to use these rows as stated in their <code>reuse_basis</code>.</label>
        <button className="primary-button" disabled={!permission || busy || !preview.rows_valid} onClick={() => run('commit')}>{busy ? 'Adding…' : `Add the ${preview.rows_read - (preview.rejected?.length || 0)} rows that passed (duplicates are counted once)`}</button>
      </section>}
    </div>
  </main>
}
