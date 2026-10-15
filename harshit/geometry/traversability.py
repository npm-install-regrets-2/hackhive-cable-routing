"""Room adjacency derived solely from normalized, verified portals."""

from __future__ import annotations

from typing import Any, Mapping


def portal_graph(plan: Mapping[str, Any], *, allow_excluded_transit: bool = False) -> dict[str, tuple[str, ...]]:
    rooms = {room["id"]: room for room in plan["rooms"]}
    adjacency: dict[str, set[str]] = {room_id: set() for room_id in rooms}
    for portal in plan["portals"]:
        a, b = portal["space_a_id"], portal["space_b_id"]
        if a not in rooms or b not in rooms:
            raise ValueError(f"portal {portal['id']} references an unknown room")
        if not allow_excluded_transit and (not rooms[a]["eligible"] or not rooms[b]["eligible"]):
            continue
        adjacency[a].add(b)
        adjacency[b].add(a)
    return {room_id: tuple(sorted(neighbors)) for room_id, neighbors in sorted(adjacency.items())}

