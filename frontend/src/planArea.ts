import type { Plan, Point } from './model'

function ringArea(points: Point[]): number {
  let twiceArea = 0
  for (let index = 0; index < points.length - 1; index++) {
    const current = points[index]
    const next = points[index + 1]
    twiceArea += current.x * next.y - next.x * current.y
  }
  return Math.abs(twiceArea) / 2
}

export function floorPlanAreaM2(plan: Pick<Plan, 'internal_boundary' | 'drawing_units_per_metre'>): number {
  const boundary = plan.internal_boundary
  const areaUnits2 = ringArea(boundary.exterior) - (boundary.holes ?? []).reduce((area, hole) => area + ringArea(hole), 0)
  return areaUnits2 / plan.drawing_units_per_metre ** 2
}
