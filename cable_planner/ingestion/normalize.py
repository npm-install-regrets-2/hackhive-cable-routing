"""Convert one trusted ResPlan item to the development Plan interchange shape.

Input geometry is in drawing units. Diagnostics live beside the Plan because
the current shared schema has no preprocessing-diagnostics field.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import pickle
import re
from typing import Any, Mapping

from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon
from shapely.ops import polylabel
from shapely.validation import make_valid


ELIGIBLE = ("living", "bedroom", "kitchen", "storage")
EXCLUDED = ("bathroom", "balcony", "stair", "garden", "pool", "parking", "land")
KINDS = (*ELIGIBLE, *EXCLUDED)


@dataclass(frozen=True)
class Rules:
    max_area_m2_per_hub: float = 100.0
    max_nodes_per_hub: int = 5
    node_wall_clearance_m: float = 0.5
    geometry_tolerance_m: float = 0.001
    max_repair_area_change_fraction: float = 0.01
    portal_contact_m: float = 0.01

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) and v > 0 for v in (
            self.max_area_m2_per_hub, self.geometry_tolerance_m,
            self.portal_contact_m, self.max_repair_area_change_fraction,
        )) or not math.isfinite(self.node_wall_clearance_m) or self.node_wall_clearance_m < 0:
            raise ValueError("rules require finite positive capacities/tolerances and nonnegative clearance")
        if isinstance(self.max_nodes_per_hub, bool) or not isinstance(self.max_nodes_per_hub, int) or self.max_nodes_per_hub < 1:
            raise ValueError("max_nodes_per_hub must be a positive integer")


@dataclass(frozen=True)
class NormalizationResult:
    plan: dict[str, Any] | None
    diagnostics: tuple[dict[str, Any], ...]

    @property
    def ok(self) -> bool:
        return self.plan is not None


def load_trusted_plan(path: str | Path, plan_id: int) -> Mapping[str, Any]:
    """Load a selected item from the locally trusted archive only.

    Pickle can execute code. Never pass user uploads or unverified downloads.
    """
    with Path(path).open("rb") as stream:
        plans = pickle.load(stream)
    if not isinstance(plans, list):
        raise ValueError("ResPlan archive root must be a list")
    for item in plans:
        if isinstance(item, dict) and item.get("id") == plan_id:
            return item
    raise KeyError(f"plan id {plan_id} not found")


def _diagnostic(code: str, message: str, *ids: str) -> dict[str, Any]:
    return {"code": code, "message": message, "entity_ids": list(ids)}


def _safe_id(value: Any) -> str:
    result = re.sub(r"[^A-Za-z0-9._:-]", "-", str(value))
    return result if result and result[0].isalnum() else "plan-" + result


def _point(x: float, y: float) -> dict[str, float]:
    return {"x": float(x), "y": float(y)}


def _polygon(poly: Polygon) -> dict[str, Any]:
    return {
        "exterior": [_point(x, y) for x, y in poly.exterior.coords],
        "holes": [[_point(x, y) for x, y in ring.coords] for ring in poly.interiors],
    }


def _parts(value: Any) -> list[Polygon]:
    if value is None or getattr(value, "is_empty", False):
        return []
    if isinstance(value, Polygon):
        return [value]
    if isinstance(value, (MultiPolygon, GeometryCollection)):
        parts: list[Polygon] = []
        for geom in value.geoms:
            parts.extend(_parts(geom))
        return parts
    raise TypeError(f"expected polygon geometry, got {getattr(value, 'geom_type', type(value).__name__)}")


def _line_parts(value: Any) -> list[LineString]:
    if value is None or getattr(value, "is_empty", False):
        return []
    if isinstance(value, LineString):
        return [value]
    if getattr(value, "geom_type", "") in ("MultiLineString", "GeometryCollection"):
        return [piece for part in value.geoms for piece in _line_parts(part)]
    if getattr(value, "geom_type", "") in ("Point", "MultiPoint"):
        return []
    raise TypeError(f"expected line geometry, got {getattr(value, 'geom_type', type(value).__name__)}")


def normalize_plan(
    raw: Mapping[str, Any], *, rules: Rules = Rules(),
    fixed_nodes: Mapping[str, tuple[float, float]] | None = None,
    clip_outside_rooms: bool = False,
) -> NormalizationResult:
    """Normalize a ResPlan dict; fixed_nodes is keyed by stable room ID.

    An invalid or unusable item returns no Plan and explicit diagnostics.
    """
    diagnostics: list[dict[str, Any]] = []
    if not isinstance(raw, Mapping):
        return NormalizationResult(None, (_diagnostic("invalid_input", "plan must be a mapping"),))
    plan_id = _safe_id(raw.get("id", "missing"))
    try:
        area_m2 = float(raw["area"])
        inner_raw = raw["inner"]
        inner_area = float(inner_raw.area)
        if not all(math.isfinite(v) and v > 0 for v in (area_m2, inner_area)):
            raise ValueError("area and inner.area must be finite and positive")
        scale = math.sqrt(inner_area / area_m2)
    except (KeyError, AttributeError, TypeError, ValueError, OverflowError) as exc:
        return NormalizationResult(None, (_diagnostic("invalid_scale", str(exc), plan_id),))

    def polygons(value: Any, label: str) -> list[Polygon]:
        try:
            found = _parts(value)
            output: list[Polygon] = []
            for index, piece in enumerate(found):
                before = piece.area
                if not piece.is_valid:
                    repaired = make_valid(piece)
                    after_parts = _parts(repaired)
                    after = sum(part.area for part in after_parts)
                    if before <= 0 or not after_parts or abs(after - before) / before > rules.max_repair_area_change_fraction:
                        diagnostics.append(_diagnostic("unusable_geometry", f"{label} component {index} cannot be repaired within area tolerance", label))
                        continue
                    diagnostics.append(_diagnostic("geometry_repaired", f"{label} component {index} repaired; area change {(after-before)/before:.6g}", label))
                    output.extend(after_parts)
                else:
                    output.append(piece)
            for piece in output:
                if piece.is_empty or not piece.is_valid or piece.area <= 0:
                    diagnostics.append(_diagnostic("unusable_geometry", f"{label} has empty or invalid polygon", label))
            return output
        except (TypeError, ValueError) as exc:
            diagnostics.append(_diagnostic("unusable_geometry", f"{label}: {exc}", label))
            return []

    boundary_parts = polygons(inner_raw, "inner")
    if len(boundary_parts) != 1:
        diagnostics.append(_diagnostic("unsupported_boundary", "internal boundary must be one usable polygon", plan_id))
    rooms: list[dict[str, Any]] = []
    room_geoms: dict[str, Polygon] = {}
    for kind in KINDS:
        if kind == "land":
            continue  # Land overlays the building in ResPlan; it is not an interior room.
        for index, poly in enumerate(polygons(raw.get(kind), kind)):
            room_id = f"room:{kind}:{index:03d}"
            rooms.append({"id": room_id, "source_label": f"{kind}_{index}", "kind": kind,
                          "eligible": kind in ELIGIBLE, "geometry": _polygon(poly),
                          "area_m2": poly.area / scale**2})
            room_geoms[room_id] = poly
    if not any(room["eligible"] for room in rooms):
        diagnostics.append(_diagnostic("no_eligible_rooms", "plan has no eligible room polygons", plan_id))

    obstacles: list[dict[str, Any]] = []
    blocked = []
    for source, kind in (("wall", "wall"), ("window", "window")):
        for index, poly in enumerate(polygons(raw.get(source), source)):
            obstacles.append({"id": f"obstacle:{kind}:{index:03d}", "kind": kind, "geometry": _polygon(poly)})
            blocked.append(poly)
    tolerance = scale * rules.geometry_tolerance_m
    if boundary_parts:
        boundary = boundary_parts[0]
        for room in rooms:
            poly = room_geoms[room["id"]]
            if room["kind"] not in ("balcony", "garden", "pool", "parking") and not boundary.buffer(tolerance).covers(poly):
                outside_m2 = poly.difference(boundary if clip_outside_rooms else boundary.buffer(tolerance)).area / scale**2
                if clip_outside_rooms:
                    clipped_parts = _parts(poly.intersection(boundary))
                    if len(clipped_parts) != 1 or not clipped_parts[0].is_valid or clipped_parts[0].area <= 0:
                        diagnostics.append(_diagnostic(
                            "room_clip_unsupported",
                            f"clipping would remove or split the room ({outside_m2:.6g} m2 outside)",
                            room["id"],
                        ))
                    else:
                        poly = clipped_parts[0]
                        room_geoms[room["id"]] = poly
                        room["geometry"] = _polygon(poly)
                        room["area_m2"] = poly.area / scale**2
                        diagnostics.append(_diagnostic(
                            "room_clipped_to_boundary",
                            f"explicit clipping removed {outside_m2:.6g} m2 outside; clipped area is {room['area_m2']:.6g} m2",
                            room["id"],
                        ))
                else:
                    diagnostics.append(_diagnostic("room_outside_boundary",
                                                   f"room extends beyond internal boundary ({outside_m2:.6g} m2 outside)",
                                                   room["id"]))
            if room["eligible"] and room["area_m2"] > rules.max_area_m2_per_hub + rules.geometry_tolerance_m:
                diagnostics.append(_diagnostic("room_over_capacity", "single eligible room exceeds hub area capacity", room["id"]))
    else:
        boundary = None

    nodes: list[dict[str, Any]] = []
    supplied = fixed_nodes or {}
    eligible_ids = {room["id"] for room in rooms if room["eligible"]}
    for unknown in sorted(set(supplied) - eligible_ids):
        diagnostics.append(_diagnostic("unknown_fixed_node_room", "fixed node references no eligible room", unknown))
    clearance = scale * rules.node_wall_clearance_m
    for room in rooms:
        if not room["eligible"]:
            continue
        room_id = room["id"]
        poly = room_geoms[room_id]
        if room_id in supplied:
            try:
                x, y = map(float, supplied[room_id])
                if not all(math.isfinite(v) for v in (x, y)):
                    raise ValueError("coordinates must be finite")
                point = Point(x, y)
            except (TypeError, ValueError) as exc:
                diagnostics.append(_diagnostic("invalid_fixed_node", str(exc), room_id))
                continue
            source = "organizer"
        else:
            point = polylabel(poly, tolerance=max(scale * 0.01, 1e-6))
            source = "development_fallback"

        def has_clearance(candidate: Point) -> bool:
            return (poly.contains(candidate)
                    and poly.boundary.distance(candidate) + tolerance >= clearance
                    and all(obstacle.distance(candidate) + tolerance >= clearance for obstacle in blocked))

        if source == "development_fallback" and not has_clearance(point):
            # The room's pole of inaccessibility can be close to an interior
            # wall. Search the inset room after subtracting wall/window buffers.
            minimum = max(clearance - tolerance, 0.0)
            usable = poly.buffer(-minimum)
            for obstacle in blocked:
                if usable.is_empty:
                    break
                usable = usable.difference(obstacle.buffer(minimum))
            for part in sorted(_parts(usable), key=lambda part: (-part.area, part.bounds)):
                candidate = polylabel(part, tolerance=max(scale * 0.01, 1e-6))
                if has_clearance(candidate):
                    point = candidate
                    break

        if not has_clearance(point):
            message = (f"no fallback point meets {rules.node_wall_clearance_m:g} m wall clearance; "
                       f"approximate maximum room-boundary clearance is {poly.boundary.distance(point) / scale:.3g} m"
                       if source == "development_fallback" else "node is outside room or lacks wall clearance")
            diagnostics.append(_diagnostic("invalid_fixed_node", message, room_id))
            continue
        nodes.append({"id": f"node:{room_id.removeprefix('room:')}", "room_id": room_id,
                      "point": _point(point.x, point.y), "source": source})

    for left_index, left in enumerate(nodes):
        for right in nodes[left_index + 1:]:
            if Point(left["point"]["x"], left["point"]["y"]).distance(
                Point(right["point"]["x"], right["point"]["y"])
            ) <= tolerance:
                diagnostics.append(_diagnostic("duplicate_fixed_nodes", "distinct rooms have coincident nodes",
                                               left["id"], right["id"]))

    portals: list[dict[str, Any]] = []
    # Door polygons are evidence; a geometric contact with two room interiors
    # is required. Generic ResPlan graph adjacency is deliberately ignored.
    for index, door in enumerate(polygons(raw.get("door"), "door")):
        contacts = [rid for rid, poly in room_geoms.items()
                    if door.buffer(tolerance if boundary else 0).intersection(poly).area > (scale * rules.portal_contact_m)**2]
        if len(contacts) != 2:
            diagnostics.append(_diagnostic("unresolved_door", f"door {index} contacts {len(contacts)} room spaces; no portal emitted", f"door:{index:03d}"))
            continue
        a, b = sorted(contacts)
        shared = room_geoms[a].boundary.intersection(room_geoms[b].boundary).intersection(door.buffer(tolerance))
        lines = _line_parts(shared)
        if lines:
            segment = max(lines, key=lambda line: line.length)
        else:
            # Real ResPlan rooms are often separated by wall thickness. The
            # door polygon itself bridges the two room interiors.
            x0, y0, x1, y1 = door.bounds
            segment = (LineString([(x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)])
                       if x1 - x0 >= y1 - y0 else
                       LineString([((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)]))
        if segment.length <= scale * rules.portal_contact_m:
            diagnostics.append(_diagnostic("unresolved_door", f"door {index} contact too short", f"door:{index:03d}"))
            continue
        portals.append({"id": f"portal:door:{index:03d}", "space_a_id": a, "space_b_id": b,
                        "kind": "door", "segment": [_point(*segment.coords[0]), _point(*segment.coords[-1])]})

    # Shared boundaries are open only if no wall or window covers the segment.
    # A conservative rule avoids treating a generic graph adjacency as a door.
    room_ids = sorted(room_geoms)
    for pos, a in enumerate(room_ids):
        for b in room_ids[pos + 1:]:
            if any({portal["space_a_id"], portal["space_b_id"]} == {a, b} for portal in portals):
                continue
            shared = room_geoms[a].boundary.intersection(room_geoms[b].boundary)
            for line in _line_parts(shared):
                if line.length <= scale * rules.portal_contact_m:
                    continue
                free = line.difference(GeometryCollection(blocked).buffer(tolerance) if blocked else GeometryCollection())
                for free_line in _line_parts(free):
                    if free_line.length > scale * rules.portal_contact_m:
                        portals.append({"id": f"portal:opening:{len(portals):03d}", "space_a_id": a,
                                        "space_b_id": b, "kind": "open_passage",
                                        "segment": [_point(*free_line.coords[0]), _point(*free_line.coords[-1])]})

    # Consumers can derive a traversability graph directly from these verified
    # portal endpoints. Disconnected eligible rooms are a warning, not a repair.
    connected = {rid: set() for rid in room_ids}
    for portal in portals:
        a, b = portal["space_a_id"], portal["space_b_id"]
        connected[a].add(b)
        connected[b].add(a)
    if eligible_ids:
        seen = set()
        stack = [min(eligible_ids)]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(connected[current] - seen)
        unreachable = sorted(eligible_ids - seen)
        if unreachable:
            diagnostics.append(_diagnostic("disconnected_eligible_rooms", "eligible rooms lack verified portal connectivity", *unreachable))

    fatal = {"invalid_scale", "unusable_geometry", "unsupported_boundary", "no_eligible_rooms",
             "room_outside_boundary", "room_clip_unsupported", "room_over_capacity", "invalid_fixed_node", "unknown_fixed_node_room",
             "duplicate_fixed_nodes"}
    if any(item["code"] in fatal for item in diagnostics):
        return NormalizationResult(None, tuple(diagnostics))
    plan = {"id": plan_id, "drawing_units_per_metre": scale, "internal_boundary": _polygon(boundary),
            "rooms": rooms, "nodes": nodes, "portals": portals, "obstacles": obstacles,
            "rules": {"max_area_m2_per_hub": rules.max_area_m2_per_hub,
                      "max_nodes_per_hub": rules.max_nodes_per_hub,
                      "node_wall_clearance_m": rules.node_wall_clearance_m,
                      "geometry_tolerance": rules.geometry_tolerance_m}}
    return NormalizationResult(plan, tuple(diagnostics))

