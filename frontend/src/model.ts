export type Point = { x: number; y: number }
export type Polygon = { exterior: Point[]; holes: Point[][] }
export type Room = { id: string; source_label: string; kind: string; eligible: boolean; geometry: Polygon; area_m2: number }
export type Node = { id: string; room_id: string; point: Point; source: string }
export type Hub = { id: string; room_id: string; point: Point }
export type Assignment = { room_id: string; node_id: string; hub_id: string }
export type Portal = { id: string; space_a_id: string; space_b_id: string; kind: 'door' | 'open_passage'; segment: Point[] }
export type Obstacle = { id: string; kind: string; geometry: Polygon | Point[] }
export type Leg = { from_id: string; to_id: string; polyline: Point[] }
export type Ring = { hub_id: string; stop_ids: string[]; legs: Leg[] }
export type Plan = {
  id: string; drawing_units_per_metre: number; internal_boundary: Polygon;
  rooms: Room[]; nodes: Node[]; portals: Portal[]; obstacles: Obstacle[];
  rules: { max_area_m2_per_hub: number; max_nodes_per_hub: number; node_wall_clearance_m: number }
}
export type Solution = { plan_id: string; status: string; hubs: Hub[]; assignments: Assignment[]; rings: Ring[] }
export type Development = { schema_version: string; plan: Plan; solution: Solution }
export type Architecture = { wall_solids: { id: string; geometry: Polygon }[]; window_solids: { id: string; geometry: Polygon }[] }
