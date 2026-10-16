import assert from 'node:assert/strict'
import test from 'node:test'
import { buildRouteTrack, reachedStops, routePosition } from '../src/routeMath.ts'
import type { Ring } from '../src/model.ts'

const ring: Ring = {
  hub_id: 'hub:1', stop_ids: ['hub:1', 'node:a', 'node:b', 'hub:1'],
  legs: [
    { from_id: 'hub:1', to_id: 'node:a', polyline: [{ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 4, y: 2 }] },
    { from_id: 'node:a', to_id: 'node:b', polyline: [{ x: 4, y: 2 }, { x: 4, y: 0 }, { x: 8, y: 0 }] },
    { from_id: 'node:b', to_id: 'hub:1', polyline: [{ x: 8, y: 0 }, { x: 0, y: 0 }] },
  ],
}

test('cumulative animation follows bends and retraced segments in solver order', () => {
  const track = buildRouteTrack(ring, 2)
  assert.equal(track.lengthM, 10)
  assert.deepEqual(routePosition(track, 2.5).point, { x: 4, y: 1 })
  assert.deepEqual(routePosition(track, 3.5).point, { x: 4, y: 1 })
  assert.equal(routePosition(track, 3.5).segment.legIndex, 1)
  assert.deepEqual(routePosition(track, 10).point, { x: 0, y: 0 })
  assert.deepEqual(reachedStops(track, 3), ['node:a'])
  assert.deepEqual(reachedStops(track, 6), ['node:a', 'node:b'])
  assert.deepEqual(reachedStops(track, 10), ['node:a', 'node:b', 'hub:1'])
})

test('rejects a leg that would invent a different stop order', () => {
  const broken: Ring = { ...ring, legs: [{ ...ring.legs[0], to_id: 'node:b' }, ...ring.legs.slice(1)] }
  assert.throws(() => buildRouteTrack(broken, 2), /stop order/)
})

test('rejects a visual shortcut across disconnected cable legs', () => {
  const broken: Ring = { ...ring, legs: [ring.legs[0],
    { ...ring.legs[1], polyline: [{ x: 6, y: 2 }, ...ring.legs[1].polyline.slice(1)] }, ring.legs[2]] }
  assert.throws(() => buildRouteTrack(broken, 2), /do not join/)
})
