"""Independent metric calculations from submitted polylines and assignment geometry."""

import math
from typing import Any, Dict, List, Set, Tuple
from shapely.geometry import LineString, Point

from cable_planner.metrics.models import RecomputedMetrics


def _direction_vector(p1: Tuple[float, float], p2: Tuple[float, float], tol: float = 1e-4) -> Tuple[int, int]:
    """Return unit direction vector for axis-aligned segment: (dx, dy) in {-1, 0, 1}."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    if abs(dx) > tol and abs(dy) > tol:
        # Diagonal segment (will be flagged in hard-rule validation)
        # Approximate to dominant axis
        if abs(dx) >= abs(dy):
            return (1 if dx > 0 else -1, 0)
        else:
            return (0, 1 if dy > 0 else -1)
    if abs(dx) > tol:
        return (1 if dx > 0 else -1, 0)
    if abs(dy) > tol:
        return (0, 1 if dy > 0 else -1)
    return (0, 0)


def calculate_length_m(rings: List[Dict[str, Any]], drawing_units_per_metre: float) -> float:
    """Calculate total polyline length in metres over every leg, including retraced travel."""
    total_units = 0.0
    for ring in rings:
        for leg in ring.get("legs", []):
            pts = [(float(p["x"]), float(p["y"])) for p in leg.get("polyline", [])]
            for i in range(len(pts) - 1):
                p1, p2 = pts[i], pts[i + 1]
                dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                total_units += dist
    return total_units / drawing_units_per_metre


def calculate_bends(rings: List[Dict[str, Any]], tol_units: float = 0.01) -> int:
    """
    Count direction changes along rings, including at nodes and hubs.
    A 90-degree turn counts once, a reversal counts once, and straight-through movement counts zero.
    """
    total_bends = 0
    for ring in rings:
        legs = ring.get("legs", [])
        if not legs:
            continue

        # Extract sequence of all directed segments along the closed ring
        segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        for leg in legs:
            pts = [(float(p["x"]), float(p["y"])) for p in leg.get("polyline", [])]
            for i in range(len(pts) - 1):
                p1, p2 = pts[i], pts[i + 1]
                # Filter out zero-length segments within tolerance
                if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) > tol_units:
                    segments.append((p1, p2))

        if len(segments) < 2:
            continue

        # Count turns between consecutive segments, including closing back from last to first
        num_segs = len(segments)
        for i in range(num_segs):
            s_prev = segments[i]
            s_next = segments[(i + 1) % num_segs]

            dir_prev = _direction_vector(s_prev[0], s_prev[1], tol=tol_units)
            dir_next = _direction_vector(s_next[0], s_next[1], tol=tol_units)

            if dir_prev == (0, 0) or dir_next == (0, 0):
                continue

            if dir_prev == dir_next:
                # Straight-through movement: 0 bend
                continue
            else:
                # Either 90-degree turn or 180-degree reversal: counts as 1 bend
                total_bends += 1

    return total_bends


def calculate_collinear_overlap_m(
    rings: List[Dict[str, Any]],
    drawing_units_per_metre: float,
    tol_units: float = 0.01
) -> float:
    """
    Calculate shared collinear cable length in metres.
    If k legs cover a stretch, it contributes (k - 1) * length.
    """
    # Collect all horizontal and vertical segments across all legs
    # Horizontal segments: grouped by y (within tol_units)
    # Vertical segments: grouped by x (within tol_units)
    horizontal_lines: Dict[float, List[Tuple[float, float]]] = {}
    vertical_lines: Dict[float, List[Tuple[float, float]]] = {}

    def find_cluster_key(val: float, clusters: Dict[float, Any]) -> float:
        for k in clusters.keys():
            if abs(k - val) <= tol_units:
                return k
        return val

    for ring in rings:
        for leg in ring.get("legs", []):
            pts = [(float(p["x"]), float(p["y"])) for p in leg.get("polyline", [])]
            for i in range(len(pts) - 1):
                p1, p2 = pts[i], pts[i + 1]
                dx = abs(p2[0] - p1[0])
                dy = abs(p2[1] - p1[1])

                if dx <= tol_units and dy <= tol_units:
                    continue  # zero length

                if dy <= tol_units:
                    # Horizontal segment
                    y_val = (p1[1] + p2[1]) / 2.0
                    key = find_cluster_key(y_val, horizontal_lines)
                    x_start, x_end = min(p1[0], p2[0]), max(p1[0], p2[0])
                    horizontal_lines.setdefault(key, []).append((x_start, x_end))
                elif dx <= tol_units:
                    # Vertical segment
                    x_val = (p1[0] + p2[0]) / 2.0
                    key = find_cluster_key(x_val, vertical_lines)
                    y_start, y_end = min(p1[1], p2[1]), max(p1[1], p2[1])
                    vertical_lines.setdefault(key, []).append((y_start, y_end))

    total_overlap_units = 0.0

    def compute_1d_overlap(intervals: List[Tuple[float, float]]) -> float:
        if len(intervals) < 2:
            return 0.0

        # Collect unique endpoints
        raw_pts = set()
        for s, e in intervals:
            raw_pts.add(s)
            raw_pts.add(e)

        sorted_pts = sorted(list(raw_pts))
        # Cluster endpoints within tolerance
        clustered_pts = [sorted_pts[0]]
        for p in sorted_pts[1:]:
            if p - clustered_pts[-1] > tol_units:
                clustered_pts.append(p)

        overlap = 0.0
        for i in range(len(clustered_pts) - 1):
            e_start = clustered_pts[i]
            e_end = clustered_pts[i + 1]
            mid = (e_start + e_end) / 2.0
            length = e_end - e_start

            # Count how many intervals cover this elementary interval
            k = sum(1 for (s, e) in intervals if (s - tol_units) <= mid <= (e + tol_units))
            if k > 1:
                overlap += (k - 1) * length

        return overlap

    for intervals in horizontal_lines.values():
        total_overlap_units += compute_1d_overlap(intervals)

    for intervals in vertical_lines.values():
        total_overlap_units += compute_1d_overlap(intervals)

    return total_overlap_units / drawing_units_per_metre


def calculate_crossings(
    rings: List[Dict[str, Any]],
    nodes: List[Dict[str, Any]],
    hubs: List[Dict[str, Any]],
    tol_units: float = 0.01
) -> int:
    """
    Points where cables meet away from a node or hub, within or between rings.
    One count per geometric point.
    """
    # Set of exempt points (nodes and hubs)
    exempt_points = []
    for n in nodes:
        pt = n.get("point", {})
        exempt_points.append((float(pt["x"]), float(pt["y"])))
    for h in hubs:
        pt = h.get("point", {})
        exempt_points.append((float(pt["x"]), float(pt["y"])))

    def is_exempt(pt: Tuple[float, float]) -> bool:
        for ep in exempt_points:
            if math.hypot(pt[0] - ep[0], pt[1] - ep[1]) <= tol_units:
                return True
        return False

    # Collect all individual line segments with metadata (ring_idx, leg_idx, seg_idx)
    all_segments: List[Tuple[Tuple[int, int, int], Tuple[float, float], Tuple[float, float], LineString]] = []
    for r_idx, ring in enumerate(rings):
        for l_idx, leg in enumerate(ring.get("legs", [])):
            pts = [(float(p["x"]), float(p["y"])) for p in leg.get("polyline", [])]
            for s_idx in range(len(pts) - 1):
                p1, p2 = pts[s_idx], pts[s_idx + 1]
                if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) > tol_units:
                    ls = LineString([p1, p2])
                    all_segments.append(((r_idx, l_idx, s_idx), p1, p2, ls))

    crossing_points: List[Tuple[float, float]] = []

    # Check pair intersections
    num_segs = len(all_segments)
    for i in range(num_segs):
        id_a, p1_a, p2_a, ls_a = all_segments[i]
        is_a_horiz = abs(p2_a[1] - p1_a[1]) <= tol_units
        is_a_vert = abs(p2_a[0] - p1_a[0]) <= tol_units

        for j in range(i + 1, num_segs):
            id_b, p1_b, p2_b, ls_b = all_segments[j]
            is_b_horiz = abs(p2_b[1] - p1_b[1]) <= tol_units
            is_b_vert = abs(p2_b[0] - p1_b[0]) <= tol_units

            # Parallel/collinear segments cannot cross
            if (is_a_horiz and is_b_horiz) or (is_a_vert and is_b_vert):
                continue

            # Check if segments intersect
            if not ls_a.intersects(ls_b):
                continue

            inter = ls_a.intersection(ls_b)
            # If intersection is a LineString, it's collinear overlap, not a crossing point
            if inter.geom_type in ("LineString", "MultiLineString"):
                continue

            # If intersection is a Point
            points_to_check = []
            if inter.geom_type == "Point":
                points_to_check.append((inter.x, inter.y))
            elif inter.geom_type == "MultiPoint":
                for geom in inter.geoms:
                    points_to_check.append((geom.x, geom.y))

            for pt in points_to_check:
                # Exclude if point is exempt (node or hub)
                if is_exempt(pt):
                    continue

                # Exclude shared vertex between consecutive segments in the same leg
                if id_a[0] == id_b[0] and id_a[1] == id_b[1] and abs(id_a[2] - id_b[2]) == 1:
                    if math.hypot(pt[0] - p2_a[0], pt[1] - p2_a[1]) <= tol_units:
                        continue
                    if math.hypot(pt[0] - p1_a[0], pt[1] - p1_a[1]) <= tol_units:
                        continue

                # Add crossing point
                crossing_points.append(pt)

    # Cluster crossing points within tolerance to count unique geometric points
    unique_crossings: List[Tuple[float, float]] = []
    for cp in crossing_points:
        matched = False
        for uc in unique_crossings:
            if math.hypot(cp[0] - uc[0], cp[1] - uc[1]) <= tol_units:
                matched = True
                break
        if not matched:
            unique_crossings.append(cp)

    return len(unique_crossings)


def calculate_area_gap_m2(
    hubs: List[Dict[str, Any]],
    assignments: List[Dict[str, Any]],
    rooms: List[Dict[str, Any]]
) -> float:
    """Calculate assigned-area gap between hubs: max - min assigned area."""
    if len(hubs) <= 1:
        return 0.0

    room_areas = {r["id"]: float(r.get("area_m2", 0.0)) for r in rooms}
    hub_areas: Dict[str, float] = {h["id"]: 0.0 for h in hubs}

    for a in assignments:
        h_id = a.get("hub_id")
        r_id = a.get("room_id")
        if h_id in hub_areas and r_id in room_areas:
            hub_areas[h_id] += room_areas[r_id]

    areas = list(hub_areas.values())
    if not areas:
        return 0.0
    return max(areas) - min(areas)


def calculate_all_metrics(
    plan: Dict[str, Any],
    solution: Dict[str, Any],
    tol_m: float = 0.001
) -> RecomputedMetrics:
    """Calculate all metrics independently from plan and solution geometry."""
    scale = float(plan.get("drawing_units_per_metre", 1.0))
    tol_units = tol_m * scale

    rings = solution.get("rings", [])
    hubs = solution.get("hubs", [])
    assignments = solution.get("assignments", [])
    nodes = plan.get("nodes", [])
    rooms = plan.get("rooms", [])

    hub_count = len(hubs)
    length_m = calculate_length_m(rings, scale)
    crossings = calculate_crossings(rings, nodes, hubs, tol_units=tol_units)
    overlap_m = calculate_collinear_overlap_m(rings, scale, tol_units=tol_units)
    bends = calculate_bends(rings, tol_units=tol_units)
    route_cost = length_m + 5.0 * crossings + overlap_m + 0.5 * bends
    area_gap = calculate_area_gap_m2(hubs, assignments, rooms)

    return RecomputedMetrics(
        hub_count=hub_count,
        length_m=length_m,
        crossings=crossings,
        overlap_m=overlap_m,
        bends=bends,
        route_cost=route_cost,
        area_gap_m2=area_gap,
    )
