"""Independent hard-rule validator for Plan and Solution objects."""

import math
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
from shapely.geometry import Point, LineString, Polygon

from cable_planner.validation.models import Diagnostic, RecomputedMetrics, ValidationReport
from cable_planner.validation.rules import (
    ELIGIBLE_ROOM_KINDS,
    EXCLUDED_ROOM_KINDS,
    ValidationConfig,
)
from cable_planner.validation.geometry import (
    parse_point,
    parse_polygon,
    parse_polyline,
    check_polyline_axis_aligned,
    check_node_clearance,
    check_internal_containment,
    check_obstacle_collision,
    points_are_close,
)
from cable_planner.metrics.calculator import calculate_all_metrics


class IndependentValidator:
    """Validator that verifies hard rules and computes metrics without trusting solver claims."""

    def __init__(self, config: Optional[ValidationConfig] = None):
        self.config = config or ValidationConfig()

    def validate(self, plan: Dict[str, Any], solution: Dict[str, Any]) -> ValidationReport:
        """Perform comprehensive independent validation of Plan and Solution."""
        plan_id = plan.get("id", "unknown_plan")
        violations: List[Diagnostic] = []
        warnings: List[Diagnostic] = []

        # Load plan rules if available
        if "rules" in plan:
            self.config = ValidationConfig.from_plan_rules(plan["rules"])

        scale = float(plan.get("drawing_units_per_metre", 1.0))
        if scale <= 0:
            violations.append(Diagnostic(
                code="INVALID_SCALE",
                message=f"drawing_units_per_metre must be positive, got {scale}",
                entity_ids=[plan_id]
            ))
            scale = 1.0

        tol_units = self.config.geometry_tolerance_m * scale

        # 1. Parse and validate Plan geometry
        rooms_by_id: Dict[str, Dict[str, Any]] = {}
        room_polys: Dict[str, Polygon] = {}
        eligible_room_ids: Set[str] = set()
        excluded_room_ids: Set[str] = set()
        total_eligible_area_m2 = 0.0

        for r in plan.get("rooms", []):
            r_id = r.get("id")
            rooms_by_id[r_id] = r
            kind = r.get("kind")
            eligible = r.get("eligible", False)
            area_m2 = float(r.get("area_m2", 0.0))

            if eligible:
                if kind not in ELIGIBLE_ROOM_KINDS:
                    violations.append(Diagnostic(
                        code="INVALID_ELIGIBLE_KIND",
                        message=f"Room '{r_id}' marked eligible but has kind '{kind}'",
                        entity_ids=[r_id]
                    ))
                eligible_room_ids.add(r_id)
                total_eligible_area_m2 += area_m2
                if area_m2 > self.config.max_area_m2_per_hub:
                    violations.append(Diagnostic(
                        code="ROOM_AREA_EXCEEDS_CAPACITY",
                        message=f"Eligible room '{r_id}' area ({area_m2} m2) exceeds hub max capacity ({self.config.max_area_m2_per_hub} m2)",
                        entity_ids=[r_id]
                    ))
            else:
                excluded_room_ids.add(r_id)

            try:
                poly = parse_polygon(r.get("geometry", {}))
                if not poly.is_valid:
                    violations.append(Diagnostic(
                        code="INVALID_ROOM_GEOMETRY",
                        message=f"Room '{r_id}' polygon is geometrically invalid",
                        entity_ids=[r_id]
                    ))
                room_polys[r_id] = poly
            except Exception as e:
                violations.append(Diagnostic(
                    code="MALFORMED_ROOM_GEOMETRY",
                    message=f"Could not parse polygon for room '{r_id}': {e}",
                    entity_ids=[r_id]
                ))

        # Parse internal boundary
        internal_boundary_poly: Optional[Polygon] = None
        try:
            internal_boundary_poly = parse_polygon(plan.get("internal_boundary", {}))
        except Exception as e:
            violations.append(Diagnostic(
                code="MALFORMED_INTERNAL_BOUNDARY",
                message=f"Could not parse internal_boundary polygon: {e}",
                entity_ids=[plan_id]
            ))

        # 2. Validate Nodes
        nodes_by_id: Dict[str, Dict[str, Any]] = {}
        room_nodes: Dict[str, List[str]] = {r_id: [] for r_id in rooms_by_id}

        for n in plan.get("nodes", []):
            n_id = n.get("id")
            nodes_by_id[n_id] = n
            r_id = n.get("room_id")
            if r_id not in rooms_by_id:
                violations.append(Diagnostic(
                    code="NODE_ORPHAN_ROOM",
                    message=f"Node '{n_id}' references unknown room '{r_id}'",
                    entity_ids=[n_id]
                ))
                continue

            room_nodes[r_id].append(n_id)

            if r_id in excluded_room_ids:
                violations.append(Diagnostic(
                    code="NODE_IN_EXCLUDED_ROOM",
                    message=f"Node '{n_id}' is placed in excluded room '{r_id}'",
                    entity_ids=[n_id, r_id]
                ))

            # Wall clearance and containment check
            if r_id in room_polys:
                pt_dict = n.get("point", {})
                n_pt = (float(pt_dict.get("x", 0.0)), float(pt_dict.get("y", 0.0)))
                min_clearance_units = self.config.node_wall_clearance_m * scale
                is_clear, actual_dist = check_node_clearance(n_pt, room_polys[r_id], min_clearance_units, tol_units)
                if not is_clear:
                    violations.append(Diagnostic(
                        code="NODE_WALL_CLEARANCE_VIOLATION",
                        message=(
                            f"Node '{n_id}' in room '{r_id}' violates {self.config.node_wall_clearance_m} m wall clearance: "
                            f"actual clearance = {actual_dist/scale:.3f} m"
                        ),
                        entity_ids=[n_id, r_id]
                    ))

        # Check: exactly one node per eligible room
        for r_id in eligible_room_ids:
            assigned_nodes = room_nodes.get(r_id, [])
            if len(assigned_nodes) == 0:
                violations.append(Diagnostic(
                    code="MISSING_FIXED_NODE",
                    message=f"Eligible room '{r_id}' has no fixed node",
                    entity_ids=[r_id]
                ))
            elif len(assigned_nodes) > 1:
                violations.append(Diagnostic(
                    code="MULTIPLE_FIXED_NODES",
                    message=f"Eligible room '{r_id}' has multiple fixed nodes: {assigned_nodes}",
                    entity_ids=[r_id] + assigned_nodes
                ))

        # 3. Build Traversability Graph from Portals
        traversability_graph = nx.Graph()
        for r_id in rooms_by_id:
            traversability_graph.add_node(r_id)

        portal_segments: List[Tuple[str, str, str, LineString]] = []
        for p in plan.get("portals", []):
            p_id = p.get("id")
            s_a = p.get("space_a_id")
            s_b = p.get("space_b_id")
            kind = p.get("kind")

            if kind not in ("door", "open_passage"):
                violations.append(Diagnostic(
                    code="INVALID_PORTAL_KIND",
                    message=f"Portal '{p_id}' has invalid kind '{kind}'",
                    entity_ids=[p_id]
                ))

            if s_a in rooms_by_id and s_b in rooms_by_id:
                traversability_graph.add_edge(s_a, s_b, portal_id=p_id, kind=kind)

            try:
                p_seg = parse_polyline(p.get("segment", []))
                portal_segments.append((p_id, s_a, s_b, p_seg))
            except Exception as e:
                violations.append(Diagnostic(
                    code="MALFORMED_PORTAL_SEGMENT",
                    message=f"Could not parse portal segment for '{p_id}': {e}",
                    entity_ids=[p_id]
                ))

        # Parse Obstacles
        obstacle_geoms: List[Tuple[str, str, Any]] = []
        for obs in plan.get("obstacles", []):
            obs_id = obs.get("id")
            obs_kind = obs.get("kind")
            geom_data = obs.get("geometry")
            try:
                if isinstance(geom_data, list):
                    # Polyline LineString
                    obs_geom = parse_polyline(geom_data)
                elif isinstance(geom_data, dict) and "exterior" in geom_data:
                    # Polygon
                    obs_geom = parse_polygon(geom_data)
                else:
                    obs_geom = None
                if obs_geom:
                    obstacle_geoms.append((obs_id, obs_kind, obs_geom))
            except Exception as e:
                violations.append(Diagnostic(
                    code="MALFORMED_OBSTACLE_GEOMETRY",
                    message=f"Could not parse geometry for obstacle '{obs_id}': {e}",
                    entity_ids=[obs_id]
                ))

        # 4. Validate Solution matching plan
        sol_plan_id = solution.get("plan_id")
        if sol_plan_id != plan_id:
            violations.append(Diagnostic(
                code="PLAN_ID_MISMATCH",
                message=f"Solution references plan '{sol_plan_id}', expected '{plan_id}'",
                entity_ids=[plan_id, str(sol_plan_id)]
            ))

        hubs = solution.get("hubs", [])
        hubs_by_id: Dict[str, Dict[str, Any]] = {}
        for h in hubs:
            h_id = h.get("id")
            hubs_by_id[h_id] = h
            hr_id = h.get("room_id")
            if hr_id not in rooms_by_id:
                violations.append(Diagnostic(
                    code="HUB_ORPHAN_ROOM",
                    message=f"Hub '{h_id}' references unknown room '{hr_id}'",
                    entity_ids=[h_id]
                ))
            elif hr_id in excluded_room_ids:
                violations.append(Diagnostic(
                    code="HUB_IN_EXCLUDED_ROOM",
                    message=f"Hub '{h_id}' placed in excluded room '{hr_id}'",
                    entity_ids=[h_id, hr_id]
                ))
            elif hr_id in room_polys:
                h_pt = parse_point(h.get("point", {}))
                if not room_polys[hr_id].buffer(tol_units).covers(Point(h_pt)):
                    violations.append(Diagnostic(
                        code="HUB_OUTSIDE_ASSIGNED_ROOM",
                        message=f"Hub '{h_id}' point ({h_pt[0]}, {h_pt[1]}) is outside room '{hr_id}' geometry",
                        entity_ids=[h_id, hr_id]
                    ))

        # Check Hub count lower bound
        min_hubs_by_area = math.ceil(total_eligible_area_m2 / self.config.max_area_m2_per_hub)
        min_hubs_by_nodes = math.ceil(len(eligible_room_ids) / self.config.max_nodes_per_hub)
        theoretical_lower_bound = max(min_hubs_by_area, min_hubs_by_nodes)

        if len(hubs) < theoretical_lower_bound and len(eligible_room_ids) > 0:
            violations.append(Diagnostic(
                code="INSUFFICIENT_HUBS",
                message=(
                    f"Solution opens {len(hubs)} hubs, but theoretical lower bound is "
                    f"{theoretical_lower_bound} (area {total_eligible_area_m2:.1f} m2 -> {min_hubs_by_area}, "
                    f"nodes {len(eligible_room_ids)} -> {min_hubs_by_nodes})"
                ),
                entity_ids=[h["id"] for h in hubs]
            ))

        # 5. Validate Assignments
        assignments = solution.get("assignments", [])
        assigned_rooms: Set[str] = set()
        assigned_nodes: Set[str] = set()
        hub_assigned_rooms: Dict[str, Set[str]] = {h_id: set() for h_id in hubs_by_id}
        hub_assigned_nodes: Dict[str, Set[str]] = {h_id: set() for h_id in hubs_by_id}

        for a in assignments:
            r_id = a.get("room_id")
            n_id = a.get("node_id")
            h_id = a.get("hub_id")

            if h_id not in hubs_by_id:
                violations.append(Diagnostic(
                    code="ASSIGNMENT_UNKNOWN_HUB",
                    message=f"Assignment references unknown hub '{h_id}'",
                    entity_ids=[h_id, str(r_id)]
                ))
                continue

            if r_id in assigned_rooms:
                violations.append(Diagnostic(
                    code="DUPLICATE_ROOM_ASSIGNMENT",
                    message=f"Room '{r_id}' is assigned to multiple hubs",
                    entity_ids=[r_id]
                ))
            if n_id in assigned_nodes:
                violations.append(Diagnostic(
                    code="DUPLICATE_NODE_ASSIGNMENT",
                    message=f"Node '{n_id}' is assigned to multiple hubs",
                    entity_ids=[n_id]
                ))

            if r_id in excluded_room_ids:
                violations.append(Diagnostic(
                    code="EXCLUDED_ROOM_ASSIGNED",
                    message=f"Excluded room '{r_id}' cannot be assigned to hub '{h_id}'",
                    entity_ids=[r_id, h_id]
                ))

            if r_id in rooms_by_id and n_id in nodes_by_id:
                expected_room = nodes_by_id[n_id].get("room_id")
                if expected_room != r_id:
                    violations.append(Diagnostic(
                        code="ASSIGNMENT_NODE_ROOM_MISMATCH",
                        message=f"Assignment pairs node '{n_id}' (in '{expected_room}') with room '{r_id}'",
                        entity_ids=[n_id, r_id]
                    ))

            assigned_rooms.add(r_id)
            assigned_nodes.add(n_id)
            hub_assigned_rooms[h_id].add(r_id)
            hub_assigned_nodes[h_id].add(n_id)

        # Check: Every eligible room must be assigned
        unassigned_eligible = eligible_room_ids - assigned_rooms
        if unassigned_eligible:
            violations.append(Diagnostic(
                code="UNASSIGNED_ELIGIBLE_ROOMS",
                message=f"Eligible rooms were not assigned: {list(unassigned_eligible)}",
                entity_ids=list(unassigned_eligible)
            ))

        # 6. Validate Hub Capacity and Territory Connectivity
        for h_id, r_ids in hub_assigned_rooms.items():
            n_ids = hub_assigned_nodes[h_id]
            # Check node count capacity
            if len(n_ids) > self.config.max_nodes_per_hub:
                violations.append(Diagnostic(
                    code="HUB_NODE_CAPACITY_EXCEEDED",
                    message=(
                        f"Hub '{h_id}' owns {len(n_ids)} nodes, exceeding "
                        f"limit of {self.config.max_nodes_per_hub}"
                    ),
                    entity_ids=[h_id] + list(n_ids)
                ))

            # Check area capacity
            hub_area = sum(float(rooms_by_id[r].get("area_m2", 0.0)) for r in r_ids if r in rooms_by_id)
            if hub_area > self.config.max_area_m2_per_hub + 1e-4:
                violations.append(Diagnostic(
                    code="HUB_AREA_CAPACITY_EXCEEDED",
                    message=(
                        f"Hub '{h_id}' assigned area ({hub_area:.2f} m2) exceeds "
                        f"limit of {self.config.max_area_m2_per_hub} m2"
                    ),
                    entity_ids=[h_id] + list(r_ids)
                ))

            # Check: Hub must have at least one assigned room
            if len(r_ids) == 0 and len(eligible_room_ids) > 0:
                violations.append(Diagnostic(
                    code="EMPTY_HUB_TERRITORY",
                    message=f"Opened hub '{h_id}' has zero assigned rooms",
                    entity_ids=[h_id]
                ))

            # Check: Territory connectivity
            if len(r_ids) > 1:
                subgraph = traversability_graph.subgraph(r_ids)
                if not nx.is_connected(subgraph):
                    components = list(nx.connected_components(subgraph))
                    violations.append(Diagnostic(
                        code="DISCONNECTED_TERRITORY",
                        message=f"Hub '{h_id}' territory is disconnected into {len(components)} components: {components}",
                        entity_ids=[h_id] + list(r_ids)
                    ))

        # 7. Validate Rings
        rings = solution.get("rings", [])
        ring_hubs = set()

        for r_idx, ring in enumerate(rings):
            r_hub_id = ring.get("hub_id")
            if r_hub_id not in hubs_by_id:
                violations.append(Diagnostic(
                    code="RING_UNKNOWN_HUB",
                    message=f"Ring {r_idx} references unknown hub '{r_hub_id}'",
                    entity_ids=[str(r_hub_id)]
                ))
                continue

            if r_hub_id in ring_hubs:
                violations.append(Diagnostic(
                    code="MULTIPLE_RINGS_FOR_HUB",
                    message=f"Hub '{r_hub_id}' has multiple rings assigned",
                    entity_ids=[r_hub_id]
                ))
            ring_hubs.add(r_hub_id)

            stop_ids = ring.get("stop_ids", [])
            legs = ring.get("legs", [])

            if len(stop_ids) < 3:
                violations.append(Diagnostic(
                    code="INSUFFICIENT_RING_STOPS",
                    message=f"Ring for hub '{r_hub_id}' must have at least 3 stops, got {len(stop_ids)}",
                    entity_ids=[r_hub_id]
                ))
                continue

            # Closure check
            if stop_ids[0] != r_hub_id or stop_ids[-1] != r_hub_id:
                violations.append(Diagnostic(
                    code="RING_NOT_CLOSED",
                    message=f"Ring for hub '{r_hub_id}' must begin and end at hub '{r_hub_id}', got stops {stop_ids[0]} -> ... -> {stop_ids[-1]}",
                    entity_ids=[r_hub_id]
                ))

            # Exactly once visit of all assigned nodes
            assigned_nodes_for_hub = hub_assigned_nodes.get(r_hub_id, set())
            visited_nodes = stop_ids[1:-1]
            if set(visited_nodes) != assigned_nodes_for_hub or len(visited_nodes) != len(assigned_nodes_for_hub):
                violations.append(Diagnostic(
                    code="INVALID_RING_VISITS",
                    message=(
                        f"Ring for hub '{r_hub_id}' visited nodes {visited_nodes}, but "
                        f"assigned nodes are {list(assigned_nodes_for_hub)}"
                    ),
                    entity_ids=[r_hub_id] + visited_nodes
                ))

            # Legs validation
            expected_legs = len(stop_ids) - 1
            if len(legs) != expected_legs:
                violations.append(Diagnostic(
                    code="LEG_COUNT_MISMATCH",
                    message=f"Ring has {len(stop_ids)} stops but {len(legs)} legs (expected {expected_legs})",
                    entity_ids=[r_hub_id]
                ))
                continue

            hub_pt = parse_point(hubs_by_id[r_hub_id].get("point", {}))

            # Check consecutive legs and stop IDs
            for i, leg in enumerate(legs):
                from_id = leg.get("from_id")
                to_id = leg.get("to_id")
                expected_from = stop_ids[i]
                expected_to = stop_ids[i + 1]

                if from_id != expected_from or to_id != expected_to:
                    violations.append(Diagnostic(
                        code="LEG_ENDPOINT_MISMATCH",
                        message=(
                            f"Leg {i} declared endpoints ({from_id} -> {to_id}) do not match "
                            f"ring sequence ({expected_from} -> {expected_to})"
                        ),
                        entity_ids=[r_hub_id, str(from_id), str(to_id)]
                    ))

                polyline_pts = leg.get("polyline", [])
                if len(polyline_pts) < 2:
                    violations.append(Diagnostic(
                        code="DEGENERATE_LEG_POLYLINE",
                        message=f"Leg {i} polyline has fewer than 2 points",
                        entity_ids=[r_hub_id, str(from_id), str(to_id)]
                    ))
                    continue

                p_start = parse_point(polyline_pts[0])
                p_end = parse_point(polyline_pts[-1])

                # Verify start point matches stop entity location
                if i == 0:
                    if not points_are_close(p_start, hub_pt, tol_units):
                        violations.append(Diagnostic(
                            code="RING_START_NOT_AT_HUB",
                            message=f"Ring polyline starts at ({p_start[0]}, {p_start[1]}), hub '{r_hub_id}' is at ({hub_pt[0]}, {hub_pt[1]})",
                            entity_ids=[r_hub_id]
                        ))
                else:
                    prev_end = parse_point(legs[i - 1].get("polyline", [])[-1])
                    if not points_are_close(p_start, prev_end, tol_units):
                        violations.append(Diagnostic(
                            code="DISCONNECTED_LEGS",
                            message=f"Leg {i} start does not match Leg {i-1} end within 1 mm tolerance",
                            entity_ids=[r_hub_id, str(from_id)]
                        ))

                if i == len(legs) - 1:
                    if not points_are_close(p_end, hub_pt, tol_units):
                        violations.append(Diagnostic(
                            code="RING_END_NOT_AT_HUB",
                            message=f"Ring polyline ends at ({p_end[0]}, {p_end[1]}), hub '{r_hub_id}' is at ({hub_pt[0]}, {hub_pt[1]})",
                            entity_ids=[r_hub_id]
                        ))
                elif to_id in nodes_by_id:
                    node_pt = parse_point(nodes_by_id[to_id].get("point", {}))
                    if not points_are_close(p_end, node_pt, tol_units):
                        violations.append(Diagnostic(
                            code="LEG_END_NOT_AT_NODE",
                            message=f"Leg {i} ends at ({p_end[0]}, {p_end[1]}), node '{to_id}' is at ({node_pt[0]}, {node_pt[1]})",
                            entity_ids=[r_hub_id, to_id]
                        ))

                # Axis alignment
                axis_errors = check_polyline_axis_aligned(polyline_pts, tol_units)
                for err in axis_errors:
                    violations.append(Diagnostic(
                        code="NON_AXIS_ALIGNED_CABLE",
                        message=f"Leg {i} ({from_id} -> {to_id}): {err}",
                        entity_ids=[r_hub_id, str(from_id), str(to_id)]
                    ))

                # Boundary containment & Obstacle collisions
                leg_ls = parse_polyline(polyline_pts)
                if internal_boundary_poly and not check_internal_containment(leg_ls, internal_boundary_poly, tol_units):
                    violations.append(Diagnostic(
                        code="CABLE_OUTSIDE_INTERNAL_BOUNDARY",
                        message=f"Leg {i} ({from_id} -> {to_id}) travels outside the internal boundary",
                        entity_ids=[r_hub_id, str(from_id), str(to_id)]
                    ))

                collisions = check_obstacle_collision(leg_ls, obstacle_geoms, tol_units)
                for obs_id, obs_kind, msg in collisions:
                    violations.append(Diagnostic(
                        code="CABLE_OBSTACLE_COLLISION",
                        message=f"Leg {i} ({from_id} -> {to_id}): {msg}",
                        entity_ids=[r_hub_id, str(from_id), str(to_id), obs_id]
                    ))

        # Check: Every opened hub must have a ring
        missing_rings = set(hubs_by_id.keys()) - ring_hubs
        if missing_rings:
            violations.append(Diagnostic(
                code="MISSING_HUB_RING",
                message=f"Hubs missing closed rings: {list(missing_rings)}",
                entity_ids=list(missing_rings)
            ))

        # 8. Recompute independent metrics
        recomputed = calculate_all_metrics(plan, solution, tol_m=self.config.geometry_tolerance_m)
        optimizer_metrics_match = True

        claimed_metrics = solution.get("metrics")
        if claimed_metrics:
            discrepancies = []
            for field_name in ("hub_count", "crossings", "bends"):
                if claimed_metrics.get(field_name) != getattr(recomputed, field_name):
                    discrepancies.append(
                        f"{field_name}: claimed {claimed_metrics.get(field_name)} != recomputed {getattr(recomputed, field_name)}"
                    )
            for field_name in ("length_m", "overlap_m", "route_cost", "area_gap_m2"):
                claimed_val = float(claimed_metrics.get(field_name, 0.0))
                calc_val = getattr(recomputed, field_name)
                if abs(claimed_val - calc_val) > 1e-2:
                    discrepancies.append(
                        f"{field_name}: claimed {claimed_val:.4f} != recomputed {calc_val:.4f}"
                    )

            if discrepancies:
                optimizer_metrics_match = False
                warnings.append(Diagnostic(
                    code="CLAIMED_METRICS_DISCREPANCY",
                    message=f"Claimed metrics differ from independently recomputed metrics: {'; '.join(discrepancies)}",
                    entity_ids=[plan_id]
                ))

        is_valid = (len(violations) == 0)

        return ValidationReport(
            plan_id=plan_id,
            is_valid=is_valid,
            violations=violations,
            warnings=warnings,
            recomputed_metrics=recomputed,
            optimizer_metrics_match=optimizer_metrics_match,
        )
