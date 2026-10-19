"""Build the checked PS4 report and combined dataset ZIP."""

from __future__ import annotations

from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import shutil
from zipfile import ZIP_DEFLATED, ZIP_LZMA, ZipFile, ZipInfo

import matplotlib.pyplot as plt
from PIL import Image as PillowImage, ImageOps
from jsonschema import Draft202012Validator
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, PageBreak, PageTemplate,
    Paragraph, Spacer,
)

from cable_planner.solver.comparison import solve_with_comparison
from cable_planner.validation import IndependentValidator
from cable_planner.visualization.renderer import render_input_plan, render_solution_overlay


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "submission"
ASSETS = SOURCE / "assets"
OUT_DIR = ROOT / "submission"
PDF = SOURCE / "npminstallregrets_PS4_report.pdf"
ZIP = OUT_DIR / "npminstallregrets_PS4.zip"
SCHEMA = ROOT / "shared" / "schema" / "common.schema.json"
DATASET_FILES = (
    "ResPlan.pkl", "split.json", "croissant.json", "LICENSE", "README.md",
    "requirements.txt", "ResPlan_demo.ipynb", "resplan_utils.py", "TAKEDOWN.md",
)


def checked_bundle(plan_id: int, validator: Draft202012Validator):
    path = ROOT / "examples" / "outputs" / f"kaggle_{plan_id}_combined.json"
    bundle = json.loads(path.read_text(encoding="utf-8"))
    validator.validate(bundle)
    report = IndependentValidator().validate(bundle["plan"], bundle["solution"])
    if not report.is_valid or report.recomputed_metrics is None:
        raise ValueError(f"Saved example {plan_id} failed independent validation")
    return bundle, report


def figure(path: Path, render):
    fig = render()
    fig.savefig(path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def pair(first: Path, second: Path, output: Path):
    images = []
    for path in (first, second):
        with PillowImage.open(path) as opened:
            image = opened.convert("RGB")
            image.thumbnail((1400, 1050), PillowImage.Resampling.LANCZOS)
            images.append(ImageOps.pad(image, (1400, 1050), color="white"))
    canvas = PillowImage.new("RGB", (2880, 1160), "#f2f5fa")
    canvas.paste(images[0], (20, 90))
    canvas.paste(images[1], (1460, 90))
    # The renderer titles identify each image; the captions in report.md give context.
    canvas.save(output, optimize=True)


def inline_markup(value: str) -> str:
    value = escape(value)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#0b5d94">\1</link>', value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", r'<font color="#245c73">\1</font>', value)
    return value.replace("  \n", "<br/>")


def page_chrome(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(colors.HexColor("#0e273a"))
    canvas.rect(0, height - 11, width, 11, fill=1, stroke=0)
    canvas.setStrokeColor(colors.HexColor("#d9e3eb"))
    canvas.line(42, 40, width - 42, 40)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#567083"))
    canvas.drawString(42, 27, "HACKHIVE 2026  /  HONEYWELL PS4  /  npminstallregrets")
    canvas.drawRightString(width - 42, 27, f"{doc.page}")
    canvas.restoreState()


def build_pdf():
    width, height = A4
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverKicker", fontName="Helvetica-Bold", fontSize=10, leading=14,
                              textColor=colors.HexColor("#247b91"), spaceAfter=12))
    styles.add(ParagraphStyle(name="CoverTitle", fontName="Helvetica-Bold", fontSize=27, leading=31,
                              textColor=colors.HexColor("#0e273a"), spaceAfter=16))
    styles.add(ParagraphStyle(name="SectionTitlePS4", fontName="Helvetica-Bold", fontSize=15.5, leading=19,
                              textColor=colors.HexColor("#0e273a"), spaceBefore=13, spaceAfter=9,
                              keepWithNext=True))
    styles.add(ParagraphStyle(name="BodyPS4", fontName="Helvetica", fontSize=9, leading=12.8,
                              textColor=colors.HexColor("#233a49"), spaceAfter=7))
    styles.add(ParagraphStyle(name="CaptionPS4", fontName="Helvetica-Oblique", fontSize=8,
                              leading=11, textColor=colors.HexColor("#536d80"), spaceBefore=5,
                              spaceAfter=8))
    story = []
    lines = (SOURCE / "report.md").read_text(encoding="utf-8").splitlines()
    paragraph = []

    def flush():
        if paragraph:
            story.append(Paragraph(inline_markup(" ".join(paragraph)), styles["BodyPS4"]))
            paragraph.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped == "---":
            flush()
            story.append(PageBreak())
        elif stripped.startswith("# "):
            flush()
            story.append(Paragraph(inline_markup(stripped[2:]), styles["CoverKicker"]))
        elif stripped.startswith("## "):
            flush()
            style = styles["CoverTitle"] if stripped == "## Cable Ring Planner" else styles["SectionTitlePS4"]
            story.append(Paragraph(inline_markup(stripped[3:]), style))
        elif stripped.startswith("!["):
            flush()
            match = re.fullmatch(r"!\[(.+)\]\(([^)]+)\)", stripped)
            if not match:
                raise ValueError(f"Unsupported image markup: {line}")
            caption, relative = match.groups()
            path = SOURCE / relative
            reader = ImageReader(str(path))
            px_width, px_height = reader.getSize()
            max_width, max_height = width - 90, 330
            scale = min(max_width / px_width, max_height / px_height)
            block = [Image(str(path), width=px_width * scale, height=px_height * scale),
                     Paragraph(escape(caption), styles["CaptionPS4"])]
            story.append(KeepTogether(block))
        elif stripped.startswith("- "):
            flush()
            story.append(Paragraph("&#8226; " + inline_markup(stripped[2:]), styles["BodyPS4"]))
        else:
            paragraph.append(stripped)
    flush()

    doc = BaseDocTemplate(str(PDF), pagesize=A4, leftMargin=45, rightMargin=45,
                          topMargin=40, bottomMargin=55,
                          title="HackHive 2026 - Honeywell PS4 Cable Ring Planner",
                          author="Team npminstallregrets")
    frame = Frame(45, 55, width - 90, height - 95, leftPadding=0,
                  rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id="normal", frames=[frame], onPage=page_chrome))
    doc.build(story)


def add_to_zip(archive: ZipFile, source: Path, target: str):
    info = ZipInfo(target, date_time=(2026, 10, 19, 0, 0, 0))
    info.compress_type = ZIP_LZMA if target == "archive/ResPlan.pkl" else ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    with source.open("rb") as input_file, archive.open(info, "w") as output_file:
        shutil.copyfileobj(input_file, output_file, length=1024 * 1024)


def digest(stream):
    checksum = sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        checksum.update(chunk)
    return checksum.digest()


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    bundles = {}
    reports = {}
    for plan_id in (12014, 8063, 4944):
        bundles[plan_id], reports[plan_id] = checked_bundle(plan_id, validator)
    if any(node["source"] != "development_fallback" for bundle in bundles.values()
           for node in bundle["plan"]["nodes"]):
        raise ValueError("Report fallback-node statement does not match examples")
    expected = {12014: 22.4604, 8063: 34.7645, 4944: 45.0814}
    for plan_id, value in expected.items():
        actual = reports[plan_id].recomputed_metrics.route_cost
        if abs(actual - value) > 0.0001:
            raise ValueError(f"Stale report metric for {plan_id}: {actual}")

    comparison = solve_with_comparison(bundles[4944]["plan"])
    if not comparison.selected_report.is_valid or comparison.alternative is None or comparison.alternative_report is None:
        raise ValueError("No independently checked 4944 comparison available")
    selected_cost = comparison.selected_report.recomputed_metrics.route_cost
    alternate_cost = comparison.alternative_report.recomputed_metrics.route_cost
    if abs(selected_cost - 45.0814) > 0.0001 or abs(alternate_cost - 48.4531) > 0.0001:
        raise ValueError(f"4944 comparison changed: {selected_cost}, {alternate_cost}")
    expected_comparison = (
        (comparison.selected_report.recomputed_metrics, 30.4697, 1, 1.1117, 17),
        (comparison.alternative_report.recomputed_metrics, 38.4531, 0, 0.0, 20),
    )
    for metrics, length, crossings, overlap, bends in expected_comparison:
        if (abs(metrics.length_m - length) > 0.0001 or metrics.crossings != crossings
                or abs(metrics.overlap_m - overlap) > 0.0001 or metrics.bends != bends):
            raise ValueError(f"4944 report detail changed: {metrics}")
    selected_bundle = {"schema_version": "0.1.0", "plan": bundles[4944]["plan"],
                       "solution": comparison.selected}
    alternate_bundle = {"schema_version": "0.1.0", "plan": bundles[4944]["plan"],
                        "solution": comparison.alternative}
    validator.validate(selected_bundle)
    validator.validate(alternate_bundle)

    figure(ASSETS / "plan_12014_input.png", lambda: render_input_plan(bundles[12014]["plan"]))
    figure(ASSETS / "plan_12014_checked.png", lambda: render_solution_overlay(
        bundles[12014]["plan"], bundles[12014]["solution"], reports[12014]))
    figure(ASSETS / "plan_4944_input.png", lambda: render_input_plan(bundles[4944]["plan"]))
    figure(ASSETS / "plan_4944_selected.png", lambda: render_solution_overlay(
        bundles[4944]["plan"], comparison.selected, comparison.selected_report))
    figure(ASSETS / "plan_4944_clean.png", lambda: render_solution_overlay(
        bundles[4944]["plan"], comparison.alternative, comparison.alternative_report))
    pair(ASSETS / "plan_12014_input.png", ASSETS / "plan_12014_checked.png",
         ASSETS / "plan_12014_pair.png")
    pair(ASSETS / "plan_4944_selected.png", ASSETS / "plan_4944_clean.png",
         ASSETS / "plan_4944_pair.png")
    build_pdf()

    selected_path = SOURCE / "example_4944_selected.json"
    selected_path.write_text(json.dumps(selected_bundle, indent=2) + "\n", encoding="utf-8")
    alternate_path = SOURCE / "example_4944_zero_crossings.json"
    alternate_path.write_text(json.dumps(alternate_bundle, indent=2) + "\n", encoding="utf-8")
    entries = {
        "README.md": SOURCE / "README.md",
        "REPORT.pdf": PDF,
        "REPORT_SOURCE.md": SOURCE / "report.md",
        "DATASET.md": SOURCE / "DATASET.md",
        "REPRODUCE.md": SOURCE / "REPRODUCE.md",
        "schema/common.schema.json": SCHEMA,
        "examples/plan_12014_checked.json": ROOT / "examples/outputs/kaggle_12014_combined.json",
        "examples/plan_8063_checked.json": ROOT / "examples/outputs/kaggle_8063_combined.json",
        "examples/plan_4944_selected.json": selected_path,
        "examples/plan_4944_zero_crossings.json": alternate_path,
    }
    entries.update({f"images/{path.name}": path for path in sorted(ASSETS.glob("*.png"))})
    dataset_dir = next(
        (path for path in (ROOT / "archive", ROOT.parent / "archive")
         if (path / "ResPlan.pkl").is_file()),
        None,
    )
    if dataset_dir is None:
        raise FileNotFoundError("Trusted ResPlan archive folder not found")
    for name in DATASET_FILES:
        source = dataset_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"Missing supplied dataset file: {source}")
        entries[f"archive/{name}"] = source
    manifest = ["# Package contents", "", "Team npminstallregrets | Honeywell PS4", "",
                "The supplied ResPlan source files are included under `archive/`.", "",
                "| Path | SHA-256 |", "| --- | --- |"]
    for target, source in sorted(entries.items()):
        with source.open("rb") as input_file:
            manifest.append(f"| `{target}` | `{digest(input_file).hex()}` |")
    manifest_path = SOURCE / "MANIFEST.md"
    manifest_path.write_text("\n".join(manifest) + "\n", encoding="utf-8")
    entries["MANIFEST.md"] = manifest_path
    with ZipFile(ZIP, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for target, source in sorted(entries.items()):
            add_to_zip(archive, source, target)
    with ZipFile(ZIP) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(entries):
            raise ValueError("ZIP integrity or inventory check failed")
        for target, source in entries.items():
            with archive.open(target) as packed_file, source.open("rb") as input_file:
                if digest(packed_file) != digest(input_file):
                    raise ValueError(f"ZIP checksum mismatch: {target}")
        for target in (name for name in entries if name.startswith("examples/")):
            bundle = json.loads(archive.read(target))
            validator.validate(bundle)
            if not IndependentValidator().validate(bundle["plan"], bundle["solution"]).is_valid:
                raise ValueError(f"ZIP example failed independent validation: {target}")
    print(f"Built {PDF} ({PDF.stat().st_size:,} bytes)")
    print(f"Built {ZIP} ({ZIP.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
