"""The 3D wall sketch uses only verified portal and obstacle locations."""

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from cable_planner.web.architecture import architecture_solids, wall_solids


def _rectangle(x0, y0, x1, y1):
    return {"exterior": [
        {"x": x0, "y": y0}, {"x": x1, "y": y0},
        {"x": x1, "y": y1}, {"x": x0, "y": y1}, {"x": x0, "y": y0},
    ], "holes": []}


def test_visual_wall_has_gap_at_verified_door_and_window():
    plan = {
        "drawing_units_per_metre": 1,
        "portals": [{"segment": [{"x": 5, "y": 5}, {"x": 5, "y": 5.1}]}],
        "obstacles": [
            {"id": "wall:0", "kind": "wall", "geometry": _rectangle(4.9, 0, 5.1, 10)},
            {"id": "window:0", "kind": "window", "geometry": _rectangle(4.9, 8, 5.1, 9)},
        ],
    }
    pieces = wall_solids(plan)
    wall = unary_union([Polygon(
        [(point["x"], point["y"]) for point in piece["geometry"]["exterior"]],
        [[(point["x"], point["y"]) for point in hole]
         for hole in piece["geometry"]["holes"]],
    ) for piece in pieces])

    assert wall.contains(Point(5, 2))
    assert not wall.intersects(Point(5, 5))
    assert not wall.intersects(Point(5, 8.5))


def test_window_lines_are_rendered_as_translucent_architectural_features():
    plan = {
        "drawing_units_per_metre": 10,
        "portals": [],
        "obstacles": [{"id": "window-line", "kind": "window", "geometry": [
            {"x": 2, "y": 3}, {"x": 2, "y": 7},
        ]}],
    }
    solids = architecture_solids(plan)
    assert solids["wall_solids"] == []
    assert len(solids["window_solids"]) == 1
    geometry = solids["window_solids"][0]["geometry"]
    window = Polygon([(point["x"], point["y"]) for point in geometry["exterior"]])
    assert window.contains(Point(2, 5))
    assert 3.6 < window.area < 3.8
