"""Deterministic exhaustive solver for small normalized development fixtures.

This slice deliberately favors proof and explicit failure over scale. It searches
all connected assignments at each hub count, then all node orders per territory.
The search is suitable for small fixtures while the production CP-SAT and grid
pathfinding implementations are developed.
"""

from __future__ import annotations

from collections import deque
from itertools import combinations, permutations, product
from math import ceil
from typing import Any, Iterable

Point = tuple[float, float]


def hub_count_lower_bound(plan: dict[str, Any]) -> int:
    """Return the simultaneous area/node capacity lower bound."""
    rooms = [room for room in plan["rooms"] if room["eligible"]]
    node_count = len(plan["nodes"])
    if not rooms:
        return 0
    rules = plan["rules"]
    return max(
        ceil(sum(room["area_m2"] for room in rooms) / rules["max_area_m2_per_hub"]),
        ceil(node_count / rules["max_nodes_per_hub"]),
    )


def solve(plan: dict[str, Any]) -> dict[str, Any]:
    """Produce a schema-shaped Solution or an explicit infeasible result.

    Hub candidates are deterministic bounding-box centers of eligible rooms.
    Routing currently accepts obstacle-free normalized plans and uses verified
    portals only. Unsupported or malformed inputs are rejected, never repaired.
    """
    lower_bound = hub_count_lower_bound(plan)
    failure = _validate_thin_slice_input(plan, lower_bound)
    if failure:
        return _infeasible(plan["id"], lower_bound, *failure)
    if lower_bound == 0:
        return {
            "plan_id": plan["id"],
            "status": "feasible",
            "lower_bound_hubs": 0,
            "hubs": [],
            "assignments": [],
            "rings": [],
            "metrics": _metrics([], {}, plan),
            "diagnostics": [{"code": "EMPTY_PLAN", "message": "Plan has no eligible rooms or nodes."}],
        }

    rooms = sorted((r for r in plan["rooms"] if r["eligible"]), key=lambda r: r["id"])
    room_by_id = {room["id"]: room for room in rooms}
    node_by_room = {node["room_id"]: node for node in plan["nodes"]}
    graph, portal_by_edge = _portal_graph(plan, room_by_id)
    try:
        candidates = [
            {"room_id": room["id"], "point": _candidate_point(room)}
            for room in rooms
        ]
    except ValueError as error:
        return _infeasible(
            plan["id"], lower_bound, "NO_LEGAL_HUB_CANDIDATE", str(error)
        )

    for hub_count in range(lower_bound, len(rooms) + 1):
        for selected, owner_indexes in _feasible_assignments(
            rooms, candidates, graph, hub_count, plan["rules"]
        ):
            hubs = [
                {
                    "id": f"hub:{index + 1}",
                    "point": _point_object(candidate["point"]),
                    "room_id": candidate["room_id"],
                }
                for index, candidate in enumerate(selected)
            ]
            assignments = [
                {
                    "room_id": room["id"],
                    "node_id": node_by_room[room["id"]]["id"],
                    "hub_id": hubs[owner_indexes[index]]["id"],
                }
                for index, room in enumerate(rooms)
            ]
            rings: list[dict[str, Any]] = []
            for hub_index, hub in enumerate(hubs):
                owned_rooms = [
                    room for index, room in enumerate(rooms) if owner_indexes[index] == hub_index
                ]
                ring = _best_ring(
                    hub,
                    owned_rooms,
                    node_by_room,
                    graph,
                    portal_by_edge,
                    room_by_id,
                )
                if ring is None:
                    break
                rings.append(ring)
            else:
                lower_bound_met = hub_count == lower_bound
                return {
                    "plan_id": plan["id"],
                    "status": "feasible" if lower_bound_met else "best_known",
                    "lower_bound_hubs": lower_bound,
                    "hubs": hubs,
                    "assignments": assignments,
                    "rings": rings,
                    "metrics": _metrics(rings, owner_indexes, plan, rooms),
                    "diagnostics": [
                        {
                            "code": "OPTIMAL_HUB_COUNT_PROVEN" if lower_bound_met else "HUB_COUNT_ABOVE_LOWER_BOUND",
                            "message": (
                                f"The solution uses {hub_count} hub(s); the arithmetic lower bound is {lower_bound}. "
                                + (
                                    "Meeting the lower bound proves the hub count optimal. "
                                    if lower_bound_met
                                    else "The finite development candidate set does not prove global hub-count optimality. "
                                )
                                + "Advisory metrics must be independently recomputed."
                            ),
                        }
                    ],
                }

    return _infeasible(
        plan["id"],
        lower_bound,
        "NO_FEASIBLE_CONNECTED_RING_SOLUTION",
        "Exhaustive small-instance search found no capacity-compliant connected assignment with legal portal paths.",
    )


def _validate_thin_slice_input(
    plan: dict[str, Any], lower_bound: int
) -> tuple[str, str] | None:
    eligible = {room["id"]: room for room in plan["rooms"] if room["eligible"]}
    nodes_by_room: dict[str, int] = {}
    for node in plan["nodes"]:
        nodes_by_room[node["room_id"]] = nodes_by_room.get(node["room_id"], 0) + 1
    missing_or_duplicate = sorted(
        room_id for room_id in eligible if nodes_by_room.get(room_id) != 1
    )
    extra = sorted(room_id for room_id in nodes_by_room if room_id not in eligible)
    if missing_or_duplicate or extra:
        return (
            "INVALID_NODE_ROOM_MAPPING",
            "Every eligible room must have exactly one node and excluded rooms must have none.",
        )
    if plan["obstacles"]:
        return (
            "UNSUPPORTED_OBSTACLES",
            "The thin-slice pathfinder only accepts obstacle-free normalized fixtures; obstacle-aware routing is the next integration step.",
        )
    area_limit = plan["rules"]["max_area_m2_per_hub"]
    oversized = sorted(room_id for room_id, room in eligible.items() if room["area_m2"] > area_limit)
    if oversized:
        return (
            "ROOM_EXCEEDS_HUB_AREA_CAPACITY",
            f"Eligible room(s) exceed the configured {area_limit:g} m2 hub limit: {', '.join(oversized)}.",
        )
    if lower_bound > len(eligible):
        return (
            "CAPACITY_LOWER_BOUND_EXCEEDS_ROOM_COUNT",
            "No non-empty territory can be created for every required hub.",
        )
    return None


def _feasible_assignments(
    rooms: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    graph: dict[str, set[str]],
    hub_count: int,
    rules: dict[str, Any],
) -> Iterable[tuple[tuple[dict[str, Any], ...], tuple[int, ...]]]:
    for selected in combinations(candidates, hub_count):
        seed_rooms = [candidate["room_id"] for candidate in selected]
        if len(set(seed_rooms)) != hub_count:
            continue
        for owners in product(range(hub_count), repeat=len(rooms)):
            if any(owners[index] != seed_rooms.index(room["id"]) for index, room in enumerate(rooms) if room["id"] in seed_rooms):
                continue
            if any(owner not in owners for owner in range(hub_count)):
                continue
            if not _capacities_hold(rooms, owners, hub_count, rules):
                continue
            if not all(
                _connected(
                    {room["id"] for index, room in enumerate(rooms) if owners[index] == owner},
                    graph,
                )
                for owner in range(hub_count)
            ):
                continue
            yield selected, owners


def _capacities_hold(
    rooms: list[dict[str, Any]], owners: tuple[int, ...], hub_count: int, rules: dict[str, Any]
) -> bool:
    for owner in range(hub_count):
        owned = [room for index, room in enumerate(rooms) if owners[index] == owner]
        if len(owned) > rules["max_nodes_per_hub"]:
            return False
        if sum(room["area_m2"] for room in owned) > rules["max_area_m2_per_hub"]:
            return False
    return True


def _connected(room_ids: set[str], graph: dict[str, set[str]]) -> bool:
    if not room_ids:
        return False
    seen = set()
    queue = deque([min(room_ids)])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(sorted((graph.get(current, set()) & room_ids) - seen))
    return seen == room_ids


def _portal_graph(
    plan: dict[str, Any], room_by_id: dict[str, dict[str, Any]]
) -> tuple[dict[str, set[str]], dict[frozenset[str], list[dict[str, Any]]]]:
    graph = {room_id: set() for room_id in room_by_id}
    portal_by_edge: dict[frozenset[str], list[dict[str, Any]]] = {}
    for portal in sorted(plan["portals"], key=lambda item: item["id"]):
        a, b = portal["space_a_id"], portal["space_b_id"]
        if a not in room_by_id or b not in room_by_id:
            continue
        graph[a].add(b)
        graph[b].add(a)
        portal_by_edge.setdefault(frozenset((a, b)), []).append(portal)
    return graph, portal_by_edge


def _best_ring(
    hub: dict[str, Any],
    rooms: list[dict[str, Any]],
    node_by_room: dict[str, dict[str, Any]],
    graph: dict[str, set[str]],
    portal_by_edge: dict[frozenset[str], list[dict[str, Any]]],
    room_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    stops = [
        (node_by_room[room["id"]]["id"], room["id"], _tuple_point(node_by_room[room["id"]]["point"]))
        for room in sorted(rooms, key=lambda item: item["id"])
    ]
    hub_stop = (hub["id"], hub["room_id"], _tuple_point(hub["point"]))
    best: tuple[float, tuple[str, ...], list[dict[str, Any]]] | None = None
    for ordered in permutations(stops):
        sequence = (hub_stop, *ordered, hub_stop)
        legs: list[dict[str, Any]] = []
        for start, end in zip(sequence, sequence[1:]):
            polyline = _legal_path(start[1:], end[1:], graph, portal_by_edge, room_by_id)
            if polyline is None:
                break
            legs.append({"from_id": start[0], "to_id": end[0], "polyline": [_point_object(p) for p in polyline]})
        else:
            length = sum(_polyline_length([_tuple_point(p) for p in leg["polyline"]]) for leg in legs)
            ids = tuple(stop[0] for stop in sequence)
            candidate = (length, ids, legs)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
    if best is None:
        return None
    return {"hub_id": hub["id"], "stop_ids": list(best[1]), "legs": best[2]}


def _legal_path(
    start: tuple[str, Point],
    end: tuple[str, Point],
    graph: dict[str, set[str]],
    portal_by_edge: dict[frozenset[str], list[dict[str, Any]]],
    room_by_id: dict[str, dict[str, Any]],
) -> list[Point] | None:
    room_path = _shortest_room_path(start[0], end[0], graph)
    if room_path is None:
        return None
    waypoints: list[tuple[str, Point]] = [(start[0], start[1])]
    for a, b in zip(room_path, room_path[1:]):
        portal = portal_by_edge[frozenset((a, b))][0]
        points = [_tuple_point(point) for point in portal["segment"]]
        midpoint = ((points[0][0] + points[-1][0]) / 2, (points[0][1] + points[-1][1]) / 2)
        waypoints.append((a, midpoint))
        waypoints.append((b, midpoint))
    waypoints.append((end[0], end[1]))
    result: list[Point] = []
    for (room_id, a), (next_room_id, b) in zip(waypoints, waypoints[1:]):
        if room_id != next_room_id:
            segment = [a, b]
        else:
            segment = _orthogonal_in_polygon(a, b, room_by_id[room_id]["geometry"])
            if segment is None:
                return None
        result.extend(segment if not result else segment[1:])
    return _remove_duplicate_and_collinear(result)


def _shortest_room_path(start: str, end: str, graph: dict[str, set[str]]) -> list[str] | None:
    queue = deque([[start]])
    seen = {start}
    while queue:
        path = queue.popleft()
        if path[-1] == end:
            return path
        for neighbor in sorted(graph.get(path[-1], set())):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append([*path, neighbor])
    return None


def _orthogonal_in_polygon(a: Point, b: Point, polygon: dict[str, Any]) -> list[Point] | None:
    if a == b:
        return [a, b]
    alternatives = ([a, b],) if a[0] == b[0] or a[1] == b[1] else ([a, (b[0], a[1]), b], [a, (a[0], b[1]), b])
    for candidate in alternatives:
        if all(_segment_inside_polygon(x, y, polygon) for x, y in zip(candidate, candidate[1:])):
            return list(candidate)
    return None


def _segment_inside_polygon(a: Point, b: Point, polygon: dict[str, Any]) -> bool:
    # Sampling is intentionally conservative fixture-level validation, not the future
    # authoritative geometry kernel supplied by the ingestion module.
    return all(
        _point_in_polygon((a[0] + (b[0] - a[0]) * step / 20, a[1] + (b[1] - a[1]) * step / 20), polygon)
        for step in range(21)
    )


def _point_in_polygon(point: Point, polygon: dict[str, Any]) -> bool:
    exterior = [_tuple_point(p) for p in polygon["exterior"]]
    if _point_on_ring(point, exterior):
        inside = True
    else:
        inside = _ray_cast(point, exterior)
    if not inside:
        return False
    return not any(_ray_cast(point, [_tuple_point(p) for p in hole]) or _point_on_ring(point, [_tuple_point(p) for p in hole]) for hole in polygon.get("holes", []))


def _ray_cast(point: Point, ring: list[Point]) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
    return inside


def _point_on_ring(point: Point, ring: list[Point], tolerance: float = 1e-9) -> bool:
    x, y = point
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) <= tolerance and min(x1, x2) - tolerance <= x <= max(x1, x2) + tolerance and min(y1, y2) - tolerance <= y <= max(y1, y2) + tolerance:
            return True
    return False


def _candidate_point(room: dict[str, Any]) -> Point:
    exterior = [_tuple_point(point) for point in room["geometry"]["exterior"][:-1]]
    xs, ys = zip(*exterior)
    candidate = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    if not _point_in_polygon(candidate, room["geometry"]):
        raise ValueError(f"No thin-slice hub candidate for non-box-like room {room['id']}")
    return candidate


def _remove_duplicate_and_collinear(points: Iterable[Point]) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if result and point == result[-1]:
            continue
        if len(result) >= 2 and (result[-2][0] == result[-1][0] == point[0] or result[-2][1] == result[-1][1] == point[1]):
            result[-1] = point
        else:
            result.append(point)
    return result if len(result) >= 2 else [*result, *result]


def _metrics(
    rings: list[dict[str, Any]],
    owners: dict[Any, Any] | tuple[int, ...],
    plan: dict[str, Any],
    rooms: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    drawing_units_per_metre = plan["drawing_units_per_metre"]
    length_units = 0.0
    bends = 0
    for ring in rings:
        for leg in ring["legs"]:
            points = [_tuple_point(point) for point in leg["polyline"]]
            length_units += _polyline_length(points)
            bends += max(0, len(points) - 2)
    areas: list[float] = []
    if rooms and owners:
        for owner in sorted(set(owners)):
            areas.append(sum(room["area_m2"] for index, room in enumerate(rooms) if owners[index] == owner))
    length_m = length_units / drawing_units_per_metre
    area_gap = max(areas) - min(areas) if areas else 0.0
    return {
        "hub_count": len(rings),
        "length_m": length_m,
        "crossings": 0,
        "overlap_m": 0.0,
        "bends": bends,
        "route_cost": length_m + 0.5 * bends,
        "area_gap_m2": area_gap,
    }


def _polyline_length(points: list[Point]) -> float:
    return sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(points, points[1:]))


def _tuple_point(point: dict[str, Any]) -> Point:
    return float(point["x"]), float(point["y"])


def _point_object(point: Point) -> dict[str, float]:
    return {"x": point[0], "y": point[1]}


def _infeasible(plan_id: str, lower_bound: int, code: str, message: str) -> dict[str, Any]:
    return {
        "plan_id": plan_id,
        "status": "infeasible",
        "lower_bound_hubs": lower_bound,
        "hubs": [],
        "assignments": [],
        "rings": [],
        "diagnostics": [{"code": code, "message": message}],
    }
