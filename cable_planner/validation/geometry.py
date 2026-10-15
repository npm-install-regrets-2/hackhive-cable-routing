"""Geometric validation primitives using Shapely and 1 mm tolerance."""

from typing import Dict, List, Optional, Tuple, Any
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
from shapely.ops import unary_union


def parse_point(pt_dict: Dict[str, float]) -> Tuple[float, float]:
    """Parse point dictionary to (x, y) tuple."""
    return (float(pt_dict["x"]), float(pt_dict["y"]))


def parse_polygon(poly_dict: Dict[str, Any]) -> Polygon:
    """Parse schema polygon dictionary to Shapely Polygon."""
    exterior = [parse_point(p) for p in poly_dict["exterior"]]
    holes = [[parse_point(p) for p in hole] for hole in poly_dict.get("holes", [])]
    return Polygon(shell=exterior, holes=holes)


def parse_polyline(pts_list: List[Dict[str, float]]) -> LineString:
    """Parse schema polyline array to Shapely LineString."""
    pts = [parse_point(p) for p in pts_list]
    return LineString(pts)


def is_axis_aligned_segment(p1: Tuple[float, float], p2: Tuple[float, float], tol_units: float) -> bool:
    """Check if segment between p1 and p2 is horizontal or vertical within tolerance."""
    dx = abs(p2[0] - p1[0])
    dy = abs(p2[1] - p1[1])
    # Either dx is effectively 0 (vertical) or dy is effectively 0 (horizontal)
    return dx <= tol_units or dy <= tol_units


def check_polyline_axis_aligned(polyline: List[Dict[str, float]], tol_units: float) -> List[str]:
    """Verify that every segment in polyline is axis-aligned. Returns list of error descriptions."""
    errors = []
    pts = [parse_point(p) for p in polyline]
    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i + 1]
        if not is_axis_aligned_segment(p1, p2, tol_units):
            errors.append(
                f"Segment {i} from ({p1[0]:.2f}, {p1[1]:.2f}) to ({p2[0]:.2f}, {p2[1]:.2f}) "
                f"is not axis-aligned (dx={abs(p2[0]-p1[0]):.4f}, dy={abs(p2[1]-p1[1]):.4f}, tol={tol_units:.4f})"
            )
    return errors


def check_node_clearance(
    node_point: Tuple[float, float],
    room_polygon: Polygon,
    min_clearance_units: float,
    tol_units: float
) -> Tuple[bool, float]:
    """Check if node is inside room and meets minimum clearance from boundary."""
    pt = Point(node_point)
    # Check containment
    if not room_polygon.buffer(tol_units).covers(pt):
        return False, 0.0

    # Distance to boundary (walls)
    dist_to_wall = room_polygon.boundary.distance(pt)
    is_valid = (dist_to_wall + tol_units) >= min_clearance_units
    return is_valid, dist_to_wall


def check_internal_containment(polyline_ls: LineString, internal_boundary: Polygon, tol_units: float) -> bool:
    """Verify that polyline stays within the internal boundary within tolerance."""
    buffered = internal_boundary.buffer(tol_units)
    return buffered.covers(polyline_ls)


def check_obstacle_collision(
    polyline_ls: LineString,
    obstacle_geoms: List[Tuple[str, str, Any]],  # (id, kind, shapely_geom)
    tol_units: float
) -> List[Tuple[str, str, str]]:
    """
    Check if polyline collides with obstacle geometries (walls, windows, external areas).
    Returns list of (obstacle_id, kind, error_message).
    """
    collisions = []
    for obs_id, obs_kind, obs_geom in obstacle_geoms:
        # If obstacle is a LineString (e.g. wall or window)
        if isinstance(obs_geom, LineString):
            # Check intersection
            if polyline_ls.crosses(obs_geom):
                collisions.append((obs_id, obs_kind, f"Cable crosses {obs_kind} obstacle '{obs_id}'"))
            elif polyline_ls.overlaps(obs_geom):
                collisions.append((obs_id, obs_kind, f"Cable overlaps {obs_kind} obstacle '{obs_id}'"))
        # If obstacle is a Polygon (e.g. thick wall or external area)
        elif isinstance(obs_geom, Polygon):
            intersection = polyline_ls.intersection(obs_geom)
            if not intersection.is_empty and intersection.length > tol_units:
                collisions.append((obs_id, obs_kind, f"Cable enters {obs_kind} polygon '{obs_id}'"))
    return collisions


def points_are_close(p1: Tuple[float, float], p2: Tuple[float, float], tol_units: float) -> bool:
    """Check if two points are identical within drawing unit tolerance."""
    return abs(p1[0] - p2[0]) <= tol_units and abs(p1[1] - p2[1]) <= tol_units
