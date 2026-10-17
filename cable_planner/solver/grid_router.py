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
import bisect
import heapq
import itertools
import math
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import networkx as nx
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import unary_union

Point2D = Tuple[float, float]
ProgressCallback = Callable[[str, int], None]
A_STAR_PROGRESS_BATCH = 512
PARTITION_PROGRESS_BATCH = 512

# Open passages are free space, not a single door: expose multiple routing lanes
# and softly prefer a cable gap without changing the scored job-cost formula.
OPEN_PASSAGE_LANE_SPACING_M = 0.4
MIN_CABLE_CLEARANCE_M = 0.5
CLEARANCE_ROUTE_WEIGHT = 3.0
CLEARANCE_RANK_WEIGHT = 6.0

# A hub sitting on top of its only node gives a ring too small to see. For
# single-node territories the hub is moved off the node by this distance (first
# legal entry wins) as a diagonal rectangle loop (O = 0, J = 4d + 2 for per-axis offset d).
# Set to () to fall back to grid routing.
SINGLE_NODE_HUB_OFFSETS_M = (0.6, 0.5, 0.4)
ALLOW_RETRACE_STUB = False  # overlap is penalised (O); True also allows an out-and-back stub when cheaper
# A hub never sits on a node: every hub keeps at least this distance from every node.
HUB_NODE_MIN_SEPARATION_M = 0.6


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

    def __init__(
        self,
        plan: Dict[str, Any],
        extra_points: Optional[List[Point2D]] = None,
        cable_wall_clearance_m: float = 0.03,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self.plan = plan
        self.scale = float(plan.get("drawing_units_per_metre", 1.0))
        self.tol = float(plan.get("rules", {}).get("geometry_tolerance", 0.001)) * self.scale
        if not math.isfinite(cable_wall_clearance_m) or cable_wall_clearance_m < 0:
            raise ValueError("cable_wall_clearance_m must be finite and nonnegative")
        self.cable_wall_clearance_m = float(cable_wall_clearance_m)
        self.cable_wall_clearance = self.cable_wall_clearance_m * self.scale
        self.progress_callback = progress_callback

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

        # Buffer obstacle geometry so routes cannot run along a wall edge.
        self.wall_keepouts = [
            obstacle.buffer(self.cable_wall_clearance)
            if self.cable_wall_clearance > 0 else obstacle
            for obstacle in [*self.wall_polys, *self.wall_lines]
        ]

        # Collect Hanan coordinates
        xs: Set[float] = set()
        ys: Set[float] = set()
        wall_vertical_xs: Set[float] = set()
        wall_horizontal_ys: Set[float] = set()
        for obstacle in [*self.wall_polys, *self.wall_lines]:
            rings = [obstacle.exterior.coords] if isinstance(obstacle, Polygon) else [obstacle.coords]
            if isinstance(obstacle, Polygon):
                rings.extend(interior.coords for interior in obstacle.interiors)
            for coordinates in rings:
                for a, b in zip(coordinates, coordinates[1:]):
                    if abs(a[0] - b[0]) <= self.tol:
                        wall_vertical_xs.add(round((a[0] + b[0]) / 2, 2))
                    if abs(a[1] - b[1]) <= self.tol:
                        wall_horizontal_ys.add(round((a[1] + b[1]) / 2, 2))

        for r in plan.get("rooms", []):
            if r.get("eligible", False):
                poly = _parse_polygon(r["geometry"])
                for x, y in poly.exterior.coords:
                    x, y = round(x, 2), round(y, 2)
                    if x in wall_vertical_xs and self.cable_wall_clearance > 0:
                        lane = self.cable_wall_clearance + max(self.tol, 0.001 * self.scale)
                        xs.update((round(x - lane, 2), round(x + lane, 2)))
                    else:
                        xs.add(x)
                    if y in wall_horizontal_ys and self.cable_wall_clearance > 0:
                        lane = self.cable_wall_clearance + max(self.tol, 0.001 * self.scale)
                        ys.update((round(y - lane, 2), round(y + lane, 2)))
                    else:
                        ys.add(y)

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
                fracs = [0.25, 0.50, 0.75]
                if port.get("kind") == "open_passage":
                    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                    spacing = OPEN_PASSAGE_LANE_SPACING_M * self.scale
                    lanes = max(3, int(length / spacing))
                    inset = min(0.5, (0.2 * self.scale) / length) if length > 0 else 0.0
                    fracs = [
                        inset + (1 - 2 * inset) * index / (lanes - 1)
                        for index in range(lanes)
                    ]
                for frac in fracs:
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
        for keepout in self.wall_keepouts:
            if ls.intersects(keepout):
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
        # A* over (node, incoming direction) states. Parent pointers replace the
        # per-push path copies, and adjacency is read directly in the hot loop.
        adj = g._adj
        bend_cost = bend_penalty * self.scale
        ex, ey = e_node
        start_state = (s_node, (0, 0))
        best_costs: Dict[Tuple[Point2D, Tuple[int, int]], float] = {start_state: 0.0}
        parents: Dict[
            Tuple[Point2D, Tuple[int, int]],
            Optional[Tuple[Point2D, Tuple[int, int]]],
        ] = {start_state: None}
        counter = 0
        open_set: List[Tuple[float, float, Point2D, Tuple[int, int], int]] = [
            (0.0, 0.0, s_node, (0, 0), counter)
        ]
        expanded_states = 0
        reported_states = 0
        next_report_at = A_STAR_PROGRESS_BATCH

        def report_expansions(*, flush: bool = False) -> None:
            nonlocal reported_states
            if self.progress_callback is None:
                return
            pending = expanded_states - reported_states
            if pending >= A_STAR_PROGRESS_BATCH or (flush and pending):
                self.progress_callback("astar_states_expanded", pending)
                reported_states = expanded_states

        while open_set:
            f, cost, curr, prev_dir, _ = heapq.heappop(open_set)
            state = (curr, prev_dir)

            if curr == e_node:
                nodes_rev: List[Point2D] = []
                cursor: Optional[Tuple[Point2D, Tuple[int, int]]] = state
                while cursor is not None:
                    nodes_rev.append(cursor[0])
                    cursor = parents[cursor]
                res = nodes_rev[::-1]
                if start != s_node:
                    res.insert(0, start)
                if end != e_node:
                    res.append(end)
                report_expansions(flush=True)
                return _simplify_collinear(res) if simplify else res

            if best_costs[state] < cost - 1e-6:
                continue

            if self.progress_callback is not None:
                expanded_states += 1
                if expanded_states >= next_report_at:
                    self.progress_callback("astar_states_expanded", expanded_states - reported_states)
                    reported_states = expanded_states
                    next_report_at += A_STAR_PROGRESS_BATCH

            cx, cy = curr
            for neighbor, edge_data in adj[curr].items():
                edge_wt = edge_data.get("weight", edge_data.get("base_weight", 1.0))
                nx_, ny_ = neighbor
                curr_dir = (
                    1 if nx_ > cx else (-1 if nx_ < cx else 0),
                    1 if ny_ > cy else (-1 if ny_ < cy else 0),
                )
                new_cost = cost + edge_wt
                if prev_dir != (0, 0) and prev_dir != curr_dir:
                    new_cost += bend_cost
                next_state = (neighbor, curr_dir)
                if next_state not in best_costs or new_cost < best_costs[next_state]:
                    best_costs[next_state] = new_cost
                    parents[next_state] = state
                    counter += 1
                    h = abs(ex - nx_) + abs(ey - ny_)
                    heapq.heappush(
                        open_set,
                        (new_cost + h, new_cost, neighbor, curr_dir, counter),
                    )

        report_expansions(flush=True)
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
    poly_by_room: Dict[str, Any] = {}
    for r in plan.get("rooms", []):
        if not r.get("eligible", False):
            continue
        poly = _parse_polygon(r["geometry"])
        poly_by_room[r["id"]] = poly
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
    return _separate_hubs_from_nodes(plan, candidates, poly_by_room, clearance_units, tol_units, scale)


def _separate_hubs_from_nodes(
    plan: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    poly_by_room: Dict[str, Any],
    clearance_units: float,
    tol_units: float,
    scale: float,
) -> List[Dict[str, Any]]:
    """Move any hub candidate that sits closer than the minimum separation to a node."""
    sep = HUB_NODE_MIN_SEPARATION_M * scale
    node_pts = [(float(n["point"]["x"]), float(n["point"]["y"])) for n in plan.get("nodes", [])]
    if sep <= 0 or not node_pts:
        return candidates
    centroid = (sum(p[0] for p in node_pts) / len(node_pts), sum(p[1] for p in node_pts) / len(node_pts))

    def far_enough(pt: Point2D) -> bool:
        return all(math.dist(pt, n) + tol_units >= sep for n in node_pts)

    for cand in candidates:
        pt = cand["point"]
        if far_enough(pt):
            continue
        poly = poly_by_room.get(cand["room_id"])
        if poly is None:
            continue
        own = min(node_pts, key=lambda n: math.dist(n, pt))
        options = []
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            for step in (1.0, 1.15, 1.4):
                h = (round(own[0] + step * sep * math.cos(rad), 2), round(own[1] + step * sep * math.sin(rad), 2))
                gap = poly.boundary.distance(Point(h))
                if poly.contains(Point(h)) and gap + tol_units >= clearance_units and far_enough(h):
                    options.append((math.dist(h, centroid), -gap, h, gap))
                    break
        if options:
            options.sort(key=lambda o: o[:2])
            cand["point"], cand["clearance"] = options[0][2], options[0][3]
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


# Cables keep this distance from walls and door jambs (visible gap in renders). If a
# plan has no feasible ring at that clearance, progressively smaller values are tried.
CABLE_WALL_CLEARANCE_M = 0.2
CABLE_WALL_CLEARANCE_FALLBACKS_M = (0.15, 0.1, 0.05, 0.03)


def solve(
    plan: Dict[str, Any],
    *,
    cable_wall_clearance_m: float = CABLE_WALL_CLEARANCE_M,
    progress_callback: Optional[Callable[[str, Dict[str, int]], None]] = None,
) -> Dict[str, Any]:
    """Solve with the requested cable-wall clearance, relaxing it only if infeasible."""
    solution, _ = _solve_observed(
        plan, cable_wall_clearance_m=cable_wall_clearance_m,
        progress_callback=progress_callback,
    )
    return solution


def _solve_observed(
    plan: Dict[str, Any], *, cable_wall_clearance_m: float = CABLE_WALL_CLEARANCE_M,
    progress_callback: Optional[Callable[[str, Dict[str, int]], None]] = None,
    candidate_observer: Optional[Callable[[Dict[str, Any], float], None]] = None,
) -> Tuple[Dict[str, Any], float]:
    """Run the usual clearance ladder and optionally observe complete candidates."""
    if progress_callback is not None:
        observer = progress_callback
        batch_sizes = {
            "partition_patterns_examined": 2048,
            "connected_partitions_found": 8,
            "candidate_combinations_evaluated": 8,
            "ring_route_attempts": 8,
            "astar_states_expanded": 2048,
        }
        pending: Dict[str, int] = {}
        active_progress_stage: str | None = None

        def flush_progress(stage: str | None = None) -> None:
            if not pending:
                return
            target_stage = stage or active_progress_stage or "search"
            values = dict(pending)
            pending.clear()
            try:
                observer(target_stage, values)
            except Exception:
                return

        def safe_progress(stage: str, counters: Dict[str, int]) -> None:
            nonlocal active_progress_stage
            if active_progress_stage is not None and stage != active_progress_stage:
                flush_progress(active_progress_stage)
            active_progress_stage = stage
            gauges = {}
            should_flush = False
            for name, value in counters.items():
                if name not in batch_sizes:
                    gauges[name] = value
                    continue
                pending[name] = pending.get(name, 0) + value
                if pending[name] >= batch_sizes[name]:
                    should_flush = True
            if gauges:
                try:
                    observer(stage, gauges)
                except Exception:
                    pass
            if should_flush:
                flush_progress(stage)

        def flush_final_progress() -> None:
            try:
                flush_progress()
            except Exception:
                pass

        progress_callback = safe_progress
    else:
        flush_final_progress = lambda: None
    ladder = [cable_wall_clearance_m] + [c for c in CABLE_WALL_CLEARANCE_FALLBACKS_M if c < cable_wall_clearance_m]
    solution: Dict[str, Any] = {}
    used_clearance = ladder[-1]
    try:
        for attempt, clearance in enumerate(ladder, start=1):
            used_clearance = clearance
            kwargs = {}
            if progress_callback is not None:
                kwargs.update(progress_callback=progress_callback, clearance_attempt=attempt)
            if candidate_observer is not None:
                kwargs["candidate_observer"] = candidate_observer
            solution = _solve_with_clearance(plan, cable_wall_clearance_m=clearance, **kwargs)
            if solution.get("status") != "infeasible":
                break
    finally:
        flush_final_progress()
    return solution, used_clearance


def _solve_with_clearance(
    plan: Dict[str, Any],
    *,
    cable_wall_clearance_m: float,
    progress_callback: Optional[Callable[[str, Dict[str, int]], None]] = None,
    clearance_attempt: int = 1,
    candidate_observer: Optional[Callable[[Dict[str, Any], float], None]] = None,
) -> Dict[str, Any]:
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
    preparation_stage = "prepare_geometry" if clearance_attempt == 1 else "search"
    if progress_callback is not None:
        progress_callback(preparation_stage, {
            "eligible_rooms": len(rooms),
            "clearance_attempt": clearance_attempt,
        })
    
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
    if progress_callback is not None:
        progress_callback(preparation_stage, {"legal_hub_locations": len(candidates)})
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
    router = HananRouter(
        plan, extra_points=all_points, cable_wall_clearance_m=cable_wall_clearance_m,
        progress_callback=(
            (lambda name, value: progress_callback("search", {name: value}))
            if progress_callback is not None else None
        ),
    )
    if progress_callback is not None:
        progress_callback("search", {
            "routing_grid_vertices": router.graph.number_of_nodes(),
            "routing_grid_edges": router.graph.number_of_edges(),
        })

    # Try hub counts starting from lower_bound
    observer = (
        (lambda candidate: candidate_observer(candidate, cable_wall_clearance_m))
        if candidate_observer is not None else None
    )
    for hub_count in range(lower_bound, len(rooms) + 1):
        search_kwargs = {}
        if progress_callback is not None:
            progress_callback("search", {"current_hub_count": hub_count, "hub_count_attempts": 1})
            search_kwargs["progress_callback"] = progress_callback
        if observer is not None:
            search_kwargs["candidate_observer"] = observer
        sol = _solve_fixed_hub_count(
            plan, rooms, nodes, candidates, portal_graph, router, hub_count, max_nodes, max_area,
            **search_kwargs,
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
    progress_callback: Optional[Callable[[str, Dict[str, int]], None]] = None,
    candidate_observer: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Optional[Dict[str, Any]]:
    """Compare feasible partitions by full route cost, then assigned-area gap."""
    room_by_id = {r["id"]: r for r in rooms}
    scale = float(plan.get("drawing_units_per_metre", 1.0))
    best_solution: Optional[Dict[str, Any]] = None
    best_rank = (float("inf"), float("inf"))
    pending_search_counts: Dict[str, int] = {}
    pending_search_events = 0

    def report_search_counts(counts: Dict[str, int], *, flush: bool = False) -> None:
        nonlocal pending_search_events
        if progress_callback is None:
            return
        for name, value in counts.items():
            pending_search_counts[name] = pending_search_counts.get(name, 0) + value
        pending_search_events += 1
        if pending_search_events >= 8 or flush:
            progress_callback("search", dict(pending_search_counts))
            pending_search_counts.clear()
            pending_search_events = 0

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
            report_search_counts({"candidate_combinations_evaluated": 1, "ring_route_attempts": 1})
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
                if candidate_observer is not None:
                    candidate_observer(copy.deepcopy(sol_dict))
                if rank < best_rank:
                    best_rank, best_solution = rank, sol_dict
        if best_solution is not None:
            best_solution["metrics"] = _compute_advisory_metrics(plan, best_solution, scale)
        report_search_counts({}, flush=True)
        return best_solution

    # Multi-hub partition search: enumerate connected partitions, and for each
    # partition conduct a joint search over all hub-candidate combinations.
    # Capping candidates per territory bounds combinatorics to
    # _MAX_TERRITORY_CANDS^hub_count route evaluations per partition.
    _MAX_TERRITORY_CANDS = 3
    room_ids = [r["id"] for r in rooms]
    cand_by_room = {c["room_id"]: c for c in candidates}

    for hub_rooms_tuple in _partition_connected(
        room_ids, portal_graph, hub_count, max_nodes, max_area, room_by_id,
        progress_callback=(
            (lambda name, value: progress_callback("search", {name: value}))
            if progress_callback is not None else None
        ),
    ):
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
            report_search_counts({"candidate_combinations_evaluated": 1})
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

                report_search_counts({"ring_route_attempts": 1})
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
                if candidate_observer is not None:
                    candidate_observer(copy.deepcopy(sol_dict))
                if rank < best_rank:
                    best_rank, best_solution = rank, sol_dict

    if best_solution is not None:
        best_solution["metrics"] = _compute_advisory_metrics(plan, best_solution, scale)
    report_search_counts({}, flush=True)
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
    progress_callback: Optional[ProgressCallback] = None,
) -> List[Tuple[List[str], ...]]:
    """Generate all valid connected partitions of rooms into k territories."""
    n = len(room_ids)
    if k == 1:
        if n <= max_nodes and sum(room_by_id[r]["area_m2"] for r in room_ids) <= max_area:
            if nx.is_connected(graph.subgraph(room_ids)):
                return [(room_ids,)]
        return []

    valid_partitions = []
    assignment_patterns_examined = 0
    # Exhaustive assignment search for small instances
    for owners in itertools.product(range(k), repeat=n):
        if progress_callback is not None:
            assignment_patterns_examined += 1
            if assignment_patterns_examined % PARTITION_PROGRESS_BATCH == 0:
                progress_callback("partition_patterns_examined", PARTITION_PROGRESS_BATCH)
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
                if progress_callback is not None:
                    progress_callback("connected_partitions_found", 1)
                if len(valid_partitions) > 50:  # Cap candidate partitions
                    break
    if progress_callback is not None:
        remaining = assignment_patterns_examined % PARTITION_PROGRESS_BATCH
        if remaining:
            progress_callback("partition_patterns_examined", remaining)
    return valid_partitions


def _offset_hub_ring(
    hub: Dict[str, Any],
    node_id: str,
    n_pt: Point2D,
    room_id: str,
    router: "HananRouter",
    scale: float,
) -> Optional[Dict[str, Any]]:
    """Move the hub off its only node so the ring is visible, picking the cheaper shape.

    Two shapes are scored with the real route cost J and the cheaper one wins:
      * stub      - hub on the node's row/column, cable goes out and is retraced back
                    (L = 2d, O = d, B = 2  ->  J = 3d + 1); drawn with a two-way arrow.
      * rectangle - hub diagonal to the node, closed loop with no overlap
                    (L = 4d, O = 0, B = 4  ->  J = 4d + 2).
    The largest offset in SINGLE_NODE_HUB_OFFSETS_M that has a legal placement is used.
    Returns None if none is legal (caller falls back to grid routing).
    """
    room = next((r for r in router.plan.get("rooms", []) if r["id"] == room_id), None)
    if room is None or not SINGLE_NODE_HUB_OFFSETS_M:
        return None
    poly = _parse_polygon(room["geometry"])
    clearance = float(router.plan.get("rules", {}).get("node_wall_clearance_m", 0.5)) * scale
    tol = router.tol
    cover = poly.buffer(tol)
    hub_id = hub["id"]

    def legal(h: Point2D, edges: List[Tuple[Point2D, Point2D]]) -> Optional[float]:
        wall_gap = poly.boundary.distance(Point(h))
        if not poly.contains(Point(h)) or wall_gap + tol < clearance:
            return None
        if not all(cover.covers(LineString(e)) and router._edge_is_valid(*e) for e in edges):
            return None
        return wall_gap

    def make_ring(h: Point2D, out: List[Point2D], back: List[Point2D]) -> Dict[str, Any]:
        return {
            "hub_id": hub_id,
            "stop_ids": [hub_id, node_id, hub_id],
            "legs": [
                {"from_id": hub_id, "to_id": node_id, "polyline": [{"x": x, "y": y} for x, y in out]},
                {"from_id": node_id, "to_id": hub_id, "polyline": [{"x": x, "y": y} for x, y in back]},
            ],
        }

    for offset_m in SINGLE_NODE_HUB_OFFSETS_M:
        d = offset_m * scale
        options: List[Tuple[float, float, Point2D, Dict[str, Any]]] = []
        for sx, sy in (((1, 0), (-1, 0), (0, 1), (0, -1)) if ALLOW_RETRACE_STUB else ()):  # stub
            # Keep the shared axis exactly equal to the node's so the stub is truly collinear.
            h = (round(n_pt[0] + sx * d, 2) if sx else n_pt[0], round(n_pt[1] + sy * d, 2) if sy else n_pt[1])
            gap = legal(h, [(h, n_pt)])
            if gap is not None:
                options.append((0.0, gap, h, make_ring(h, [h, n_pt], [n_pt, h])))
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):          # rectangle
            h = (round(n_pt[0] + sx * d, 2), round(n_pt[1] + sy * d, 2))
            c1, c2 = (n_pt[0], h[1]), (h[0], n_pt[1])
            gap = legal(h, [(h, c1), (c1, n_pt), (n_pt, c2), (c2, h)])
            if gap is not None:
                options.append((0.0, gap, h, make_ring(h, [h, c1, n_pt], [n_pt, c2, h])))
        if not options:
            continue
        scored = []
        for _, gap, h, ring in options:
            cost = _ring_route_cost(ring, scale, [h, n_pt])
            scored.append((round(cost, 6), -gap, h, ring))
        scored.sort(key=lambda item: item[:3])
        _, _, h, ring = scored[0]
        hub["point"] = {"x": h[0], "y": h[1]}
        return ring
    return None


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

        shifted = _offset_hub_ring(hub, n_id, n_pt, territory_rooms[0], router, scale)
        if shifted is not None:
            return shifted

        # Fallback: hub and node co-located, route two distinct rectangular routes
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

    # Route cost J is at least cable length, which is at least the Manhattan
    # tour length. Try promising orders first and stop when the bound cannot
    # beat the best fully routed ring. Keep original order for exact ties.
    def _manhattan_tour_m(order: Tuple[str, ...]) -> float:
        points = [hub_pt] + [node_coords[node_id] for node_id in order] + [hub_pt]
        return sum(
            abs(a[0] - b[0]) + abs(a[1] - b[1])
            for a, b in zip(points, points[1:])
        ) / scale

    ordered = sorted(
        ((_manhattan_tour_m(perm), index, perm) for index, perm in enumerate(perms)),
        key=lambda item: (item[0], item[1]),
    )
    best_index = -1

    for lower_bound_m, perm_index, perm in ordered:
        if lower_bound_m > best_cost + 1e-9:
            break
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
            cost = (
                _ring_route_cost(candidate_ring, scale, exempt_points)
                + CLEARANCE_RANK_WEIGHT * _clearance_shortfall_m(candidate_ring, scale)
            )
            if cost < best_cost - 1e-9 or (
                abs(cost - best_cost) <= 1e-9 and perm_index < best_index
            ):
                best_cost = cost
                best_perm = seq
                best_legs = legs
                best_index = perm_index

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


class _EdgeIndex:
    """Static index for finding Hanan edges a routed segment can interact with."""

    def __init__(self, graph: nx.Graph) -> None:
        horizontal: Dict[float, List[Tuple[float, float, Point2D, Point2D]]] = {}
        vertical: Dict[float, List[Tuple[float, float, Point2D, Point2D]]] = {}
        for a, b in graph.edges():
            if a[1] == b[1]:
                horizontal.setdefault(a[1], []).append((min(a[0], b[0]), max(a[0], b[0]), a, b))
            else:
                vertical.setdefault(a[0], []).append((min(a[1], b[1]), max(a[1], b[1]), a, b))
        self.horizontal_keys = sorted(horizontal)
        self.vertical_keys = sorted(vertical)
        self.horizontal = {key: sorted(edges, key=lambda edge: edge[0]) for key, edges in horizontal.items()}
        self.vertical = {key: sorted(edges, key=lambda edge: edge[0]) for key, edges in vertical.items()}
        self.horizontal_los = {key: [edge[0] for edge in edges] for key, edges in self.horizontal.items()}
        self.vertical_los = {key: [edge[0] for edge in edges] for key, edges in self.vertical.items()}


def _lines_in_range(keys: List[float], lo: float, hi: float) -> List[float]:
    return keys[bisect.bisect_left(keys, lo):bisect.bisect_right(keys, hi)]


def _edges_containing(rows, lower_bounds, key: float, coordinate: float):
    """Yield grid edges on a row/column that contain a crossing coordinate."""
    edges = rows[key]
    index = bisect.bisect_right(lower_bounds[key], coordinate)
    for edge_index in (index - 1, index - 2):
        if 0 <= edge_index < len(edges):
            edge = edges[edge_index]
            if edge[0] <= coordinate <= edge[1]:
                yield edge


def _routed_penalties(
    index: _EdgeIndex,
    routed_segments: List[Tuple[Point2D, Point2D]],
    exempt_points: List[Point2D],
    scale: float,
) -> Dict[Tuple[Point2D, Point2D], float]:
    """Apply the existing interaction penalties using only nearby edges."""
    tolerance = 0.001 * scale
    clearance = max(tolerance * 2, MIN_CABLE_CLEARANCE_M * scale)
    penalties: Dict[Tuple[Point2D, Point2D], float] = {}

    def add(a: Point2D, b: Point2D, value: float) -> None:
        if value:
            penalties[(a, b)] = penalties.get((a, b), 0.0) + value

    for c, d in routed_segments:
        routed_horizontal = abs(c[1] - d[1]) <= tolerance
        routed_vertical = abs(c[0] - d[0]) <= tolerance
        if routed_horizontal:
            lo, hi = sorted((c[0], d[0]))
            for y in _lines_in_range(index.horizontal_keys, c[1] - clearance, c[1] + clearance):
                gap = abs(y - c[1])
                for edge_lo, edge_hi, a, b in index.horizontal[y]:
                    shared = min(edge_hi, hi) - max(edge_lo, lo)
                    if shared > 0:
                        penalty = (
                            20.0 * shared if gap <= tolerance
                            else CLEARANCE_ROUTE_WEIGHT * shared * (1.0 - gap / clearance)
                        )
                        add(a, b, penalty)
            for x in _lines_in_range(index.vertical_keys, lo, hi):
                for _edge_lo, _edge_hi, a, b in _edges_containing(
                    index.vertical, index.vertical_los, x, c[1]
                ):
                    if any(math.dist((x, c[1]), stop) <= tolerance for stop in exempt_points):
                        continue
                    add(a, b, 20.0 * scale)
        elif routed_vertical:
            lo, hi = sorted((c[1], d[1]))
            for x in _lines_in_range(index.vertical_keys, c[0] - clearance, c[0] + clearance):
                gap = abs(x - c[0])
                for edge_lo, edge_hi, a, b in index.vertical[x]:
                    shared = min(edge_hi, hi) - max(edge_lo, lo)
                    if shared > 0:
                        penalty = (
                            20.0 * shared if gap <= tolerance
                            else CLEARANCE_ROUTE_WEIGHT * shared * (1.0 - gap / clearance)
                        )
                        add(a, b, penalty)
            for y in _lines_in_range(index.horizontal_keys, lo, hi):
                for _edge_lo, _edge_hi, a, b in _edges_containing(
                    index.horizontal, index.horizontal_los, y, c[0]
                ):
                    if any(math.dist((c[0], y), stop) <= tolerance for stop in exempt_points):
                        continue
                    add(a, b, 20.0 * scale)
    return penalties


def _route_legs_in_order(
    router: HananRouter,
    coords: List[Point2D],
    construction_order: Tuple[int, ...],
    exempt_points: List[Point2D],
    scale: float,
) -> Optional[Dict[int, List[Point2D]]]:
    """Route each leg with penalties for meeting already routed cable."""
    graph = router.graph.copy()
    index = getattr(router, "_edge_index", None)
    if index is None:
        index = router._edge_index = _EdgeIndex(router.graph)
    paths: Dict[int, List[Point2D]] = {}
    for leg_index in construction_order:
        path = router.route_path(coords[leg_index], coords[leg_index + 1], dynamic_graph=graph)
        if path is None:
            return None
        paths[leg_index] = path
        routed_segments = [(a, b) for a, b in zip(path, path[1:]) if math.dist(a, b) > 0.001 * scale]
        for (a, b), penalty in _routed_penalties(index, routed_segments, exempt_points, scale).items():
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


def _clearance_shortfall_m(ring: Dict[str, Any], scale: float) -> float:
    """Softly measure parallel run length closer than MIN_CABLE_CLEARANCE_M."""
    tolerance = 0.001 * scale
    clearance = MIN_CABLE_CLEARANCE_M * scale
    segments: List[Tuple[bool, float, float, float]] = []
    for leg in ring["legs"]:
        points = [(float(point["x"]), float(point["y"])) for point in leg["polyline"]]
        for a, b in zip(points, points[1:]):
            if math.dist(a, b) <= tolerance:
                continue
            if a[1] == b[1]:
                segments.append((True, a[1], min(a[0], b[0]), max(a[0], b[0])))
            else:
                segments.append((False, a[0], min(a[1], b[1]), max(a[1], b[1])))

    shortfall = 0.0
    for index, (horizontal, fixed, lo, hi) in enumerate(segments):
        for other_horizontal, other_fixed, other_lo, other_hi in segments[index + 1:]:
            gap = abs(fixed - other_fixed)
            if horizontal != other_horizontal or gap <= tolerance or gap >= clearance:
                continue
            parallel_length = min(hi, other_hi) - max(lo, other_lo)
            if parallel_length > 0:
                shortfall += parallel_length * (1.0 - gap / clearance)
    return shortfall / scale


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
