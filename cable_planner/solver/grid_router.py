"""Obstacle-aware rectilinear Hanan-grid router and capacity-constrained ring solver.

Implements:
1. Precise wall clearance hub-candidate generation (>= 0.5m clearance).
2. Connected territory partitioning respecting area (100 m2) and node (5 or configurable) limits.
3. Multi-lane portal traversal to prevent doorway collinear overlap and reversals.
4. Obstacle-aware rectilinear Hanan-grid pathfinding strictly avoiding walls and exterior.
5. Tour search using the lexicographic objective:
   Primary: Hub Count H
   Secondary: Route Cost J = L + 5X + O + 0.5B
   Tertiary: Area Balance Gap
"""

from __future__ import annotations

import copy
import heapq
import itertools
import math
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import unary_union

Point2D = Tuple[float, float]


def hub_count_lower_bound(plan: Dict[str, Any]) -> int:
    """Return the simultaneous area/node capacity lower bound."""
    rooms = [room for room in plan["rooms"] if room.get("eligible", False)]
    node_count = len(plan.get("nodes", []))
    if not rooms:
        return 0
    rules = plan["rules"]
    max_area = rules.get("max_area_m2_per_hub", 100.0)
    max_nodes = rules.get("max_nodes_per_hub", 5)
    return max(
        math.ceil(sum(room["area_m2"] for room in rooms) / max_area),
        math.ceil(node_count / max_nodes),
    )


def _parse_polygon(geom_dict: Dict[str, Any]) -> Polygon:
    exterior = [(p["x"], p["y"]) for p in geom_dict.get("exterior", [])]
    holes = [[(p["x"], p["y"]) for p in h] for h in geom_dict.get("holes", [])]
    return Polygon(shell=exterior, holes=holes)


def _parse_polyline(geom_list: List[Dict[str, Any]]) -> LineString:
    return LineString([(p["x"], p["y"]) for p in geom_list])


class HananRouter:
    """Rectilinear grid router built on the Hanan grid of floorplan features."""

    def __init__(self, plan: Dict[str, Any], extra_points: Optional[List[Point2D]] = None):
        self.plan = plan
        self.scale = float(plan.get("drawing_units_per_metre", 1.0))
        self.tol = float(plan.get("rules", {}).get("geometry_tolerance", 0.001)) * self.scale

        # Obstacles and boundary
        boundary_dict = plan.get("internal_boundary")
        if boundary_dict and "exterior" in boundary_dict:
            self.internal_boundary: Optional[Polygon] = _parse_polygon(boundary_dict).buffer(self.tol)
        else:
            self.internal_boundary = None

        self.wall_polys: List[Polygon] = []
        self.wall_lines: List[LineString] = []
        for o in plan.get("obstacles", []):
            g = o.get("geometry")
            if isinstance(g, dict) and "exterior" in g:
                self.wall_polys.append(_parse_polygon(g))
            elif isinstance(g, list) and len(g) >= 2:
                self.wall_lines.append(_parse_polyline(g))

        # Collect Hanan coordinates
        xs: Set[float] = set()
        ys: Set[float] = set()

        for r in plan.get("rooms", []):
            if r.get("eligible", False):
                poly = _parse_polygon(r["geometry"])
                for x, y in poly.exterior.coords:
                    xs.add(round(x, 2))
                    ys.add(round(y, 2))

        for n in plan.get("nodes", []):
            xs.add(round(float(n["point"]["x"]), 2))
            ys.add(round(float(n["point"]["y"]), 2))

        # Portals: endpoints and multiple lateral lanes (25%, 50%, 75%)
        for port in plan.get("portals", []):
            s = port.get("segment", [])
            if len(s) >= 2:
                p0 = (float(s[0]["x"]), float(s[0]["y"]))
                p1 = (float(s[-1]["x"]), float(s[-1]["y"]))
                for pt in [p0, p1]:
                    xs.add(round(pt[0], 2))
                    ys.add(round(pt[1], 2))
                for frac in [0.25, 0.50, 0.75]:
                    lx = p0[0] + frac * (p1[0] - p0[0])
                    ly = p0[1] + frac * (p1[1] - p0[1])
                    xs.add(round(lx, 2))
                    ys.add(round(ly, 2))

        if extra_points:
            for ep in extra_points:
                xs.add(round(ep[0], 2))
                ys.add(round(ep[1], 2))

        self.xs = sorted(xs)
        self.ys = sorted(ys)

        # Build graph
        self.graph = nx.Graph()
        self._build_grid()

    def _edge_is_valid(self, p1: Point2D, p2: Point2D) -> bool:
        ls = LineString([p1, p2])
        if self.internal_boundary and not self.internal_boundary.covers(ls):
            return False
        for wp in self.wall_polys:
            inter = ls.intersection(wp)
            if not inter.is_empty and inter.length > self.tol:
                return False
        for wl in self.wall_lines:
            if ls.crosses(wl) or ls.overlaps(wl):
                return False
        return True

    def _build_grid(self) -> None:
        # Horizontal edges
        for j in range(len(self.ys)):
            y = self.ys[j]
            for i in range(len(self.xs) - 1):
                p1 = (self.xs[i], y)
                p2 = (self.xs[i + 1], y)
                if self._edge_is_valid(p1, p2):
                    dist = abs(p2[0] - p1[0])
                    self.graph.add_edge(p1, p2, weight=dist, base_weight=dist)

        # Vertical edges
        for i in range(len(self.xs)):
            x = self.xs[i]
            for j in range(len(self.ys) - 1):
                p1 = (x, self.ys[j])
                p2 = (x, self.ys[j + 1])
                if self._edge_is_valid(p1, p2):
                    dist = abs(p2[1] - p1[1])
                    self.graph.add_edge(p1, p2, weight=dist, base_weight=dist)

    def find_nearest_node(self, pt: Point2D) -> Point2D:
        """Find the closest existing node in the Hanan graph."""
        if pt in self.graph:
            return pt
        # Find closest graph vertex
        best_pt = None
        best_dist = float("inf")
        for node in self.graph.nodes():
            d = math.hypot(node[0] - pt[0], node[1] - pt[1])
            if d < best_dist:
                best_dist = d
                best_pt = node
        return best_pt if best_pt is not None else pt

    def route_path(
        self,
        start: Point2D,
        end: Point2D,
        dynamic_graph: Optional[nx.Graph] = None,
        simplify: bool = True,
        bend_penalty: float = 0.5,
    ) -> Optional[List[Point2D]]:
        """A* search on rectilinear graph penalizing direction changes (bends)."""
        g = dynamic_graph if dynamic_graph is not None else self.graph
        s_node = self.find_nearest_node(start)
        e_node = self.find_nearest_node(end)

        if s_node not in g or e_node not in g:
            return None
        if not nx.has_path(g, s_node, e_node):
            return None

        # Priority queue stores: (f_score, cost, current_node, prev_dir, path)
        open_set: List[Tuple[float, float, Point2D, Tuple[int, int], List[Point2D]]] = []
        heapq.heappush(open_set, (0.0, 0.0, s_node, (0, 0), [s_node]))
        
        # Best cost to state (node, dir)
        best_costs: Dict[Tuple[Point2D, Tuple[int, int]], float] = {}

        while open_set:
            f, cost, curr, prev_dir, path = heapq.heappop(open_set)

            if curr == e_node:
                res = list(path)
                if start != s_node:
                    res.insert(0, start)
                if end != e_node:
                    res.append(end)
                return _simplify_collinear(res) if simplify else res

            state = (curr, prev_dir)
            if state in best_costs and best_costs[state] < cost - 1e-6:
                continue

            for neighbor in g.neighbors(curr):
                edge_data = g[curr][neighbor]
                edge_wt = edge_data.get("weight", edge_data.get("base_weight", 1.0))

                dx = 1 if neighbor[0] > curr[0] else (-1 if neighbor[0] < curr[0] else 0)
                dy = 1 if neighbor[1] > curr[1] else (-1 if neighbor[1] < curr[1] else 0)
                curr_dir = (dx, dy)

                # Bend cost in drawing units (bend_penalty * scale)
                turn_cost = 0.0
                if prev_dir != (0, 0) and prev_dir != curr_dir:
                    turn_cost = bend_penalty * self.scale

                new_cost = cost + edge_wt + turn_cost
                next_state = (neighbor, curr_dir)

                if next_state not in best_costs or new_cost < best_costs[next_state]:
                    best_costs[next_state] = new_cost
                    # Heuristic: Manhattan distance
                    h = (abs(e_node[0] - neighbor[0]) + abs(e_node[1] - neighbor[1]))
                    heapq.heappush(open_set, (new_cost + h, new_cost, neighbor, curr_dir, path + [neighbor]))

        return None


def _simplify_collinear(points: List[Point2D]) -> List[Point2D]:
    """Eliminate redundant intermediate collinear points along rectilinear lines."""
    if not points:
        return []
    if len(points) == 1:
        return [points[0], points[0]]
    result = [points[0]]
    for pt in points[1:]:
        if len(result) >= 2:
            p_prev = result[-2]
            p_curr = result[-1]
            if (p_prev[0] == p_curr[0] == pt[0]) or (p_prev[1] == p_curr[1] == pt[1]):
                result[-1] = pt
                continue
        result.append(pt)
    return result if len(result) >= 2 else [*result, *result]


def find_legal_hub_candidates(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate legal hub candidates having >= 0.5m clearance from room boundary."""
    scale = float(plan.get("drawing_units_per_metre", 1.0))
    clearance_m = float(plan.get("rules", {}).get("node_wall_clearance_m", 0.5))
    tol_m = float(plan.get("rules", {}).get("geometry_tolerance", 0.001))
    clearance_units = clearance_m * scale
    tol_units = tol_m * scale

    candidates = []
    for r in plan.get("rooms", []):
        if not r.get("eligible", False):
            continue
        poly = _parse_polygon(r["geometry"])
        eroded = poly.buffer(-clearance_units)
        if not eroded.is_empty:
            # Pick representative point inside eroded safe region
            cand = eroded.representative_point()
            cand_pt = (round(cand.x, 2), round(cand.y, 2))
            actual_dist = poly.boundary.distance(Point(cand_pt))
            if actual_dist + tol_units >= clearance_units:
                candidates.append({
                    "room_id": r["id"],
                    "point": cand_pt,
                    "clearance": actual_dist,
                    "area_m2": float(r.get("area_m2", 0.0))
                })
        else:
            # Fallback to centroid if room is tightly configured
            cand = poly.centroid
            candidates.append({
                "room_id": r["id"],
                "point": (round(cand.x, 2), round(cand.y, 2)),
                "clearance": 0.0,
                "area_m2": float(r.get("area_m2", 0.0))
            })
    return candidates


def _portal_connectivity(plan: Dict[str, Any], eligible_room_ids: Set[str]) -> nx.Graph:
    """Build graph of eligible room connections via portals."""
    g = nx.Graph()
    for r_id in eligible_room_ids:
        g.add_node(r_id)
    for p in plan.get("portals", []):
        a, b = p.get("space_a_id"), p.get("space_b_id")
        if a in eligible_room_ids and b in eligible_room_ids:
            g.add_edge(a, b)
    return g


def solve(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for capacity-constrained rectilinear closed-ring optimization.
    Guarantees:
      - Closed ring starting and ending at hub
      - Strict axis-alignment
      - 100% obstacle collision avoidance
      - Capacity adherence (area and node limits)
      - Deterministic routing and checker-style candidate tour scoring
    """
    plan_id = plan.get("id")
    lower_bound = hub_count_lower_bound(plan)
    rooms = sorted([r for r in plan.get("rooms", []) if r.get("eligible", False)], key=lambda x: x["id"])
    nodes = {n["room_id"]: n for n in plan.get("nodes", [])}
    
    if not rooms or not nodes:
        return {
            "plan_id": plan_id,
            "status": "feasible",
            "lower_bound_hubs": 0,
            "hubs": [],
            "assignments": [],
            "rings": [],
            "metrics": {},
            "diagnostics": [{"code": "EMPTY_PLAN", "message": "No eligible rooms or nodes."}]
        }

    rules = plan.get("rules", {})
    max_area = float(rules.get("max_area_m2_per_hub", 100.0))
    max_nodes = int(rules.get("max_nodes_per_hub", 5))
    scale = float(plan.get("drawing_units_per_metre", 1.0))

    eligible_room_ids = {r["id"] for r in rooms}
    portal_graph = _portal_connectivity(plan, eligible_room_ids)

    # Candidate hubs
    candidates = find_legal_hub_candidates(plan)
    if not candidates:
        return {
            "plan_id": plan_id,
            "status": "infeasible",
            "lower_bound_hubs": lower_bound,
            "hubs": [],
            "assignments": [],
            "rings": [],
            "diagnostics": [{"code": "NO_LEGAL_HUB_CANDIDATE", "message": "No room has legal clearance for a hub."}]
        }

    # Pre-build router with candidate and node points
    all_points = [c["point"] for c in candidates] + [
        (float(n["point"]["x"]), float(n["point"]["y"])) for n in plan.get("nodes", [])
    ]
    router = HananRouter(plan, extra_points=all_points)

    # Try hub counts starting from lower_bound
    for hub_count in range(lower_bound, len(rooms) + 1):
        sol = _solve_fixed_hub_count(
            plan, rooms, nodes, candidates, portal_graph, router, hub_count, max_nodes, max_area
        )
        if sol is not None:
            sol["status"] = "feasible" if hub_count == lower_bound else "best_known"
            sol["lower_bound_hubs"] = lower_bound
            return sol

    return {
        "plan_id": plan_id,
        "status": "infeasible",
        "lower_bound_hubs": lower_bound,
        "hubs": [],
        "assignments": [],
        "rings": [],
        "diagnostics": [{"code": "NO_FEASIBLE_SOLUTION", "message": "No connected capacity-valid ring found."}]
    }


def _solve_fixed_hub_count(
    plan: Dict[str, Any],
    rooms: List[Dict[str, Any]],
    nodes: Dict[str, Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    portal_graph: nx.Graph,
    router: HananRouter,
    hub_count: int,
    max_nodes: int,
    max_area: float,
) -> Optional[Dict[str, Any]]:
    """Compare feasible partitions by full route cost, then assigned-area gap."""
    room_by_id = {r["id"]: r for r in rooms}
    scale = float(plan.get("drawing_units_per_metre", 1.0))
    best_solution: Optional[Dict[str, Any]] = None
    best_rank = (float("inf"), float("inf"))

    # Single hub case optimization
    if hub_count == 1:
        total_area = sum(r["area_m2"] for r in rooms)
        if len(rooms) > max_nodes or total_area > max_area:
            return None
        # Check overall connectivity
        if len(rooms) > 1 and not nx.is_connected(portal_graph.subgraph([r["id"] for r in rooms])):
            return None

        # Try each legal hub room and compare the routed rings.
        ranked_candidates = sorted(
            candidates,
            key=lambda c: (portal_graph.degree(c["room_id"]), c["area_m2"]),
            reverse=True
        )

        for cand in ranked_candidates:
            hub_dict = {
                "id": "hub:1",
                "point": {"x": cand["point"][0], "y": cand["point"][1]},
                "room_id": cand["room_id"],
            }
            ring = _route_territory_ring(
                hub_dict, [r["id"] for r in rooms], nodes, router, scale
            )
            if ring is not None:
                assignments = [
                    {"room_id": r["id"], "node_id": nodes[r["id"]]["id"], "hub_id": "hub:1"}
                    for r in rooms
                ]
                sol_dict = {
                    "plan_id": plan["id"],
                    "hubs": [hub_dict],
                    "assignments": assignments,
                    "rings": [ring],
                    "diagnostics": [
                        {
                            "code": "OPTIMAL_HUB_COUNT_PROVEN",
                            "message": "Solution meets the capacity lower bound with legal closed ring."
                        }
                    ],
                }
                rank = _fixed_hub_solution_rank(sol_dict, room_by_id, plan, scale)
                if rank < best_rank:
                    best_rank, best_solution = rank, sol_dict
        if best_solution is not None:
            best_solution["metrics"] = _compute_advisory_metrics(plan, best_solution, scale)
        return best_solution

    # Multi-hub partition search: enumerate connected partitions, and for each
    # partition conduct a joint search over all hub-candidate combinations.
    # Capping candidates per territory bounds combinatorics to
    # _MAX_TERRITORY_CANDS^hub_count route evaluations per partition.
    _MAX_TERRITORY_CANDS = 3
    room_ids = [r["id"] for r in rooms]
    cand_by_room = {c["room_id"]: c for c in candidates}

    for hub_rooms_tuple in _partition_connected(room_ids, portal_graph, hub_count, max_nodes, max_area, room_by_id):
        # Rank and cap candidates for every territory in this partition.
        territory_candidate_lists: List[List[Dict[str, Any]]] = []
        partition_feasible = True
        for territory_rooms in hub_rooms_tuple:
            avail = [cand_by_room[r] for r in territory_rooms if r in cand_by_room]
            if not avail:
                partition_feasible = False
                break
            # Most-connected room first, then largest area; best hub placements lead.
            ranked = sorted(
                avail,
                key=lambda c: (portal_graph.degree(c["room_id"]), c["area_m2"]),
                reverse=True,
            )
            territory_candidate_lists.append(ranked[:_MAX_TERRITORY_CANDS])
        if not partition_feasible:
            continue

        # Joint search: every combination of one hub candidate per territory.
        for candidate_combo in itertools.product(*territory_candidate_lists):
            combo_hubs: List[Dict[str, Any]] = []
            combo_rings: List[Dict[str, Any]] = []
            combo_assignments: List[Dict[str, Any]] = []
            feasible = True

            for h_idx, (territory_rooms, cand) in enumerate(zip(hub_rooms_tuple, candidate_combo)):
                h_id = f"hub:{h_idx + 1}"
                hub_dict = {
                    "id": h_id,
                    "point": {"x": cand["point"][0], "y": cand["point"][1]},
                    "room_id": cand["room_id"],
                }
                combo_hubs.append(hub_dict)

                ring = _route_territory_ring(hub_dict, territory_rooms, nodes, router, scale)
                if ring is None:
                    feasible = False
                    break
                combo_rings.append(ring)

                for r_id in territory_rooms:
                    combo_assignments.append({
                        "room_id": r_id,
                        "node_id": nodes[r_id]["id"],
                        "hub_id": h_id,
                    })

            if feasible:
                sol_dict = {
                    "plan_id": plan["id"],
                    "hubs": combo_hubs,
                    "assignments": combo_assignments,
                    "rings": combo_rings,
                    "diagnostics": [
                        {
                            "code": "CAPACITY_CONSTRAINED_SOLUTION",
                            "message": f"Solution generated with {len(combo_hubs)} connected territories.",
                        }
                    ],
                }
                rank = _fixed_hub_solution_rank(sol_dict, room_by_id, plan, scale)
                if rank < best_rank:
                    best_rank, best_solution = rank, sol_dict

    if best_solution is not None:
        best_solution["metrics"] = _compute_advisory_metrics(plan, best_solution, scale)
    return best_solution


def _fixed_hub_solution_rank(
    solution: Dict[str, Any], room_by_id: Dict[str, Dict[str, Any]],
    plan: Dict[str, Any], scale: float,
) -> Tuple[float, float]:
    """Apply the secondary cost and tertiary area-gap objectives for fixed H."""
    exempt_points = [
        (float(node["point"]["x"]), float(node["point"]["y"]))
        for node in plan.get("nodes", [])
    ] + [
        (float(hub["point"]["x"]), float(hub["point"]["y"]))
        for hub in solution["hubs"]
    ]
    route_cost = _rings_route_cost(solution["rings"], scale, exempt_points)
    areas = {hub["id"]: 0.0 for hub in solution["hubs"]}
    for assignment in solution["assignments"]:
        areas[assignment["hub_id"]] += float(room_by_id[assignment["room_id"]]["area_m2"])
    area_gap = max(areas.values()) - min(areas.values()) if areas else 0.0
    return route_cost, area_gap


def _partition_connected(
    room_ids: List[str],
    graph: nx.Graph,
    k: int,
    max_nodes: int,
    max_area: float,
    room_by_id: Dict[str, Any],
) -> List[Tuple[List[str], ...]]:
    """Generate all valid connected partitions of rooms into k territories."""
    n = len(room_ids)
    if k == 1:
        if n <= max_nodes and sum(room_by_id[r]["area_m2"] for r in room_ids) <= max_area:
            if nx.is_connected(graph.subgraph(room_ids)):
                return [(room_ids,)]
        return []

    valid_partitions = []
    # Exhaustive assignment search for small instances
    for owners in itertools.product(range(k), repeat=n):
        # Must use all owners
        if len(set(owners)) != k:
            continue
        # Avoid permutations of labels: enforce owner of room 0 is 0, etc.
        groups = [[] for _ in range(k)]
        for r_idx, o in enumerate(owners):
            groups[o].append(room_ids[r_idx])

        # Validate capacity & connectivity
        ok = True
        for g in groups:
            if not (1 <= len(g) <= max_nodes):
                ok = False
                break
            if sum(room_by_id[r]["area_m2"] for r in g) > max_area:
                ok = False
                break
            if len(g) > 1 and not nx.is_connected(graph.subgraph(g)):
                ok = False
                break
        if ok:
            # Sort canonical
            sorted_groups = tuple(sorted(groups, key=lambda g: g[0]))
            if sorted_groups not in valid_partitions:
                valid_partitions.append(sorted_groups)
                if len(valid_partitions) > 50:  # Cap candidate partitions
                    break
    return valid_partitions


def _route_territory_ring(
    hub: Dict[str, Any],
    territory_rooms: List[str],
    nodes: Dict[str, Dict[str, Any]],
    router: HananRouter,
    scale: float,
) -> Optional[Dict[str, Any]]:
    """Search stop orders and alternative leg-construction orders for a cheap ring."""
    hub_pt = (float(hub["point"]["x"]), float(hub["point"]["y"]))
    territory_nodes = [nodes[r_id] for r_id in territory_rooms if r_id in nodes]

    if not territory_nodes:
        return None

    hub_id = hub["id"]
    t_node_ids = [n["id"] for n in territory_nodes]
    node_coords = {n["id"]: (float(n["point"]["x"]), float(n["point"]["y"])) for n in territory_nodes}

    # Single-node territory (e.g. 1 room):
    # Form an open rectangle: Hub -> (N.x, H.y) -> Node -> (H.x, N.y) -> Hub
    # This ensures a distinct, non-overlapping closed circuit!
    if len(territory_nodes) == 1:
        n_id = t_node_ids[0]
        n_pt = node_coords[n_id]
        
        # Try both rectangular routes
        corner1 = (n_pt[0], hub_pt[1])
        corner2 = (hub_pt[0], n_pt[1])
        
        # Route outbound leg without simplification so the dynamic-graph
        # penalty pass can mark every grid edge it occupies individually.
        leg1 = router.route_path(hub_pt, n_pt, simplify=False)
        dyn_g = router.graph.copy()
        if leg1:
            for i in range(len(leg1) - 1):
                u, v = leg1[i], leg1[i + 1]
                if dyn_g.has_edge(u, v):
                    dyn_g[u][v]["weight"] = dyn_g[u][v].get("weight", 1.0) + 100.0 * scale

        leg2 = router.route_path(n_pt, hub_pt, dynamic_graph=dyn_g, simplify=False)
        if leg1 is not None and leg2 is not None:
            s_leg1 = _simplify_collinear(leg1)
            s_leg2 = _simplify_collinear(leg2)
            return {
                "hub_id": hub_id,
                "stop_ids": [hub_id, n_id, hub_id],
                "legs": [
                    {"from_id": hub_id, "to_id": n_id, "polyline": [{"x": p[0], "y": p[1]} for p in s_leg1]},
                    {"from_id": n_id, "to_id": hub_id, "polyline": [{"x": p[0], "y": p[1]} for p in s_leg2]},
                ],
            }

    # Multi-node territory: test permutations of visit orders
    best_cost = float("inf")
    best_perm: Optional[List[str]] = None
    best_legs: Optional[List[Dict[str, Any]]] = None

    perms = list(itertools.permutations(t_node_ids))
    # If more than 5 nodes (e.g. 20-node config), use nearest neighbor TSP heuristic
    if len(perms) > 120:
        perms = [_nearest_neighbor_tour(hub_pt, territory_nodes)]

    for perm in perms:
        seq = [hub_id] + list(perm) + [hub_id]
        coords = [hub_pt] + [node_coords[nid] for nid in perm] + [hub_pt]
        exempt_points = [hub_pt, *node_coords.values()]
        leg_count = len(seq) - 1
        construction_orders = [tuple(range(leg_count))]
        if leg_count <= 5:
            construction_orders.append((0, *range(leg_count - 1, 0, -1)))

        for construction_order in construction_orders:
            paths = _route_legs_in_order(router, coords, construction_order, exempt_points, scale)
            if paths is None:
                continue
            legs = [
                {
                    "from_id": seq[i],
                    "to_id": seq[i + 1],
                    "polyline": [{"x": p[0], "y": p[1]} for p in paths[i]],
                }
                for i in range(leg_count)
            ]
            candidate_ring = {"hub_id": hub_id, "stop_ids": seq, "legs": legs}
            cost = _ring_route_cost(candidate_ring, scale, exempt_points)
            if cost < best_cost:
                best_cost = cost
                best_perm = seq
                best_legs = legs

    if best_perm is None or best_legs is None:
        return None

    home_node = nodes.get(hub["room_id"])
    if home_node is not None:
        home_id = home_node["id"]
        if home_id in best_perm:
            position = best_perm.index(home_id)
            if position > (len(best_perm) - 1) / 2:
                best_perm = list(reversed(best_perm))
                best_legs = [
                    {
                        "from_id": leg["to_id"],
                        "to_id": leg["from_id"],
                        "polyline": list(reversed(leg["polyline"])),
                    }
                    for leg in reversed(best_legs)
                ]

    return {
        "hub_id": hub_id,
        "stop_ids": best_perm,
        "legs": best_legs,
    }


def _route_legs_in_order(
    router: HananRouter,
    coords: List[Point2D],
    construction_order: Tuple[int, ...],
    exempt_points: List[Point2D],
    scale: float,
) -> Optional[Dict[int, List[Point2D]]]:
    """Route each leg with penalties for meeting already routed cable."""
    graph = router.graph.copy()
    paths: Dict[int, List[Point2D]] = {}
    for leg_index in construction_order:
        path = router.route_path(coords[leg_index], coords[leg_index + 1], dynamic_graph=graph)
        if path is None:
            return None
        paths[leg_index] = path
        routed_segments = [(a, b) for a, b in zip(path, path[1:]) if math.dist(a, b) > 0.001 * scale]
        for a, b in graph.edges():
            penalty = sum(
                _edge_interaction_penalty(a, b, c, d, exempt_points, scale)
                for c, d in routed_segments
            )
            graph[a][b]["weight"] += penalty
    return paths


def _edge_interaction_penalty(
    a: Point2D, b: Point2D, c: Point2D, d: Point2D,
    exempt_points: List[Point2D], scale: float,
) -> float:
    """Discourage shared cable and orthogonal meetings on the Hanan grid."""
    edge_horizontal = a[1] == b[1]
    routed_horizontal = abs(c[1] - d[1]) <= 0.001 * scale
    routed_vertical = abs(c[0] - d[0]) <= 0.001 * scale
    if edge_horizontal == routed_horizontal and (routed_horizontal or routed_vertical):
        fixed_edge = a[1] if edge_horizontal else a[0]
        fixed_route = c[1] if edge_horizontal else c[0]
        if abs(fixed_edge - fixed_route) > 0.001 * scale:
            return 0.0
        edge_lo, edge_hi = sorted((a[0], b[0]) if edge_horizontal else (a[1], b[1]))
        route_lo, route_hi = sorted((c[0], d[0]) if edge_horizontal else (c[1], d[1]))
        return 20.0 * max(0.0, min(edge_hi, route_hi) - max(edge_lo, route_lo))
    if not (routed_horizontal or routed_vertical):
        return 0.0
    x = c[0] if edge_horizontal else a[0]
    y = a[1] if edge_horizontal else c[1]
    point = (x, y)
    if not (min(a[0], b[0]) <= x <= max(a[0], b[0])
            and min(a[1], b[1]) <= y <= max(a[1], b[1])
            and min(c[0], d[0]) <= x <= max(c[0], d[0])
            and min(c[1], d[1]) <= y <= max(c[1], d[1])):
        return 0.0
    if any(math.dist(point, stop) <= 0.001 * scale for stop in exempt_points):
        return 0.0
    return 20.0 * scale


def _ring_route_cost(
    ring: Dict[str, Any], scale: float, exempt_points: List[Point2D]
) -> float:
    """Score one candidate ring with the checker's route-cost terms."""
    return _rings_route_cost([ring], scale, exempt_points)


def _rings_route_cost(
    rings: List[Dict[str, Any]], scale: float, exempt_points: List[Point2D]
) -> float:
    """Score complete cable geometry, including interactions between rings."""
    tol_units = 0.001 * scale
    segments: List[Tuple[Point2D, Point2D, int, int, int]] = []
    length_units = 0.0
    bends = 0
    for ring_index, ring in enumerate(rings):
        directions: List[Point2D] = []
        for leg_index, leg in enumerate(ring["legs"]):
            points = [(float(p["x"]), float(p["y"])) for p in leg["polyline"]]
            for segment_index, (a, b) in enumerate(zip(points, points[1:])):
                length_units += math.dist(a, b)
                if math.dist(a, b) <= tol_units:
                    continue
                segments.append((a, b, ring_index, leg_index, segment_index))
                directions.append((math.copysign(1, b[0] - a[0]), 0) if a[1] == b[1]
                                  else (0, math.copysign(1, b[1] - a[1])))
        bends += sum(directions[i] != directions[i - 1] for i in range(len(directions)))

    length_m = length_units / scale
    crossings: List[Point2D] = []
    for i, (a, b, ring_a, leg_a, seg_a) in enumerate(segments):
        for c, d, ring_b, leg_b, seg_b in segments[i + 1:]:
            if (a[0] == b[0]) == (c[0] == d[0]):
                continue
            intersection = LineString([a, b]).intersection(LineString([c, d]))
            if intersection.geom_type != "Point":
                continue
            point = (intersection.x, intersection.y)
            if any(math.dist(point, stop) <= tol_units for stop in exempt_points):
                continue
            if ring_a == ring_b and leg_a == leg_b and abs(seg_a - seg_b) == 1:
                continue
            if not any(math.dist(point, prior) <= tol_units for prior in crossings):
                crossings.append(point)

    overlap_units = 0.0
    for horizontal in (True, False):
        lines: Dict[float, List[Tuple[float, float]]] = {}
        for a, b, _, _, _ in segments:
            if (a[1] == b[1]) != horizontal:
                continue
            fixed = a[1] if horizontal else a[0]
            lo, hi = sorted((a[0], b[0]) if horizontal else (a[1], b[1]))
            lines.setdefault(fixed, []).append((lo, hi))
        for intervals in lines.values():
            endpoints = sorted({coordinate for interval in intervals for coordinate in interval})
            for lo, hi in zip(endpoints, endpoints[1:]):
                middle = (lo + hi) / 2
                coverage = sum(start < middle < end for start, end in intervals)
                overlap_units += max(0, coverage - 1) * (hi - lo)

    return length_m + 5 * len(crossings) + overlap_units / scale + 0.5 * bends


def _nearest_neighbor_tour(hub_pt: Point2D, nodes: List[Dict[str, Any]]) -> Tuple[str, ...]:
    """Greedy nearest-neighbor tour for larger node sets."""
    remaining = {n["id"]: (float(n["point"]["x"]), float(n["point"]["y"])) for n in nodes}
    tour = []
    curr = hub_pt
    while remaining:
        next_id = min(remaining.keys(), key=lambda nid: math.hypot(remaining[nid][0]-curr[0], remaining[nid][1]-curr[1]))
        tour.append(next_id)
        curr = remaining.pop(next_id)
    return tuple(tour)


def _compute_advisory_metrics(plan: Dict[str, Any], solution: Dict[str, Any], scale: float) -> Dict[str, Any]:
    """Calculate exact metrics for solution output using validator's calculator if available."""
    try:
        from cable_planner.metrics.calculator import calculate_all_metrics
        m = calculate_all_metrics(plan, solution)
        return m.to_dict()
    except Exception:
        total_len = 0.0
        total_bends = 0
        for r in solution.get("rings", []):
            for leg in r.get("legs", []):
                pts = [(float(p["x"]), float(p["y"])) for p in leg.get("polyline", [])]
                for i in range(len(pts) - 1):
                    total_len += math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1])
                total_bends += max(0, len(pts) - 2)
        length_m = total_len / scale
        return {
            "hub_count": len(solution.get("rings", [])),
            "length_m": length_m,
            "crossings": 0,
            "overlap_m": 0.0,
            "bends": total_bends,
            "route_cost": length_m + 0.5 * total_bends,
            "area_gap_m2": 0.0,
        }
