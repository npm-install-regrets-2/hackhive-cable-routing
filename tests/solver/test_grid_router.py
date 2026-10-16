import json
from pathlib import Path
import pytest
import networkx as nx
from cable_planner.solver import grid_router as grid_router_module
from jsonschema import Draft202012Validator

from cable_planner.solver.grid_router import (
    hub_count_lower_bound, solve, HananRouter, find_legal_hub_candidates,
    _ring_route_cost, _fixed_hub_solution_rank, _partition_connected, _portal_connectivity,
    _edge_interaction_penalty, _route_legs_in_order, _clearance_shortfall_m,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "three_room_plan.json"
SCHEMA = ROOT / "shared" / "schema" / "common.schema.json"
OUTPUTS = ROOT / "examples" / "outputs"


@pytest.fixture
def plan():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_grid_router_fixture_valid(plan):
    solution = solve(plan)
    assert solution["status"] == "feasible"
    assert solution["lower_bound_hubs"] == 1
    assert len(solution["hubs"]) == 1
    assert len(solution["rings"]) == 1
    ring = solution["rings"][0]
    assert ring["stop_ids"][0] == ring["hub_id"] == ring["stop_ids"][-1]
    assert len(ring["legs"]) == 4

    # Validate against shared schema
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(
        {"schema_version": "0.1.0", "plan": plan, "solution": solution}
    )


def test_grid_router_with_obstacle(plan):
    # Add a wall obstacle to the plan
    import copy
    with_obstacle = copy.deepcopy(plan)
    with_obstacle["obstacles"] = [
        {
            "id": "wall:1",
            "kind": "wall",
            "geometry": [{"x": 1.0, "y": 1.0}, {"x": 1.0, "y": 3.0}]
        }
    ]
    solution = solve(with_obstacle)
    assert solution["status"] == "feasible"
    assert len(solution["hubs"]) == 1
    assert len(solution["rings"]) == 1


def test_indexed_route_penalties_match_full_edge_scan(monkeypatch):
    # Isolate the original crossing/overlap penalties from the later soft
    # near-parallel clearance preference.
    monkeypatch.setattr(grid_router_module, "MIN_CABLE_CLEARANCE_M", 0.0)
    graph = nx.Graph()
    edges = [
        ((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (2.0, 0.0)),
        ((1.0, -1.0), (1.0, 0.0)), ((1.0, 0.0), (1.0, 1.0)),
        ((0.0, 0.1), (1.0, 0.1)),
    ]
    graph.add_edges_from((a, b, {"weight": 1.0, "base_weight": 1.0}) for a, b in edges)
    first_path = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    second_path = [(1.0, -1.0), (1.0, 0.0), (1.0, 1.0)]

    class FixedPathRouter:
        def __init__(self):
            self.graph = graph
            self.calls = []

        def route_path(self, start, end, dynamic_graph=None):
            self.calls.append({(a, b): data["weight"] for a, b, data in dynamic_graph.edges(data=True)})
            return first_path if len(self.calls) == 1 else second_path

    router = FixedPathRouter()
    _route_legs_in_order(router, [(0.0, 0.0), (2.0, 0.0), (1.0, 1.0)], (0, 1), [], 10.0)

    expected = graph.copy()
    routed_segments = list(zip(first_path, first_path[1:]))
    for a, b in expected.edges():
        expected[a][b]["weight"] += sum(
            _edge_interaction_penalty(a, b, c, d, [], 10.0)
            for c, d in routed_segments
        )
    assert router.calls[1] == pytest.approx(
        {(a, b): expected[a][b]["weight"] for a, b in expected.edges()}
    )


def test_open_passage_adds_distributed_routing_lanes(plan):
    plan["portals"][1]["segment"] = [{"x": 12, "y": 0.5}, {"x": 12, "y": 4.5}]
    router = HananRouter(plan, cable_wall_clearance_m=0)
    passage_lanes = [y for y in router.ys if 0.5 < y < 4.5]
    assert len(passage_lanes) >= 8


def test_clearance_shortfall_is_a_soft_rank_only_measure():
    ring = {"legs": [
        {"polyline": [{"x": 0, "y": 0}, {"x": 10, "y": 0}]},
        {"polyline": [{"x": 0, "y": 2.5}, {"x": 10, "y": 2.5}]},
    ]}
    assert _clearance_shortfall_m(ring, scale=10) == pytest.approx(0.5)


def test_plan_13033_compares_connected_partitions_by_checked_cost():
    from cable_planner.validation.checker import IndependentValidator
    from cable_planner.metrics.calculator import calculate_all_metrics

    combined = json.loads((OUTPUTS / "kaggle_13033_combined.json").read_text(encoding="utf-8"))
    plan = combined["plan"]
    solution = solve(plan)
    report = IndependentValidator().validate(plan, solution)

    assert report.is_valid
    assert report.recomputed_metrics.hub_count == 3
    assert sorted(sum(a["hub_id"] == h["id"] for a in solution["assignments"]) for h in solution["hubs"]) == [1, 1, 3]
    assert report.recomputed_metrics.route_cost < 43.0  # incl. visible single-node hub loops (4d + 2 J each)
    assert report.recomputed_metrics.crossings == 0
    assert report.recomputed_metrics.overlap_m <= _stub_overlap_limit_m(solution)
    assert report.recomputed_metrics.area_gap_m2 < 73.9414
    rank = _fixed_hub_solution_rank(
        solution, {r["id"]: r for r in plan["rooms"]}, plan, plan["drawing_units_per_metre"]
    )
    assert rank == pytest.approx((report.recomputed_metrics.route_cost, report.recomputed_metrics.area_gap_m2), abs=0.0001)

    hub = solution["hubs"][0]
    ring = solution["rings"][0]
    exempt = [(hub["point"]["x"], hub["point"]["y"])] + [
        (node["point"]["x"], node["point"]["y"]) for node in plan["nodes"]
    ]
    local_cost = _ring_route_cost(ring, plan["drawing_units_per_metre"], exempt)
    ring_only = {**solution, "rings": [ring], "hubs": [hub]}
    independent_cost = calculate_all_metrics(plan, ring_only).route_cost
    assert local_cost == pytest.approx(independent_cost, abs=0.0001)


def test_plan_14433_compares_connected_partitions_by_checked_cost():
    from cable_planner.validation.checker import IndependentValidator

    combined = json.loads((OUTPUTS / "kaggle_14433_combined.json").read_text(encoding="utf-8"))
    plan = combined["plan"]
    solution = solve(plan)
    report = IndependentValidator().validate(plan, solution)

    assert report.is_valid
    assert report.recomputed_metrics.crossings == 0
    assert report.recomputed_metrics.overlap_m <= _stub_overlap_limit_m(solution)
    assert report.recomputed_metrics.route_cost < 48.0  # incl. visible single-node hub stub
    assert report.recomputed_metrics.area_gap_m2 < 86.2188
    assert sorted(sum(a["hub_id"] == h["id"] for a in solution["assignments"]) for h in solution["hubs"]) == [1, 4]
    rank = _fixed_hub_solution_rank(
        solution, {r["id"]: r for r in plan["rooms"]}, plan, plan["drawing_units_per_metre"]
    )
    assert rank == pytest.approx((report.recomputed_metrics.route_cost, report.recomputed_metrics.area_gap_m2), abs=0.0001)


@pytest.mark.parametrize("filename,hub_count,expected_counts", [
    ("kaggle_13033_combined.json", 3, (1, 1, 3)),
    ("kaggle_14433_combined.json", 2, (1, 4)),
])
def test_portal_graph_forces_uneven_node_counts(filename, hub_count, expected_counts):
    plan = json.loads((OUTPUTS / filename).read_text(encoding="utf-8"))["plan"]
    rooms = sorted((room for room in plan["rooms"] if room["eligible"]), key=lambda room: room["id"])
    room_ids = [room["id"] for room in rooms]
    graph = _portal_connectivity(plan, set(room_ids))
    rules = plan["rules"]
    partitions = _partition_connected(
        room_ids, graph, hub_count, rules["max_nodes_per_hub"],
        rules["max_area_m2_per_hub"], {room["id"]: room for room in rooms},
    )
    assert partitions
    assert all(tuple(sorted(map(len, partition))) == expected_counts for partition in partitions)


def _stub_overlap_limit_m(solution):
    """Only single-node hubs may retrace (out-and-back stub); allow the largest offset each."""
    from cable_planner.solver.grid_router import SINGLE_NODE_HUB_OFFSETS_M
    single_node = sum(len(ring["stop_ids"]) == 3 for ring in solution["rings"])
    return single_node * max(SINGLE_NODE_HUB_OFFSETS_M, default=0.0) + 0.01
