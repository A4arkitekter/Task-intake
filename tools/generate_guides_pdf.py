"""Generér og validér de tre PDF-vejledninger fra Markdown-kilderne."""
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        ListFlowable,
        ListItem,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
except ImportError as exc:  # pragma: no cover - tydelig fejl til PowerShell-scriptet
    raise SystemExit(
        "PDF-afhængigheder mangler. Kør: .venv\\Scripts\\python.exe -m pip install "
        "-r requirements-dev.txt"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT
TEMP_ROOT = ROOT / "tmp" / "pdfs"
GUIDES = (
    ("docs/source/INSTALLATIONSVEJLEDNING.md", "INSTALLATIONSVEJLEDNING.pdf", "INSTALLATION OG OPDATERING"),
    ("docs/source/BRUGERVEJLEDNING.md", "BRUGERVEJLEDNING.pdf", "DAGLIG BRUG"),
)

NAVY = colors.HexColor("#3D2A1F")
BLUE = colors.HexColor("#C45C26")
PALE_BLUE = colors.HexColor("#F3EEE4")
PALE_GRAY = colors.HexColor("#F4F6F8")
MID_GRAY = colors.HexColor("#64748B")
RULE = colors.HexColor("#CBD5E1")


def normalize_text(value: str) -> str:
    """Normalisér tegn, der ofte giver PDF-font- eller kopieringsproblemer."""
    return (
        value.replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u00ad", "")
        .replace("\u00a0", " ")
    )


def register_fonts() -> None:
    candidates = (
        (
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeui.ttf",
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeuib.ttf",
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "consola.ttf",
        ),
    )
    regular, bold, mono = candidates[0]
    missing = [str(path) for path in (regular, bold, mono) if not path.is_file()]
    if missing:
        raise RuntimeError("De krævede Windows-skrifttyper mangler: " + ", ".join(missing))
    pdfmetrics.registerFont(TTFont("GuideSans", str(regular)))
    pdfmetrics.registerFont(TTFont("GuideSansBold", str(bold)))
    pdfmetrics.registerFont(TTFont("GuideMono", str(mono)))
    pdfmetrics.registerFontFamily(
        "GuideSans", normal="GuideSans", bold="GuideSansBold", italic="GuideSans", boldItalic="GuideSansBold"
    )


def inline_markup(value: str) -> str:
    value = normalize_text(value.strip())
    replacements: dict[str, str] = {}

    def hold(fragment: str) -> str:
        key = f"@@PDFTOKEN{len(replacements)}@@"
        replacements[key] = fragment
        return key

    value = re.sub(
        r"`([^`]+)`",
        lambda match: hold(
            '<font name="GuideMono" backColor="#EEF2F6">'
            + html.escape(match.group(1))
            + "</font>"
        ),
        value,
    )
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        lambda match: hold(
            f'<link href="{html.escape(match.group(2), quote=True)}" color="#2D6A9F">'
            f'<u>{html.escape(match.group(1))}</u></link>'
        ),
        value,
    )
    value = re.sub(
        r"<(https?://[^>]+)>",
        lambda match: hold(
            f'<link href="{html.escape(match.group(1), quote=True)}" color="#2D6A9F">'
            f'<u>{html.escape(match.group(1))}</u></link>'
        ),
        value,
    )
    value = html.escape(value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", value)
    for key, fragment in replacements.items():
        value = value.replace(key, fragment)
    return value


def make_styles():
    base = getSampleStyleSheet()
    return {
        "cover_label": ParagraphStyle(
            "CoverLabel", parent=base["Normal"], fontName="GuideSansBold", fontSize=9,
            leading=12, textColor=BLUE, spaceAfter=7 * mm, alignment=TA_LEFT,
        ),
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName="GuideSansBold", fontSize=25,
            leading=30, textColor=NAVY, alignment=TA_LEFT, spaceAfter=7 * mm,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName="GuideSans", fontSize=12,
            leading=18, textColor=colors.HexColor("#334155"), spaceAfter=8 * mm,
        ),
        "h2": ParagraphStyle(
            "Heading2", parent=base["Heading2"], fontName="GuideSansBold", fontSize=16,
            leading=20, textColor=NAVY, spaceBefore=6 * mm, spaceAfter=3 * mm,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "Heading3", parent=base["Heading3"], fontName="GuideSansBold", fontSize=12,
            leading=15, textColor=BLUE, spaceBefore=4 * mm, spaceAfter=2 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="GuideSans", fontSize=9.6,
            leading=14, textColor=colors.HexColor("#1E293B"), spaceAfter=2.5 * mm,
            splitLongWords=True,
        ),
        "list": ParagraphStyle(
            "List", parent=base["BodyText"], fontName="GuideSans", fontSize=9.4,
            leading=13.5, textColor=colors.HexColor("#1E293B"), spaceAfter=1.2 * mm,
            splitLongWords=True,
        ),
        "code": ParagraphStyle(
            "Code", parent=base["Code"], fontName="GuideMono", fontSize=8,
            leading=11, textColor=colors.HexColor("#0F172A"), splitLongWords=True,
        ),
        "toc_title": ParagraphStyle(
            "TocTitle", parent=base["Heading2"], fontName="GuideSansBold", fontSize=13,
            leading=16, textColor=NAVY, spaceBefore=3 * mm, spaceAfter=3 * mm,
        ),
        "toc0": ParagraphStyle(
            "TOC0", parent=base["Normal"], fontName="GuideSans", fontSize=9.5,
            leading=14, leftIndent=0, firstLineIndent=0, textColor=NAVY, spaceBefore=1.5 * mm,
        ),
        "toc1": ParagraphStyle(
            "TOC1", parent=base["Normal"], fontName="GuideSans", fontSize=8.5,
            leading=12, leftIndent=6 * mm, firstLineIndent=0, textColor=MID_GRAY,
        ),
        "table_head": ParagraphStyle(
            "TableHead", parent=base["Normal"], fontName="GuideSansBold", fontSize=8.5,
            leading=11, textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "TableCell", parent=base["Normal"], fontName="GuideSans", fontSize=8.3,
            leading=11, textColor=colors.HexColor("#1E293B"), splitLongWords=True,
        ),
    }


class GuideDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        level = getattr(flowable, "toc_level", None)
        if level is None:
            return
        text = flowable.getPlainText()
        key = f"heading-{self.seq.nextf('heading')}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=False)
        self.notify("TOCEntry", (level, text, self.page, key))


def split_markdown(markdown: str) -> tuple[str, str, list[str]]:
    lines = normalize_text(markdown).splitlines()
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), "Vejledning")
    first_h2 = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    intro_lines = [line.strip() for line in lines[1:first_h2] if line.strip()]
    intro = " ".join(intro_lines) or "Vejledning til Indtagelse."
    return title, intro, lines[first_h2:]


def is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def parse_table(lines: list[str], start: int, styles, available_width: float):
    raw_rows = []
    index = start
    while index < len(lines) and "|" in lines[index] and lines[index].strip():
        raw_rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
        index += 1
    if len(raw_rows) < 2 or not is_table_separator(lines[start + 1]):
        return None, start
    rows = [raw_rows[0]] + raw_rows[2:]
    columns = max(len(row) for row in rows)
    rows = [row + [""] * (columns - len(row)) for row in rows]
    data = []
    for row_index, row in enumerate(rows):
        style = styles["table_head"] if row_index == 0 else styles["table_cell"]
        data.append([Paragraph(inline_markup(cell), style) for cell in row])
    if columns == 2:
        col_widths = [available_width * 0.32, available_width * 0.68]
    else:
        col_widths = [available_width / columns] * columns
    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.45, RULE),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_GRAY]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table, index


def markdown_flowables(lines: list[str], styles, available_width: float):
    story = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped == "<!-- PAGEBREAK -->":
            story.append(PageBreak())
            index += 1
            continue
        if stripped.startswith("```"):
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(normalize_text(lines[index]))
                index += 1
            index += 1
            code_html = "<br/>".join(html.escape(value) if value else "&nbsp;" for value in code_lines)
            code_box = Table([[Paragraph(f'<font name="GuideMono">{code_html}</font>', styles["code"])]],
                             colWidths=[available_width])
            code_box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PALE_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            story.extend([code_box, Spacer(1, 3 * mm)])
            continue
        if stripped.startswith("## ") or stripped.startswith("### "):
            level = 0 if stripped.startswith("## ") else 1
            prefix = "## " if level == 0 else "### "
            heading = Paragraph(inline_markup(stripped[len(prefix):]), styles["h2" if level == 0 else "h3"])
            heading.toc_level = level
            story.append(heading)
            index += 1
            continue
        if index + 1 < len(lines) and "|" in line and is_table_separator(lines[index + 1]):
            table, index = parse_table(lines, index, styles, available_width)
            story.extend([table, Spacer(1, 3 * mm)])
            continue
        bullet_match = re.match(r"^\s*[-*]\s+(.+)$", line)
        number_match = re.match(r"^\s*(\d+)[.)]\s+(.+)$", line)
        if bullet_match or number_match:
            numbered = bool(number_match)
            items = []
            list_start = int(number_match.group(1)) if number_match else None
            pattern = r"^\s*(\d+)[.)]\s+(.+)$" if numbered else r"^\s*[-*]\s+(.+)$"
            while index < len(lines):
                match = re.match(pattern, lines[index])
                if not match:
                    break
                content_group = 2 if numbered else 1
                items.append(ListItem(Paragraph(inline_markup(match.group(content_group)), styles["list"])))
                index += 1
            list_options = {
                "bulletType": "1" if numbered else "bullet",
                "leftIndent": 7 * mm,
                "bulletFontName": "GuideSans",
                "bulletFontSize": 8.5,
                "bulletColor": BLUE,
                "bulletAlign": "right",
                "bulletDedent": 2 * mm,
                "spaceAfter": 2.5 * mm,
            }
            if numbered:
                list_options["start"] = list_start
            story.append(KeepTogether([ListFlowable(items, **list_options)]))
            continue
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if (
                not candidate
                or candidate.startswith(("## ", "### ", "```", "<!-- PAGEBREAK -->"))
                or re.match(r"^\s*[-*]\s+", lines[index])
                or re.match(r"^\s*\d+[.)]\s+", lines[index])
                or (index + 1 < len(lines) and "|" in lines[index] and is_table_separator(lines[index + 1]))
            ):
                break
            paragraph_lines.append(candidate)
            index += 1
        paragraph = Paragraph(inline_markup(" ".join(paragraph_lines)), styles["body"])
        if len(" ".join(paragraph_lines)) < 90 and paragraph_lines[-1].endswith(":"):
            paragraph.keepWithNext = True
        story.append(paragraph)
    return story


def page_decorator(title: str, source_name: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setTitle(title)
        canvas.setAuthor("Indtagelse")
        canvas.setSubject(f"Genereret fra {source_name}")
        width, height = A4
        if doc.page > 1:
            canvas.setStrokeColor(RULE)
            canvas.setLineWidth(0.5)
            canvas.line(18 * mm, height - 15 * mm, width - 18 * mm, height - 15 * mm)
            canvas.setFont("GuideSans", 8)
            canvas.setFillColor(MID_GRAY)
            canvas.drawString(18 * mm, height - 11.5 * mm, title)
        canvas.setStrokeColor(RULE)
        canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
        canvas.setFont("GuideSans", 7.5)
        canvas.setFillColor(MID_GRAY)
        canvas.drawString(18 * mm, 9.5 * mm, f"Kilde: {source_name}")
        canvas.drawRightString(width - 18 * mm, 9.5 * mm, f"Side {doc.page}")
        canvas.restoreState()
    return draw


def build_pdf(source: Path, destination: Path, label: str) -> dict:
    markdown = source.read_text(encoding="utf-8")
    title, intro, body_lines = split_markdown(markdown)
    styles = make_styles()
    available_width = A4[0] - 36 * mm
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_pdf = TEMP_ROOT / destination.name
    temp_pdf.unlink(missing_ok=True)

    doc = GuideDocTemplate(
        str(temp_pdf), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=21 * mm, bottomMargin=20 * mm, title=title, author="Indtagelse",
    )
    toc = TableOfContents()
    toc.levelStyles = [styles["toc0"], styles["toc1"]]
    story = [
        Spacer(1, 8 * mm),
        Paragraph("INDTAGELSE", styles["cover_label"]),
        Paragraph(inline_markup(title), styles["title"]),
        Paragraph(inline_markup(intro), styles["subtitle"]),
        Table([[Paragraph(inline_markup(label), styles["table_cell"])]], colWidths=[available_width],
              style=TableStyle([
                  ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
                  ("BOX", (0, 0), (-1, -1), 0.6, BLUE),
                  ("LEFTPADDING", (0, 0), (-1, -1), 8),
                  ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                  ("TOPPADDING", (0, 0), (-1, -1), 7),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
              ])),
        Spacer(1, 8 * mm),
        Paragraph("Indhold", styles["toc_title"]),
        toc,
        PageBreak(),
    ]
    story.extend(markdown_flowables(body_lines, styles, available_width))
    decorate = page_decorator(title, source.name)
    doc.multiBuild(story, onFirstPage=decorate, onLaterPages=decorate)

    result = validate_pdf(temp_pdf, source, title)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_pdf, destination)
    return result


def validate_pdf(pdf_path: Path, source_path: Path, expected_title: str | None = None) -> dict:
    if not pdf_path.is_file() or pdf_path.stat().st_size < 5_000:
        raise RuntimeError(f"PDF mangler eller er mistænkeligt lille: {pdf_path}")
    reader = PdfReader(str(pdf_path))
    if not reader.pages:
        raise RuntimeError(f"PDF har ingen sider: {pdf_path}")
    extracted = "\n".join((page.extract_text() or "") for page in reader.pages)
    compact = re.sub(r"\s+", " ", normalize_text(extracted))
    source_text = normalize_text(source_path.read_text(encoding="utf-8"))
    title = expected_title or split_markdown(source_text)[0]
    required = [title] + re.findall(r"^##\s+(.+)$", source_text, flags=re.MULTILINE)
    missing = [heading for heading in required if re.sub(r"\s+", " ", heading).strip() not in compact]
    if missing:
        raise RuntimeError(f"PDF mangler forventede overskrifter ({pdf_path.name}): {missing}")
    if "\ufffd" in extracted:
        raise RuntimeError(f"PDF indeholder ugyldige erstatningstegn: {pdf_path}")
    metadata_title = str((reader.metadata or {}).get("/Title") or "")
    if title not in metadata_title:
        raise RuntimeError(f"PDF-metadata mangler korrekt titel: {pdf_path}")
    return {"file": pdf_path.name, "pages": len(reader.pages), "bytes": pdf_path.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    register_fonts()
    results = []
    for source_name, pdf_name, label in GUIDES:
        source = ROOT / source_name
        output = args.output_dir.resolve() / pdf_name
        if args.validate_only:
            title, _intro, _body = split_markdown(source.read_text(encoding="utf-8"))
            result = validate_pdf(output, source, title)
        else:
            result = build_pdf(source, output, label)
        results.append(result)
        print(f"OK {result['file']}: {result['pages']} sider, {result['bytes']} bytes")
    if TEMP_ROOT.exists() and not any(TEMP_ROOT.iterdir()):
        shutil.rmtree(TEMP_ROOT)
    print(f"PDF-kontrol bestået: {len(results)} vejledninger.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FEJL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
