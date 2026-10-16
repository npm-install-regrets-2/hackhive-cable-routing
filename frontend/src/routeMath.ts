import type { Point, Ring } from './model'

export type RouteSegment = {
  from: Point; to: Point; startM: number; endM: number;
  legIndex: number; destinationId: string
}
export type RouteTrack = {
  segments: RouteSegment[]; legEnds: { destinationId: string; atM: number }[];
  lengthM: number
}

export function buildRouteTrack(ring: Ring, scale: number): RouteTrack {
  if (!(scale > 0) || !Number.isFinite(scale) ||
      ring.stop_ids.length !== ring.legs.length + 1 ||
      ring.stop_ids[0] !== ring.hub_id || ring.stop_ids.at(-1) !== ring.hub_id) {
    throw new Error('The checked ring has no usable closed sequence.')
  }
  const nodeStops = ring.stop_ids.slice(1, -1)
  if (new Set(nodeStops).size !== nodeStops.length || nodeStops.includes(ring.hub_id)) {
    throw new Error('A checked ring repeats or omits a node stop.')
  }
  const segments: RouteSegment[] = []
  const legEnds: RouteTrack['legEnds'] = []
  let lengthM = 0
  let priorEnd: Point | null = null
  ring.legs.forEach((leg, legIndex) => {
    if (leg.from_id !== ring.stop_ids[legIndex] || leg.to_id !== ring.stop_ids[legIndex + 1] || leg.polyline.length < 2) {
      throw new Error('A cable leg does not match the checked stop order.')
    }
    const first = leg.polyline[0]
    if (priorEnd && Math.hypot(priorEnd.x - first.x, priorEnd.y - first.y) / scale > 0.01) {
      throw new Error('Cable legs do not join at their checked stop.')
    }
    for (let index = 1; index < leg.polyline.length; index += 1) {
      const from = leg.polyline[index - 1]
      const to = leg.polyline[index]
      if (![from.x, from.y, to.x, to.y].every(Number.isFinite)) throw new Error('A cable vertex is not finite.')
      const spanM = Math.hypot(to.x - from.x, to.y - from.y) / scale
      if (spanM <= 0) continue
      segments.push({ from, to, startM: lengthM, endM: lengthM + spanM, legIndex, destinationId: leg.to_id })
      lengthM += spanM
    }
    priorEnd = leg.polyline.at(-1)!
    legEnds.push({ destinationId: leg.to_id, atM: lengthM })
  })
  const start = ring.legs[0].polyline[0]
  if (Math.hypot(start.x - priorEnd!.x, start.y - priorEnd!.y) / scale > 0.01) {
    throw new Error('The cable geometry does not return to its originating hub.')
  }
  if (!segments.length) throw new Error('The checked ring has no cable geometry.')
  return { segments, legEnds, lengthM }
}

export function routePosition(track: RouteTrack, distanceM: number): { point: Point; segment: RouteSegment; fraction: number } {
  const position = Math.max(0, Math.min(track.lengthM, distanceM))
  const segment = track.segments.find(item => position <= item.endM) ?? track.segments.at(-1)!
  const fraction = Math.max(0, Math.min(1, (position - segment.startM) / (segment.endM - segment.startM)))
  return {
    point: {
      x: segment.from.x + (segment.to.x - segment.from.x) * fraction,
      y: segment.from.y + (segment.to.y - segment.from.y) * fraction,
    }, segment, fraction,
  }
}

export function reachedStops(track: RouteTrack, distanceM: number): string[] {
  return track.legEnds.filter(item => item.atM <= distanceM + 1e-9).map(item => item.destinationId)
}
