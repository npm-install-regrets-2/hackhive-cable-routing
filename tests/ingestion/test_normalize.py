import json
from pathlib import Path

from jsonschema import Draft202012Validator
from shapely.geometry import MultiPolygon, Point, Polygon, box

from cable_planner.ingestion import Rules, normalize_plan
from cable_planner.geometry import portal_graph


def fixture():
    """Synthetic, not organizer data: two 25 m² rooms with one door."""
    return {
        "id": 42,
        "inner": box(0, 0, 20, 10),
        "area": 50.0,
        "living": box(0, 0, 10, 10),
        "bedroom": box(10, 0, 20, 10),
        "door": box(9.5, 4, 10.5, 6),
        "wall": None,
        "window": None,
    }


def validate(plan):
    schema_path = Path(__file__).resolve().parents[2] / "shared/schema/common.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator({"$ref": "#/$defs/plan", "$defs": schema["$defs"]}).validate(plan)


def test_synthetic_fixture_has_stable_ids_scale_nodes_and_door():
    first = normalize_plan(fixture())
    second = normalize_plan(fixture())
    assert first.ok and first == second
    plan = first.plan
    validate(plan)
    assert plan["drawing_units_per_metre"] == 2
    assert [(r["id"], r["area_m2"]) for r in plan["rooms"]] == [
        ("room:living:000", 25), ("room:bedroom:000", 25)]
    assert [n["room_id"] for n in plan["nodes"]] == [r["id"] for r in plan["rooms"]]
    assert all(n["source"] == "development_fallback" for n in plan["nodes"])
    assert len(plan["portals"]) == 1
    assert plan["portals"][0]["kind"] == "door"
    assert portal_graph(plan)["room:living:000"] == ("room:bedroom:000",)
    assert plan["rules"]["max_nodes_per_hub"] == 5


def test_multipart_components_and_configurable_limits():
    raw = fixture()
    raw["living"] = MultiPolygon([box(0, 0, 5, 5), box(5, 0, 10, 5)])
    result = normalize_plan(raw, rules=Rules(max_area_m2_per_hub=40, max_nodes_per_hub=3))
    assert result.ok
    assert [r["id"] for r in result.plan["rooms"]] == [
        "room:living:000", "room:living:001", "room:bedroom:000"]
    assert result.plan["rules"]["max_nodes_per_hub"] == 3


def test_invalid_scale_and_unusable_geometry_are_explicit():
    raw = fixture()
    raw["area"] = 0
    assert normalize_plan(raw).diagnostics[0]["code"] == "invalid_scale"
    raw = fixture()
    raw["living"] = Polygon([(0, 0), (10, 10), (0, 10), (10, 0), (0, 0)])
    result = normalize_plan(raw)
    assert result.plan is None
    assert any(d["code"] == "unusable_geometry" for d in result.diagnostics)


def test_fixed_node_clearance_and_excluded_room():
    raw = fixture()
    raw["bathroom"] = box(0, 0, 2, 2)
    result = normalize_plan(raw, fixed_nodes={"room:living:000": (0.1, 5)})
    assert result.plan is None
    assert any(d["code"] == "invalid_fixed_node" for d in result.diagnostics)
    good = normalize_plan(raw, fixed_nodes={"room:living:000": (5, 5)})
    assert good.ok
    assert good.plan["nodes"][0]["source"] == "organizer"
    assert len(good.plan["nodes"]) == 2


def test_fallback_node_moves_away_from_wall_when_room_has_clear_space():
    raw = fixture()
    raw["wall"] = box(4.5, 4.5, 5.5, 5.5)

    result = normalize_plan(raw)

    assert result.ok, result.diagnostics
    validate(result.plan)
    node = next(node for node in result.plan["nodes"] if node["room_id"] == "room:living:000")
    point = Point(node["point"]["x"], node["point"]["y"])
    scale = result.plan["drawing_units_per_metre"]
    clearance = result.plan["rules"]["node_wall_clearance_m"] - result.plan["rules"]["geometry_tolerance"]
    assert raw["living"].boundary.distance(point) / scale >= clearance
    assert raw["wall"].distance(point) / scale >= clearance


def test_fallback_node_reports_when_no_clear_space_exists():
    raw = fixture()
    raw["wall"] = raw["living"]

    result = normalize_plan(raw)

    assert result.plan is None
    assert any(d["code"] == "invalid_fixed_node"
               and d["entity_ids"] == ["room:living:000"]
               and "no fallback point" in d["message"] for d in result.diagnostics)


def test_outside_and_narrow_room_fragments_have_measured_diagnostics():
    raw = fixture()
    raw["living"] = MultiPolygon([box(-0.8, 0, -0.4, 8), box(5, 1, 5.02, 8)])

    result = normalize_plan(raw)

    assert result.plan is None
    outside = next(d for d in result.diagnostics if d["code"] == "room_outside_boundary")
    assert outside["entity_ids"] == ["room:living:000"]
    assert "m2 outside" in outside["message"]
    narrow = [d for d in result.diagnostics if d["code"] == "invalid_fixed_node"]
    assert {tuple(d["entity_ids"]) for d in narrow} == {
        ("room:living:000",), ("room:living:001",)}
    assert all("0.5 m wall clearance" in d["message"]
               and "maximum room-boundary clearance" in d["message"] for d in narrow)


def test_outside_room_clipping_is_explicit_and_updates_plan_geometry():
    raw = fixture()
    raw["living"] = box(-2, 0, 10, 10)

    strict = normalize_plan(raw)
    assert strict.plan is None
    assert any(item["code"] == "room_outside_boundary" for item in strict.diagnostics)

    clipped = normalize_plan(raw, clip_outside_rooms=True)
    assert clipped.ok, clipped.diagnostics
    validate(clipped.plan)
    living = next(room for room in clipped.plan["rooms"] if room["id"] == "room:living:000")
    assert living["area_m2"] == 25
    assert min(point["x"] for point in living["geometry"]["exterior"]) == 0
    diagnostic = next(item for item in clipped.diagnostics if item["code"] == "room_clipped_to_boundary")
    assert diagnostic["entity_ids"] == ["room:living:000"]
    assert "5 m2 outside" in diagnostic["message"]


def test_wall_blocks_open_passage_and_missing_door_warns():
    raw = fixture()
    raw["door"] = None
    raw["wall"] = box(9.9, 0, 10.1, 10)
    result = normalize_plan(raw)
    assert result.ok
    assert result.plan["portals"] == []
    assert portal_graph(result.plan)["room:living:000"] == ()
    assert any(d["code"] == "disconnected_eligible_rooms" for d in result.diagnostics)


def test_unobstructed_shared_boundary_is_open_passage():
    raw = fixture()
    raw["door"] = None
    result = normalize_plan(raw)
    assert result.ok
    assert len(result.plan["portals"]) == 1
    assert result.plan["portals"][0]["kind"] == "open_passage"

