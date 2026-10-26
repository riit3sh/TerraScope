/** Parcel area display. Areas are kept in square metres everywhere; only the label changes with the unit. */
import { useState } from 'react'

export type AreaUnit = 'acres' | 'ha' | 'm2'
export const AREA_UNITS: AreaUnit[] = ['acres', 'ha', 'm2']
export const AREA_UNIT_LABEL: Record<AreaUnit, string> = { acres: 'acres', ha: 'ha', m2: 'm²' }
export const ACRES_PER_HECTARE = 2.4710538147
const STORAGE_KEY = 'terrascope.areaUnit'

export function convertArea(m2: number, unit: AreaUnit): number {
  return unit === 'm2' ? m2 : unit === 'ha' ? m2 / 10000 : (m2 / 10000) * ACRES_PER_HECTARE
}

/** Saved-report lists carry acres only; back to square metres with the same factor. */
export function acresToM2(acres: number): number {
  return (acres / ACRES_PER_HECTARE) * 10000
}

/** `1,067.54 acres`, `432.06 ha`, `4,320,600 m²`; plots under 0.1 acre/ha keep two significant digits (0.012 acres). */
export function formatArea(m2: number | null | undefined, unit: AreaUnit): string {
  if (m2 == null || !Number.isFinite(m2)) return 'Area unavailable'
  const value = convertArea(m2, unit)
  const digits = unit === 'm2' ? 0 : value === 0 || value >= 0.1 ? 2 : Math.min(6, 1 - Math.floor(Math.log10(value)))
  return `${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })} ${AREA_UNIT_LABEL[unit]}`
}

export function loadAreaUnit(): AreaUnit {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return AREA_UNITS.includes(saved as AreaUnit) ? saved as AreaUnit : 'acres'
  } catch { return 'acres' }  // storage blocked (private window, preview): acres, not an error
}

/** The viewer's chosen unit, remembered in this browser only; acres by default. */
export function useAreaUnit(): [AreaUnit, (unit: AreaUnit) => void] {
  const [unit, setUnit] = useState<AreaUnit>(loadAreaUnit)
  return [unit, (next: AreaUnit) => { setUnit(next); try { localStorage.setItem(STORAGE_KEY, next) } catch { /* not remembered */ } }]
}
