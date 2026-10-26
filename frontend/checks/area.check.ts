// Run from frontend/: node checks/area.check.ts   (Node 23.6+ runs TypeScript directly; no test framework needed)
import assert from 'node:assert/strict'
import { acresToM2, convertArea, formatArea } from '../src/lib/area.ts'

// The exact factor: 1 ha = 2.4710538147 acres.
assert.equal(convertArea(10000, 'acres'), 2.4710538147)
assert.equal(convertArea(10000, 'ha'), 1)
// Examples from the requirement (432.06 ha).
assert.equal(formatArea(4_320_600, 'ha'), '432.06 ha')
assert.equal(formatArea(4_320_600, 'acres'), '1,067.64 acres')  // 432.06 ha x 2.4710538147
assert.equal(formatArea(4_320_600, 'm2'), '4,320,600 m²')
// Small plots keep two significant digits; zero and missing values are explicit.
assert.equal(formatArea(50, 'acres'), '0.012 acres')
assert.equal(formatArea(50, 'm2'), '50 m²')
assert.equal(formatArea(1780.6, 'acres'), '0.44 acres')
assert.equal(formatArea(0, 'acres'), '0.00 acres')
assert.equal(formatArea(null, 'acres'), 'Area unavailable')
// Large parcels group thousands.
assert.equal(formatArea(10_000_000, 'acres'), '2,471.05 acres')
// Saved lists carry acres: the round trip returns the same display.
assert.equal(formatArea(acresToM2(0.44), 'acres'), '0.44 acres')
assert.equal(formatArea(acresToM2(110.18), 'ha'), '44.59 ha')
console.log('area checks passed')
