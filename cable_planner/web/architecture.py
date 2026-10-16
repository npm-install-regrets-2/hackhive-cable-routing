"""Schematic wall solids derived from the validated 2D Plan geometry.

Only visual openings are cut here. The normalizer and independent validator
remain the authorities for portals and cable legality.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon
from shapely.ops import unary_union


def _polygon(value: dict[str, Any]) -> Polygon:
    return Polygon(
        [(point["x"], point["y"]) for point in value["exterior"]],
        [[(point["x"], point["y"]) for point in hole] for hole in value.get("holes", [])],
    )


def _parts(geometry: Any) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry] if geometry.area > 0 else []
    if isinstance(geometry, (MultiPolygon, GeometryCollection)):
        return [part for child in geometry.geoms for part in _parts(child)]
    return []


def _wire_polygon(polygon: Polygon) -> dict[str, Any]:
    def ring(coords: Any) -> list[dict[str, float]]:
        return [{"x": float(x), "y": float(y)} for x, y in coords]

    return {
        "exterior": ring(polygon.exterior.coords),
        "holes": [ring(hole.coords) for hole in polygon.interiors],
    }


def architecture_solids(plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return source wall footprints with visible gaps at verified portals.

    ResPlan has no wall elevations or door-leaf widths. A 0.8 m schematic
    opening centered on each verified portal makes its location legible.
    Window footprints replace opaque wall material with translucent material.
    The original Plan and route coordinates are never changed.
    """
    scale = float(plan["drawing_units_per_metre"])
    half_opening = 0.4 * scale
    cutters = []
    for portal in plan["portals"]:
        endpoints = [(point["x"], point["y"]) for point in portal["segment"]]
        cutters.append(LineString(endpoints).buffer(half_opening, cap_style="square"))
    for obstacle in plan["obstacles"]:
        if obstacle["kind"] == "window" and "exterior" in obstacle["geometry"]:
            cutters.append(_polygon(obstacle["geometry"]))
    openings = unary_union(cutters) if cutters else GeometryCollection()

    solids = []
    windows = []
    for obstacle in plan["obstacles"]:
        if obstacle["kind"] == "window":
            geometry = obstacle["geometry"]
            window = _polygon(geometry) if "exterior" in geometry else LineString(
                [(point["x"], point["y"]) for point in geometry]
            ).buffer(0.04 * scale)
            for index, piece in enumerate(_parts(window)):
                windows.append({"id": f"{obstacle['id']}:piece:{index:03d}", "geometry": _wire_polygon(piece)})
            continue
        if obstacle["kind"] != "wall":
            continue
        geometry = obstacle["geometry"]
        if "exterior" in geometry:
            wall = _polygon(geometry)
        else:
            wall = LineString([(point["x"], point["y"]) for point in geometry]).buffer(0.06 * scale)
        for index, piece in enumerate(_parts(wall.difference(openings))):
            solids.append({"id": f"{obstacle['id']}:piece:{index:03d}", "geometry": _wire_polygon(piece)})
    return {"wall_solids": solids, "window_solids": windows}


def wall_solids(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Compatibility helper for callers interested only in wall pieces."""
    return architecture_solids(plan)["wall_solids"]
