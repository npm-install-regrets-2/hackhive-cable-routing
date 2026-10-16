"""Visual overlay renderer derived strictly from checked validation and metric data."""

import math
from typing import Any, Dict, Optional, Tuple
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Patch, Rectangle
from matplotlib.lines import Line2D
import matplotlib.patheffects as pe
from shapely.geometry import LineString, MultiLineString, Point, Polygon

from cable_planner.validation.models import ValidationReport


# Distinct, harmonious color palette for territories
TERRITORY_COLORS = [
    "#2468B4",  # Blue
    "#E3821B",  # Orange
    "#2A8A66",  # Green
    "#8153A6",  # Purple
    "#C64E55",  # Red
    "#168B9B",  # Teal
    "#9A7620",  # Ochre
    "#5965A8",  # Indigo
]

TERRITORY_FILL_COLORS = [
    "#DCE8F8",  # Pale blue
    "#FCE7D0",  # Pale orange
    "#DCEFE6",  # Pale green
    "#EAE1F2",  # Pale purple
    "#F5DEDF",  # Pale red
    "#D9EEF0",  # Pale teal
    "#F0EAD7",  # Pale ochre
    "#E0E3F2",  # Pale indigo
]

ROOM_TYPE_COLORS = {
    "living": "#A8DADC", "bedroom": "#CDB4DB", "kitchen": "#FFD6A5",
    "storage": "#BDE0FE", "bathroom": "#D9E2F2", "balcony": "#CAFFBF",
    "stair": "#E9C46A", "garden": "#95D5B2", "pool": "#48CAE4",
    "parking": "#ADB5BD", "land": "#D8F3DC", "other": "#DEE2E6",
}


def _open_passage_lines(plan: Dict[str, Any]) -> list[LineString]:
    return [
        LineString([(p["x"], p["y"]) for p in portal.get("segment", [])])
        for portal in plan.get("portals", [])
        if portal.get("kind") == "open_passage" and len(portal.get("segment", [])) >= 2
    ]


def _shared_cable_spans(
    rings: list[Dict[str, Any]], scale: float,
) -> list[Tuple[str, float, float, float]]:
    """Return collinear spans used by at least two cable legs."""
    tolerance = 0.001 * scale
    groups: list[Tuple[str, float, list[Tuple[float, float]]]] = []
    for ring in rings:
        for leg in ring.get("legs", []):
            points = [
                (float(point["x"]), float(point["y"]))
                for point in leg.get("polyline", [])
            ]
            for (x1, y1), (x2, y2) in zip(points, points[1:]):
                if math.dist((x1, y1), (x2, y2)) <= tolerance:
                    continue
                if abs(y1 - y2) <= tolerance:
                    axis, fixed = "h", (y1 + y2) / 2
                    lo, hi = sorted((x1, x2))
                elif abs(x1 - x2) <= tolerance:
                    axis, fixed = "v", (x1 + x2) / 2
                    lo, hi = sorted((y1, y2))
                else:
                    continue
                group = next(
                    (item for item in groups
                     if item[0] == axis and abs(item[1] - fixed) <= tolerance),
                    None,
                )
                if group is None:
                    groups.append((axis, fixed, [(lo, hi)]))
                else:
                    group[2].append((lo, hi))

    shared: list[Tuple[str, float, float, float]] = []
    for axis, fixed, intervals in groups:
        overlaps: list[Tuple[float, float]] = []
        for index, (left, right) in enumerate(intervals):
            for other_left, other_right in intervals[index + 1:]:
                lo, hi = max(left, other_left), min(right, other_right)
                if hi - lo > tolerance:
                    overlaps.append((lo, hi))
        overlaps.sort()
        merged: list[list[float]] = []
        for lo, hi in overlaps:
            if merged and lo <= merged[-1][1] + tolerance:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        shared.extend((axis, fixed, lo, hi) for lo, hi in merged)
    return shared


def _draw_room_outline(
    ax: Any, exterior: list[Tuple[float, float]], passages: list[LineString],
    *, color: str, linewidth: float, zorder: int = 2,
) -> None:
    """Draw room edges while leaving shared open-passage spans unmarked."""
    if len(exterior) < 2:
        return
    for start, end in zip(exterior, exterior[1:] + exterior[:1]):
        edge = LineString([start, end])
        for passage in passages:
            if edge.distance(passage) <= 1e-6:
                edge = edge.difference(passage)
        parts = list(edge.geoms) if isinstance(edge, MultiLineString) else [edge]
        for part in parts:
            if isinstance(part, LineString) and part.length > 1e-6:
                x, y = part.xy
                ax.plot(x, y, color=color, linewidth=linewidth, zorder=zorder)


def _room_label_anchor(
    exterior: list[Tuple[float, float]],
    center: Tuple[float, float],
    avoid_points: list[Tuple[float, float]],
    cable_lines: list[LineString],
    scale: float,
) -> Tuple[float, float]:
    """Move labels off hubs, nodes, and cable routes when the room allows."""
    if not exterior:
        return center
    boundary = Polygon(exterior)
    safe_area = boundary.buffer(-max(1.0, 0.25 * scale))
    center_point = Point(center)
    avoid_geometries = [Point(point) for point in avoid_points] + cable_lines
    if not avoid_geometries or min(center_point.distance(g) for g in avoid_geometries) >= 0.75 * scale:
        return center

    min_x, min_y, max_x, max_y = boundary.bounds
    candidates = []
    for fx in (0.25, 0.5, 0.75):
        for fy in (0.15, 0.5, 0.85):
            point = Point(min_x + fx * (max_x - min_x), min_y + fy * (max_y - min_y))
            if safe_area.covers(point):
                clearance = min(point.distance(g) for g in avoid_geometries)
                candidates.append((clearance, (point.x, point.y)))
    return max(candidates, default=(0.0, center), key=lambda candidate: candidate[0])[1]


def render_input_plan(
    plan: Dict[str, Any], figsize: Tuple[int, int] = (12, 10), dpi: int = 200
) -> plt.Figure:
    """Show the normalized floor plan before hub placement and cable routing."""
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_aspect("equal")
    open_passages = _open_passage_lines(plan)

    for room in plan.get("rooms", []):
        exterior = [(p["x"], p["y"]) for p in room["geometry"]["exterior"]]
        if not exterior:
            continue
        color = ROOM_TYPE_COLORS.get(room.get("kind", "other"), ROOM_TYPE_COLORS["other"])
        ax.add_patch(MplPolygon(exterior, closed=True, facecolor=color, edgecolor="none", alpha=0.5))
        _draw_room_outline(ax, exterior, open_passages, color="#6C757D", linewidth=1.0)
        cx = sum(p[0] for p in exterior) / len(exterior)
        cy = sum(p[1] for p in exterior) / len(exterior)
        ax.text(cx, cy, room["id"], ha="center", va="center", fontsize=8)

    boundary = plan.get("internal_boundary", {})
    exterior = [(p["x"], p["y"]) for p in boundary.get("exterior", [])]
    if exterior:
        ax.add_patch(MplPolygon(exterior, closed=True, fill=False, edgecolor="#1B263B", linewidth=2.5, linestyle="--"))

    for obstacle in plan.get("obstacles", []):
        geometry = obstacle.get("geometry")
        color = "#00B4D8" if obstacle.get("kind") == "window" else "#0D1B2A"
        if isinstance(geometry, list):
            ax.plot([p["x"] for p in geometry], [p["y"] for p in geometry], color=color, linewidth=3)
        elif isinstance(geometry, dict):
            points = geometry.get("exterior", [])
            if points:
                ax.add_patch(MplPolygon([(p["x"], p["y"]) for p in points], closed=True, facecolor=color, alpha=0.5))

    for portal in plan.get("portals", []):
        points = portal.get("segment", [])
        if len(points) >= 2 and portal.get("kind", "door") == "door":
            ax.plot([p["x"] for p in points], [p["y"] for p in points], color="#06D6A0", linewidth=4)

    for node in plan.get("nodes", []):
        point = node["point"]
        ax.scatter(point["x"], point["y"], s=140, color="#FFB703", edgecolor="#D48B00", zorder=5)
        ax.text(point["x"] + 1.5, point["y"] - 2.2, node["id"], fontsize=8, zorder=6)

    _add_floorplan_legend(ax, plan)

    ax.set_title(f"Plan: {plan.get('id', 'N/A')} — Normalized Input", fontsize=12, weight="bold", pad=12)
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.relim()
    ax.autoscale_view()
    return fig


def render_solution_overlay(
    plan: Dict[str, Any],
    solution: Dict[str, Any],
    report: ValidationReport,
    output_path: Optional[str] = None,
    figsize: Tuple[int, int] = (12, 10),
    dpi: int = 200,
) -> plt.Figure:
    """
    Render a high-fidelity visual overlay of the floor plan, assignments,
    cable routes, and independent metrics.
    Guaranteed to display metrics derived directly from validation.
    """
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_aspect("equal")
    open_passages = _open_passage_lines(plan)

    # Map assignments: room_id -> hub_id
    room_to_hub: Dict[str, str] = {}
    for a in solution.get("assignments", []):
        room_to_hub[a["room_id"]] = a["hub_id"]

    hubs = solution.get("hubs", [])
    hub_ids = [h["id"] for h in hubs]
    hub_color_map = {
        h_id: TERRITORY_COLORS[i % len(TERRITORY_COLORS)]
        for i, h_id in enumerate(hub_ids)
    }
    hub_fill_map = {
        h_id: TERRITORY_FILL_COLORS[i % len(TERRITORY_FILL_COLORS)]
        for i, h_id in enumerate(hub_ids)
    }
    node_to_hub = {
        assignment["node_id"]: assignment["hub_id"]
        for assignment in solution.get("assignments", [])
    }
    node_labels = {
        node["id"]: f"N{index + 1}"
        for index, node in enumerate(sorted(plan.get("nodes", []), key=lambda item: item["id"]))
    }
    rooms_by_kind: Dict[str, list[Dict[str, Any]]] = {}
    for item in sorted(plan.get("rooms", []), key=lambda value: value["id"]):
        rooms_by_kind.setdefault(item.get("kind", "room"), []).append(item)
    room_labels = {
        item["id"]: (
            f"{item.get('kind', 'Room').title()} {index + 1}"
            if len(rooms_by_kind[item.get("kind", "room")]) > 1
            else item.get("kind", "Room").title()
        )
        for group in rooms_by_kind.values()
        for index, item in enumerate(group)
    }
    cable_lines = [
        LineString([(float(p["x"]), float(p["y"])) for p in leg.get("polyline", [])])
        for ring in solution.get("rings", [])
        for leg in ring.get("legs", [])
        if len(leg.get("polyline", [])) >= 2
    ]
    symbol_points = [
        (float(item["point"]["x"]), float(item["point"]["y"]))
        for item in [*hubs, *plan.get("nodes", [])]
    ]

    # 1. Draw Rooms
    for room in plan.get("rooms", []):
        r_id = room.get("id")
        eligible = room.get("eligible", False)
        kind = room.get("kind", "room")
        poly_data = room.get("geometry", {})
        exterior = [(p["x"], p["y"]) for p in poly_data.get("exterior", [])]

        if not exterior:
            continue

        assigned_hub = room_to_hub.get(r_id)
        face_color = hub_fill_map.get(assigned_hub, "#E1E4E8")
        edge_width = 2.0 if eligible else 1.5
        alpha = 0.88 if eligible else 0.62
        patch = MplPolygon(exterior, closed=True, facecolor=face_color, edgecolor="none", linewidth=0, alpha=alpha)
        ax.add_patch(patch)
        _draw_room_outline(ax, exterior, open_passages, color="#3B424A", linewidth=edge_width)

        # Room label centroid
        xs = [p[0] for p in exterior]
        ys = [p[1] for p in exterior]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        cx, cy = _room_label_anchor(
            exterior, (cx, cy), symbol_points, cable_lines,
            float(plan.get("drawing_units_per_metre", 1.0)),
        )
        area_m2 = room.get("area_m2", 0.0)
        label_text = f"{room_labels.get(r_id, kind.title())}\n{area_m2:.1f} m²"
        ax.text(cx, cy, label_text, ha="center", va="center", fontsize=7.5, color="#20252B",
                weight="semibold", alpha=1, zorder=3,
                bbox=dict(boxstyle="round,pad=0.28", facecolor="white", edgecolor="none", alpha=0.72))

    # 2. Draw Internal Boundary
    boundary_data = plan.get("internal_boundary", {})
    b_exterior = [(p["x"], p["y"]) for p in boundary_data.get("exterior", [])]
    if b_exterior:
        b_patch = MplPolygon(b_exterior, closed=True, fill=False, edgecolor="#1B263B", linewidth=2.5, linestyle="--")
        ax.add_patch(b_patch)

    # 3. Mark verified portals. Open passages use a faint dashed centre line
    # along free space; unlike doors, the line does not imply a narrow opening.
    for portal in plan.get("portals", []):
        pts = [(p["x"], p["y"]) for p in portal.get("segment", [])]
        if len(pts) >= 2 and portal.get("kind") == "open_passage":
            px = [pts[0][0], pts[1][0]]
            py = [pts[0][1], pts[1][1]]
            ax.plot(px, py, color="#118AB2", linewidth=9.0, alpha=0.16,
                    solid_capstyle="butt", zorder=3)
            ax.plot(px, py, color="#118AB2", linewidth=1.2,
                    linestyle=(0, (4, 3)), alpha=0.85,
                    solid_capstyle="butt", zorder=4)
        elif len(pts) >= 2 and portal.get("kind", "door") == "door":
            px = [pts[0][0], pts[1][0]]
            py = [pts[0][1], pts[1][1]]
            ax.plot(px, py, color="#06D6A0", linewidth=5.0, solid_capstyle="butt", zorder=4)

    # 4. Draw Obstacles (Walls, Windows)
    for obs in plan.get("obstacles", []):
        geom_data = obs.get("geometry")
        kind = obs.get("kind", "wall")
        obs_color = "#0D1B2A" if kind == "wall" else "#00B4D8" if kind == "window" else "#495057"
        if isinstance(geom_data, list):
            ox = [p["x"] for p in geom_data]
            oy = [p["y"] for p in geom_data]
            ax.plot(ox, oy, color=obs_color, linewidth=3.2, solid_capstyle="round", zorder=7)
        elif isinstance(geom_data, dict) and "exterior" in geom_data:
            o_ext = [(p["x"], p["y"]) for p in geom_data.get("exterior", [])]
            o_patch = MplPolygon(o_ext, closed=True, facecolor=obs_color, edgecolor=obs_color, linewidth=1.5, alpha=0.72, zorder=7)
            ax.add_patch(o_patch)

    rings = solution.get("rings", [])
    shared_cable_spans = _shared_cable_spans(
        rings, float(plan.get("drawing_units_per_metre", 1.0))
    )

    # 5. Draw Cable Rings
    for ring in rings:
        r_hub_id = ring.get("hub_id")
        cable_color = hub_color_map.get(r_hub_id, "#E63946")
        legs = ring.get("legs", [])

        for leg_idx, leg in enumerate(legs):
            pts = [(float(p["x"]), float(p["y"])) for p in leg.get("polyline", [])]
            if len(pts) < 2:
                continue

            lx = [p[0] for p in pts]
            ly = [p[1] for p in pts]

            # Route polyline: contrasting white casing + vibrant core cable
            ax.plot(lx, ly, color="white", linewidth=4.2, alpha=1, zorder=5, solid_capstyle="round", solid_joinstyle="round")
            ax.plot(lx, ly, color=cable_color, linewidth=2.2, alpha=1, zorder=6, solid_capstyle="round", solid_joinstyle="round")

            # Find longest segment to host sequence badge
            longest_seg_idx = 0
            max_seg_len = 0.0

            # Draw directional arrows along segments
            for s in range(len(pts) - 1):
                p1, p2 = pts[s], pts[s + 1]
                mid_x = (p1[0] + p2[0]) / 2.0
                mid_y = (p1[1] + p2[1]) / 2.0
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                dist = math.hypot(dx, dy)
                if dist > max_seg_len:
                    max_seg_len = dist
                    longest_seg_idx = s

                if dist > 3.0:
                    ax.annotate(
                        "",
                        xy=(mid_x + dx * 0.12, mid_y + dy * 0.12),
                        xytext=(mid_x - dx * 0.12, mid_y - dy * 0.12),
                        arrowprops=dict(arrowstyle="->", color=cable_color, lw=2.2, mutation_scale=13),
                        zorder=7,
                    )

            # Draw leg sequence badge [1], [2], ... on longest segment
            if max_seg_len > 2.0:
                p1, p2 = pts[longest_seg_idx], pts[longest_seg_idx + 1]
                badge_x = (p1[0] + p2[0]) / 2.0
                badge_y = (p1[1] + p2[1]) / 2.0
                # Slight perpendicular offset for readability
                nx = -(p2[1] - p1[1]) / max_seg_len
                ny = (p2[0] - p1[0]) / max_seg_len
                bx = badge_x + nx * 1.5
                by = badge_y + ny * 1.5
                ax.annotate(
                    f"{leg_idx + 1}", xy=(bx, by), xytext=(0, 0), textcoords="offset points",
                    fontsize=7.5, weight="bold", color=cable_color, ha="center", va="center",
                    bbox=dict(boxstyle="circle,pad=0.25", facecolor="white", edgecolor=cable_color, lw=1.4),
                    zorder=8,
                )

    # Shared runs are retraced cable, so explicitly show both directions.
    # Parallel runs on distinct lines never reach this layer.
    for axis, fixed, lo, hi in shared_cable_spans:
        if axis == "h":
            start, end = (lo, fixed), (hi, fixed)
        else:
            start, end = (fixed, lo), (fixed, hi)
        ax.annotate(
            "", xy=end, xytext=start,
            arrowprops=dict(
                arrowstyle="<->", color="#17212B", lw=1.7,
                mutation_scale=13, shrinkA=1.5, shrinkB=1.5,
            ),
            zorder=9,
        )

    # 6. Draw Fixed Nodes
    for node in plan.get("nodes", []):
        n_id = node.get("id")
        nx_val = float(node["point"]["x"])
        ny_val = float(node["point"]["y"])
        node_label = node_labels.get(n_id, n_id)

        node_color = hub_color_map.get(node_to_hub.get(n_id), "#2468B4")
        ax.scatter(nx_val, ny_val, s=180, color=node_color, edgecolor="white", linewidth=1.8, zorder=10)
        ax.annotate(
            node_label, xy=(nx_val, ny_val), xytext=(8, -10), textcoords="offset points",
            fontsize=8, weight="bold", color="#1F2421",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=node_color, alpha=0.96),
            ha="left", va="top",
            path_effects=[pe.withStroke(linewidth=3, foreground="white")],
            zorder=11,
        )

    # 7. Draw Selected Hubs
    fixed_node_points = [
        (float(node["point"]["x"]), float(node["point"]["y"]))
        for node in plan.get("nodes", [])
    ]
    for hub in hubs:
        h_id = hub.get("id")
        hx_val = float(hub["point"]["x"])
        hy_val = float(hub["point"]["y"])
        h_color = hub_color_map.get(h_id, "#E63946")
        hub_size = float(plan.get("drawing_units_per_metre", 1.0))
        hub_width, hub_height = 0.82 * hub_size, 0.55 * hub_size
        nearest_node = min(
            fixed_node_points,
            key=lambda point: math.dist(point, (hx_val, hy_val)),
            default=None,
        )
        overlaps_node = (
            nearest_node is not None
            and math.dist(nearest_node, (hx_val, hy_val)) < 1.0 * hub_size
        )
        hub_label = f"H{hub_ids.index(h_id) + 1}"
        if overlaps_node:
            # Keep the true hub point visible, but move its rectangular label
            # aside with a leader so it cannot hide the short ring loop.
            ax.scatter(
                hx_val, hy_val, s=34, marker="s", color=h_color,
                edgecolor="white", linewidth=1.1, zorder=12,
            )
            dx = hx_val - nearest_node[0]
            dy = hy_val - nearest_node[1]
            norm = math.hypot(dx, dy)
            if norm < 1e-6:
                label_offset = (-28, 18)
            else:
                label_offset = (28 * dx / norm, 28 * dy / norm)
            ax.annotate(
                hub_label, xy=(hx_val, hy_val), xytext=label_offset,
                textcoords="offset points", fontsize=9, weight="bold",
                color="white", ha="center", va="center",
                bbox=dict(boxstyle="square,pad=0.3", facecolor=h_color,
                          edgecolor="white", linewidth=1.5),
                arrowprops=dict(arrowstyle="-", color=h_color, linewidth=1.2,
                                shrinkA=3, shrinkB=4),
                zorder=13,
            )
            continue
        ax.add_patch(Rectangle(
            (hx_val - hub_width / 2, hy_val - hub_height / 2),
            hub_width, hub_height, facecolor=h_color, edgecolor="white",
            linewidth=1.8, zorder=12,
        ))
        ax.annotate(
            hub_label, xy=(hx_val, hy_val),
            fontsize=9, weight="bold", color="white",
            ha="center", va="center",
            zorder=13,
        )

    # 8. Recomputed Metrics Badge (Upper Left)
    status_str = "VALID (PASSED)" if report.is_valid else f"INVALID ({len(report.violations)} VIOLATIONS)"
    status_color = "#06D6A0" if report.is_valid else "#E63946"

    m = report.recomputed_metrics
    if m:
        metrics_text = (
            f"Validation Status: {status_str}\n"
            f"-------------------------------------\n"
            f"Hub Count (H): {m.hub_count}\n"
            f"Total Length (L): {m.length_m:.2f} m\n"
            f"Crossings (X): {m.crossings}\n"
            f"Collinear Overlap (O): {m.overlap_m:.2f} m\n"
            f"Ring Bends (B): {m.bends}\n"
            f"Route Cost (J): {m.route_cost:.2f}\n"
            f"Area Gap: {m.area_gap_m2:.2f} m²"
        )
    else:
        metrics_text = f"Status: {status_str}"

    ax.text(
        0.02, 0.98, metrics_text,
        transform=ax.transAxes,
        fontsize=9,
        family="monospace",
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="white", edgecolor=status_color, linewidth=2.2, alpha=0.95),
        zorder=20,
    )

    ax.set_title(f"Plan: {plan.get('id', 'N/A')} — Cable Routing Verification Overlay", fontsize=12, weight="bold", pad=12)
    ax.grid(True, linestyle=":", alpha=0.4)
    _add_floorplan_legend(ax, plan, hub_color_map, hub_fill_map)

    if output_path:
        fig.savefig(output_path, bbox_inches="tight")

    return fig


def _add_floorplan_legend(
    ax: Any,
    plan: Dict[str, Any],
    hub_colors: Optional[Dict[str, str]] = None,
    hub_fills: Optional[Dict[str, str]] = None,
) -> None:
    """Show territory colors, obstacles, and portals."""
    handles = []
    if hub_colors:
        handles.extend(
            Patch(
                facecolor=(hub_fills or {}).get(hub_id, "#E1E4E8"),
                edgecolor=color,
                label=f"Territory H{index + 1}",
            )
            for index, (hub_id, color) in enumerate(hub_colors.items())
        )
        if any(not room.get("eligible", False) for room in plan.get("rooms", [])):
            handles.append(Patch(facecolor="#E1E4E8", edgecolor="#3B424A", label="No node / excluded"))
    else:
        kinds = sorted({room.get("kind", "other") for room in plan.get("rooms", [])})
        handles.extend(Patch(facecolor=ROOM_TYPE_COLORS.get(kind, ROOM_TYPE_COLORS["other"]),
                             edgecolor="#6C757D", label=f"Room: {kind}") for kind in kinds)
    for kind in sorted({item.get("kind", "wall") for item in plan.get("obstacles", [])}):
        color = "#17212B" if kind == "wall" else "#00A6C7" if kind == "window" else "#495057"
        handles.append(Line2D([0], [0], color=color, lw=3, label=kind.title()))
    portal_kinds = {item.get("kind", "door") for item in plan.get("portals", [])}
    if "open_passage" in portal_kinds:
        handles.append(Line2D([0], [0], color="#118AB2", lw=1.4,
                              linestyle=(0, (4, 3)), label="Open Passage (free space)"))
    if "door" in portal_kinds:
        handles.append(Line2D([0], [0], color="#06D6A0", lw=4, label="Door"))
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=7.5, framealpha=0.96,
                  title="Floor plan key", title_fontsize=8)
