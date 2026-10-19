import assert from 'node:assert/strict'
import test from 'node:test'
import { floorPlanAreaM2 } from '../src/planArea.ts'

test('floor area uses the boundary footprint, subtracts holes, and converts drawing units', () => {
  const area = floorPlanAreaM2({
    drawing_units_per_metre: 2,
    internal_boundary: {
      exterior: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 0 }],
      holes: [[{ x: 2, y: 2 }, { x: 2, y: 4 }, { x: 4, y: 4 }, { x: 4, y: 2 }, { x: 2, y: 2 }]],
    },
  })
  assert.equal(area, 24)
})
