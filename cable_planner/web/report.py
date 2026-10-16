"""PDF report generation for a completed, independently checked run."""

from __future__ import annotations

import base64
import io
import json
import textwrap
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


INK = colors.HexColor("#171717")
CORAL = colors.HexColor("#ff604d")
BONE = colors.HexColor("#f5efdf")
MUTED = colors.HexColor("#6c665b")


def _image_bytes(data_uri: Any) -> bytes | None:
    if data_uri is None:
        return None
    if not isinstance(data_uri, str) or not data_uri.startswith("data:image/png;base64,"):
        raise ValueError("Report images must be PNG data URIs from a completed run.")
    try:
        payload = base64.b64decode(data_uri.split(",", 1)[1], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("A report image is not valid base64 data.") from exc
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("A report image is not a valid PNG.")
    return payload


def _json_pretty(value: Any, width: int = 112) -> str:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)
    lines: list[str] = []
    for line in rendered.splitlines():
        if len(line) <= width:
            lines.append(line)
            continue
        # Preserve readable JSON indentation while ensuring a long string or
        # list line cannot run into the page margin.
        indent = len(line) - len(line.lstrip())
        lines.extend(textwrap.wrap(line, width=width, subsequent_indent=" " * min(indent + 2, 20),
                                   break_long_words=True, break_on_hyphens=False))
    return "\n".join(lines)


def _on_page(canvas, document) -> None:
    canvas.saveState()
    width, _ = letter
    canvas.setStrokeColor(colors.HexColor("#d8cfba"))
    canvas.setLineWidth(0.5)
    canvas.line(document.leftMargin, 0.55 * inch, width - document.rightMargin, 0.55 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(document.leftMargin, 0.36 * inch, "CABLE RING STUDIO · FLOOR PLAN REPORT")
    canvas.drawRightString(width - document.rightMargin, 0.36 * inch, f"PAGE {document.page}")
    canvas.restoreState()


def build_pdf_report(result: dict[str, Any]) -> bytes:
    """Build a self-contained PDF report from the public completed-run payload."""
    if not isinstance(result, dict):
        raise ValueError("A completed run result is required.")
    plan_id = result.get("plan_id", "unknown")
    development = result.get("development")
    if not isinstance(development, dict):
        raise ValueError("The run is missing its development Plan and Solution JSON.")
    input_png = _image_bytes(result.get("input_image"))
    output_png = _image_bytes(result.get("output_image"))

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Times-Bold",
                              fontSize=26, leading=30, textColor=INK, alignment=TA_LEFT, spaceAfter=9))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
                              fontSize=18, leading=22, textColor=INK, spaceAfter=12))
    styles.add(ParagraphStyle(name="SubTitle", parent=styles["Heading2"], fontName="Helvetica-Bold",
                              fontSize=11, leading=14, textColor=INK, spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontSize=9, leading=13,
                              textColor=MUTED, spaceAfter=5))
    styles.add(ParagraphStyle(name="Json", fontName="Courier", fontSize=6.2, leading=7.4,
                              textColor=INK, leftIndent=0, rightIndent=0, spaceAfter=0))
    styles.add(ParagraphStyle(name="Label", parent=styles["BodyText"], fontName="Helvetica-Bold",
                              fontSize=8, leading=10, textColor=MUTED))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.68 * inch, leftMargin=0.68 * inch,
                            topMargin=0.68 * inch, bottomMargin=0.78 * inch,
                            title=f"Floor plan {plan_id} report", author="Cable Ring Studio")
    story: list[Any] = []

    story.extend([
        Paragraph("CABLE RING STUDIO&nbsp;&nbsp; / &nbsp;&nbsp;CHECKED RUN", styles["Label"]),
        Spacer(1, 0.18 * inch),
        Paragraph(f"Floor plan {plan_id}", styles["ReportTitle"]),
        Paragraph("Complete run record: source plan, checked output, metrics, diagnostics, and machine-readable exports.", styles["BodySmall"]),
        Spacer(1, 0.1 * inch),
    ])

    validation = result.get("validation") or {}
    metrics = validation.get("recomputed_metrics") or {}
    timings = result.get("timings") or {}
    status = str(result.get("status", "unknown")).replace("_", " ").upper()
    validity = "PASSED" if validation.get("is_valid") else "FAILED"
    summary_rows = [
        ["PLAN", str(plan_id), "SOURCE", str(result.get("source", "unknown")).upper()],
        ["SOLVER STATUS", status, "INDEPENDENT CHECK", validity],
        ["HUBS", str(metrics.get("hub_count", "—")), "LOWER BOUND", str(result.get("lower_bound_hubs", "—"))],
        ["ROUTE COST · J", _fmt(metrics.get("route_cost")), "TOTAL LENGTH", f"{_fmt(metrics.get('length_m'))} m"],
        ["CROSSINGS", str(metrics.get("crossings", "—")), "BENDS", str(metrics.get("bends", "—"))],
        ["OVERLAP", f"{_fmt(metrics.get('overlap_m'))} m", "AREA GAP", f"{_fmt(metrics.get('area_gap_m2'))} m²"],
        ["SERVER RUNTIME", f"{_fmt(timings.get('total_s'))} s", "FALLBACK NODES", str(result.get("fallback_nodes", 0))],
    ]
    table = Table(summary_rows, colWidths=[1.25 * inch, 2.05 * inch, 1.35 * inch, 2.0 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BONE),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), MUTED),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d8cfba")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([table, Spacer(1, 0.12 * inch)])

    story.append(Paragraph("Run timings", styles["SubTitle"]))
    timing_rows = [["LOAD", "NORMALIZE", "SOLVE", "VALIDATE", "RENDER + EXPORT"], [
        _seconds(timings.get("load_s")), _seconds(timings.get("normalize_s")),
        _seconds(timings.get("solve_s")), _seconds(timings.get("validate_s")),
        _seconds(timings.get("render_export_s")),
    ]]
    timing_table = Table(timing_rows, colWidths=[1.32 * inch] * 5)
    timing_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("GRID", (0, 0), (-1, -1), .3, colors.white),
    ]))
    story.append(timing_table)
    story.append(Paragraph("Objective: J = L + 5X + O + 0.5B. Metrics above are from the independent checker.", styles["BodySmall"]))

    diagnostics = result.get("diagnostics") or []
    violations = validation.get("violations") or []
    warnings = validation.get("warnings") or []
    story.append(Paragraph("Diagnostics and validation", styles["SectionTitle"]))
    if not diagnostics and not violations and not warnings:
        story.append(Paragraph("No solver diagnostics, validation violations, or warnings were reported.", styles["BodySmall"]))
    for heading, values in (("Solver diagnostics", diagnostics), ("Validation violations", violations), ("Validation warnings", warnings)):
        if values:
            story.append(Paragraph(heading, styles["SubTitle"]))
            for item in values:
                code = str(item.get("code", "diagnostic"))
                message = str(item.get("message", ""))
                ids = item.get("entity_ids") or []
                suffix = f" <font color='#6c665b'>[{', '.join(map(str, ids))}]</font>" if ids else ""
                story.append(Paragraph(f"<b>{_escape(code)}</b> — {_escape(message)}{suffix}", styles["BodySmall"]))

    if input_png:
        story.extend([PageBreak(), Paragraph("Input floor plan", styles["SectionTitle"]),
                      Paragraph("Rendered source geometry used by this run.", styles["BodySmall"]),
                      _fit_image(input_png, doc.width, doc.height - 0.7 * inch)])
    if output_png:
        story.extend([PageBreak(), Paragraph("Checked output", styles["SectionTitle"]),
                      Paragraph("Solver result overlay reviewed by the independent validator.", styles["BodySmall"]),
                      _fit_image(output_png, doc.width, doc.height - 0.7 * inch)])
    else:
        story.extend([PageBreak(), Paragraph("Checked output", styles["SectionTitle"]),
                      Paragraph("No output overlay was produced for this run.", styles["BodySmall"])])

    story.extend([PageBreak(), Paragraph("Development Plan + Solution JSON", styles["SectionTitle"]),
                  Paragraph("Drawing-unit interchange document validated against the shared development schema.", styles["BodySmall"]),
                  Preformatted(_json_pretty(development), styles["Json"])])
    submission = result.get("submission")
    story.extend([PageBreak(), Paragraph("Official submission JSON", styles["SectionTitle"])])
    if submission is None:
        story.append(Paragraph("No submission export was produced because the independent validation did not permit one.", styles["BodySmall"]))
    else:
        story.extend([Paragraph("Metre-based export for the current organizer format.", styles["BodySmall"]),
                      Preformatted(_json_pretty(submission), styles["Json"])])

    architecture = result.get("architecture")
    story.extend([PageBreak(), Paragraph("Architecture and run metadata JSON", styles["SectionTitle"]),
                  Paragraph("Rendering geometry and response metadata associated with this report.", styles["BodySmall"])])
    story.append(Paragraph("Architecture", styles["SubTitle"]))
    story.append(Preformatted(_json_pretty(architecture), styles["Json"]))
    metadata = {key: value for key, value in result.items() if key not in {"input_image", "output_image", "development", "submission", "architecture"}}
    story.extend([Paragraph("Run metadata", styles["SubTitle"]), Preformatted(_json_pretty(metadata), styles["Json"])])

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):,.3f}"
    except (TypeError, ValueError):
        return "—"


def _seconds(value: Any) -> str:
    return "N/A" if value is None else f"{_fmt(value)} s"


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fit_image(data: bytes, max_width: float, max_height: float) -> Image:
    image = Image(io.BytesIO(data))
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    image.hAlign = "CENTER"
    return image
