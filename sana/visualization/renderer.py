"""Visual overlay renderer derived strictly from checked validation and metric data."""

import math
from typing import Any, Dict, Optional, Tuple
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, FancyArrowPatch
import matplotlib.patheffects as pe

from sana.validation.models import ValidationReport


# Distinct, harmonious color palette for territories
TERRITORY_COLORS = [
    "#4361EE",  # Royal Blue
    "#7209B7",  # Purple
    "#3A0CA3",  # Indigo
    "#F72585",  # Pink
    "#4CC9F0",  # Sky Blue
    "#06D6A0",  # Emerald
    "#FFB703",  # Amber
    "#FB8500",  # Orange
]


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
        if assigned_hub and assigned_hub in hub_color_map:
            face_color = hub_color_map[assigned_hub]
            alpha = 0.22
        elif eligible:
            face_color = "#E0E1DD"
            alpha = 0.15
        else:
            face_color = "#D3D3D3"
            alpha = 0.10

        patch = MplPolygon(exterior, closed=True, facecolor=face_color, edgecolor="#6C757D", linewidth=1.2, alpha=alpha)
        ax.add_patch(patch)

        # Room label centroid
        xs = [p[0] for p in exterior]
        ys = [p[1] for p in exterior]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        area_m2 = room.get("area_m2", 0.0)
        label_text = f"{r_id}\n({kind})\n{area_m2:.1f} m²"
        ax.text(cx, cy, label_text, ha="center", va="center", fontsize=8, color="#2B2D42", weight="semibold", alpha=0.85)

    # 2. Draw Internal Boundary
    boundary_data = plan.get("internal_boundary", {})
    b_exterior = [(p["x"], p["y"]) for p in boundary_data.get("exterior", [])]
    if b_exterior:
        b_patch = MplPolygon(b_exterior, closed=True, fill=False, edgecolor="#1B263B", linewidth=2.5, linestyle="--")
        ax.add_patch(b_patch)

    # 3. Draw Portals (Doors / Open Passages)
    for portal in plan.get("portals", []):
        pts = [(p["x"], p["y"]) for p in portal.get("segment", [])]
        if len(pts) >= 2:
            px = [pts[0][0], pts[1][0]]
            py = [pts[0][1], pts[1][1]]
            p_kind = portal.get("kind", "door")
            color = "#06D6A0" if p_kind == "door" else "#118AB2"
            ax.plot(px, py, color=color, linewidth=4.0, solid_capstyle="round", label=f"Portal ({p_kind})")

    # 4. Draw Obstacles (Walls, Windows)
    for obs in plan.get("obstacles", []):
        geom_data = obs.get("geometry")
        kind = obs.get("kind", "wall")
        obs_color = "#0D1B2A" if kind == "wall" else "#00B4D8" if kind == "window" else "#495057"
        if isinstance(geom_data, list):
            ox = [p["x"] for p in geom_data]
            oy = [p["y"] for p in geom_data]
            ax.plot(ox, oy, color=obs_color, linewidth=3.0, solid_capstyle="round")
        elif isinstance(geom_data, dict) and "exterior" in geom_data:
            o_ext = [(p["x"], p["y"]) for p in geom_data.get("exterior", [])]
            o_patch = MplPolygon(o_ext, closed=True, facecolor=obs_color, edgecolor=obs_color, linewidth=1.5, alpha=0.5)
            ax.add_patch(o_patch)

    # 5. Draw Cable Rings
    # Build stop order mapping: entity_id -> stop_index
    stop_order_map: Dict[str, List[int]] = {}
    rings = solution.get("rings", [])
    for ring in rings:
        for idx, s_id in enumerate(ring.get("stop_ids", [])):
            stop_order_map.setdefault(s_id, []).append(idx)

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
            ax.plot(lx, ly, color="white", linewidth=4.8, alpha=0.95, zorder=5, solid_capstyle="round", solid_joinstyle="round")
            ax.plot(lx, ly, color=cable_color, linewidth=2.8, alpha=0.95, zorder=6, solid_capstyle="round", solid_joinstyle="round")

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
                ax.text(
                    bx, by, f"#{leg_idx + 1}",
                    fontsize=7.5, weight="bold", color="white", ha="center", va="center",
                    bbox=dict(boxstyle="circle,pad=0.25", facecolor=cable_color, edgecolor="white", lw=1.2),
                    zorder=8,
                )

    # 6. Draw Fixed Nodes
    for node in plan.get("nodes", []):
        n_id = node.get("id")
        nx_val = float(node["point"]["x"])
        ny_val = float(node["point"]["y"])
        order_list = stop_order_map.get(n_id, [])
        order_str = f" [Stop {order_list[0]}]" if order_list else ""

        ax.scatter(nx_val, ny_val, s=200, color="#FFB703", edgecolor="#D48B00", linewidth=2.2, zorder=10)
        ax.text(
            nx_val + 1.5, ny_val - 2.2, f"{n_id}{order_str}",
            fontsize=8, weight="bold", color="#1F2421",
            path_effects=[pe.withStroke(linewidth=3, foreground="white")],
            zorder=11,
        )

    # 7. Draw Selected Hubs
    for hub in hubs:
        h_id = hub.get("id")
        hx_val = float(hub["point"]["x"])
        hy_val = float(hub["point"]["y"])
        h_color = hub_color_map.get(h_id, "#E63946")
        ax.scatter(hx_val, hy_val, s=360, marker="*", color=h_color, edgecolor="#1B263B", linewidth=2.4, zorder=12)
        ax.text(
            hx_val + 2.0, hy_val + 2.5, f"★ Hub: {h_id} (Loop Start/End)",
            fontsize=9, weight="bold", color=h_color,
            path_effects=[pe.withStroke(linewidth=3.5, foreground="white")],
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

    if output_path:
        fig.savefig(output_path, bbox_inches="tight")

    return fig
