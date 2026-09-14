from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

WORKOUT_PLAN_SYSTEM = """You are a coach writing a one-page training handout a person could print and take to the gym.
Use ONLY facts from the cited posts. Same language as the user.

Structure:
1. A short title as `# ...` then 1-2 lines on goal and level. No slogans.
2. Weekly split as a short list (not a marketing overview).
3. Each training day: `### Day N: ...` then a table:
   | Exercise | Sets | Reps | Notes |
   Copy sets, reps, rest, and loads exactly. Do not invent numbers.
4. Cite with [Source N] only on the row or sentence that comes from that post.

No "training brief", no "at a glance", no pep talk, no closing.
"""

RECIPE_BOOK_SYSTEM = """You are writing a recipe card someone would keep on the kitchen counter.
Use ONLY facts from the cited posts. Same language as the user.

Structure:
1. Dish name as `# ...` and prep time if the sources say it.
2. Ingredients table: | Ingredient | Quantity | Notes |
3. Numbered method steps.
4. At most two short notes (storage, swaps) if present in the sources.
5. [Source N] only next to facts from that post.

No restaurant copy and no "enjoy".
"""

GROCERY_LIST_SYSTEM = """Write a shopping list someone would take to the store.
Use ONLY ingredients from the cited posts. Same language as the user.

Use markdown checklists grouped by:
- Proteins
- Vegetables and fruit
- Carbs
- Fats, condiments, other

Format: `- [ ] item — amount` when an amount exists. Merge duplicates.
No intro and no sign-off.
"""

ARTIFACT_PROMPTS = {
    "workout_plan": WORKOUT_PLAN_SYSTEM,
    "recipe_book": RECIPE_BOOK_SYSTEM,
    "grocery_list": GROCERY_LIST_SYSTEM,
}


def get_artifact_system_prompt(artifact_type: Optional[str]) -> Optional[str]:
    if not artifact_type:
        return None
    key = artifact_type.strip().lower().replace("-", "_").replace(" ", "_")
    return ARTIFACT_PROMPTS.get(key)


def _first_heading_and_body(content: str) -> Tuple[Optional[str], str]:
    lines = content.split("\n")
    heading = None
    skip_idx = None
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            heading = stripped[2:].strip()
            skip_idx = i
        break
    if skip_idx is None:
        return None, content
    body = "\n".join(lines[:skip_idx] + lines[skip_idx + 1 :])
    return heading, body.lstrip("\n")


def _replace_sources_in_bracket(match: re.Match, sources_map: Optional[Dict[int, str]] = None) -> str:
    inner = match.group(1)
    numbers = re.findall(r"\d+", inner)
    if not numbers:
        return match.group(0)
    links = []
    for n_str in numbers:
        n = int(n_str)
        target_url = sources_map.get(n) if sources_map else None
        if target_url:
            links.append(f'<a href="{target_url}"><u><b>Source {n}</b></u></a>')
        else:
            links.append(f'<a href="#source_{n}"><u><b>Source {n}</b></u></a>')
    return f"[{', '.join(links)}]"


def _md_to_reportlab_html(text: str, sources_map: Optional[Dict[int, str]] = None) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', escaped)
    escaped = re.sub(
        r"\[(Source\s*\d+[^\]]*)\]",
        lambda m: _replace_sources_in_bracket(m, sources_map=sources_map),
        escaped,
        flags=re.IGNORECASE,
    )
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2"><u>\1</u></a>', escaped)
    return escaped


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_table_separator(line: str) -> bool:
    s = line.strip().replace(" ", "")
    return s.startswith("|") and re.match(r"^\|(\:?\-{2,}\:?\|)+$", s) is not None


def _parse_table_block(table_lines: List[str]) -> Optional[Tuple[List[str], List[List[str]]]]:
    clean_lines = [l.strip() for l in table_lines if l.strip()]
    if not clean_lines:
        return None

    header = []
    rows = []

    for line in clean_lines:
        if _is_table_separator(line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not header:
            header = cells
        else:
            if len(cells) < len(header):
                cells += [""] * (len(header) - len(cells))
            elif len(cells) > len(header):
                cells = cells[: len(header)]
            rows.append(cells)

    if not header:
        return None
    return header, rows


def _render_reportlab_table(
    header: List[str],
    rows: List[List[str]],
    max_width: float = 516.0,
    sources_map: Optional[Dict[int, str]] = None,
) -> Any:
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors

    col_count = len(header)
    if col_count == 0:
        return None

    col_max_lengths = [len(h) for h in header]
    for r in rows:
        for c_idx, cell in enumerate(r):
            if c_idx < col_count:
                col_max_lengths[c_idx] = max(col_max_lengths[c_idx], len(cell))

    total_len = max(sum(col_max_lengths), 1)
    col_widths = []
    for length in col_max_lengths:
        col_widths.append(max(length / total_len, 0.12))

    norm_sum = sum(col_widths)
    actual_widths = [(w / norm_sum) * max_width for w in col_widths]

    th_style = ParagraphStyle(
        "THStyle",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#333333"),
        fontName="Helvetica-Bold",
        alignment=0,
    )
    td_style = ParagraphStyle(
        "TDStyle",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#333333"),
        fontName="Helvetica",
        alignment=0,
    )

    table_data = []
    table_data.append(
        [Paragraph(_md_to_reportlab_html(h, sources_map=sources_map), th_style) for h in header]
    )
    for r in rows:
        table_data.append(
            [Paragraph(_md_to_reportlab_html(c, sources_map=sources_map), td_style) for c in r]
        )

    t = Table(table_data, colWidths=actual_widths, repeatRows=1)
    line = colors.HexColor("#DDDDDD")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, line),
                ("LINEABOVE", (0, 0), (-1, 0), 0.4, line),
                ("LINEBEFORE", (0, 0), (0, -1), 0.4, line),
                ("LINEAFTER", (-1, 0), (-1, -1), 0.4, line),
            ]
        )
    )
    return t


def _draw_page_number(canvas, doc) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors

    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(letter[0] / 2.0, 22, str(canvas.getPageNumber()))
    canvas.restoreState()


def export_artifact(
    content: str,
    output_path: str,
    title: str = "Documento",
    sources: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    sources_map = {i: s.get("url", "") for i, s in enumerate(sources or [], start=1)}
    cited_sources = [
        (i, s) for i, s in enumerate(sources or [], start=1) if s.get("cited", True)
    ]
    heading, body = _first_heading_and_body(content)
    display_title = heading or title

    if out.suffix.lower() == ".pdf":
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            HRFlowable,
            PageBreak,
            KeepTogether,
        )
        from reportlab.lib import colors

        ink = colors.HexColor("#333333")
        muted = colors.HexColor("#555555")
        rule = colors.HexColor("#CCCCCC")

        doc = SimpleDocTemplate(
            str(out),
            pagesize=letter,
            rightMargin=54,
            leftMargin=54,
            topMargin=54,
            bottomMargin=46,
        )
        styles = getSampleStyleSheet()
        doc_title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            textColor=ink,
            fontName="Helvetica-Bold",
            spaceAfter=8,
        )
        h1_style = ParagraphStyle(
            "DocH1",
            parent=styles["Heading1"],
            fontSize=12,
            leading=16,
            textColor=ink,
            fontName="Helvetica-Bold",
            spaceBefore=14,
            spaceAfter=6,
            keepWithNext=True,
        )
        h2_style = ParagraphStyle(
            "DocH2",
            parent=styles["Heading2"],
            fontSize=11,
            leading=14,
            textColor=ink,
            fontName="Helvetica-Bold",
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
        )
        body_style = ParagraphStyle(
            "DocBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=ink,
            fontName="Helvetica",
            spaceAfter=4,
        )
        bullet_style = ParagraphStyle(
            "DocBullet",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=ink,
            fontName="Helvetica",
            leftIndent=14,
            spaceAfter=3,
        )
        quote_style = ParagraphStyle(
            "DocQuote",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=muted,
            fontName="Helvetica-Oblique",
            leftIndent=14,
            spaceBefore=4,
            spaceAfter=6,
        )
        source_heading_style = ParagraphStyle(
            "SourceHeading",
            parent=styles["Heading1"],
            fontSize=14,
            leading=18,
            textColor=ink,
            fontName="Helvetica-Bold",
            spaceAfter=8,
        )
        source_title_style = ParagraphStyle(
            "SourceTitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=ink,
            fontName="Helvetica-Bold",
            spaceAfter=2,
        )
        source_body_style = ParagraphStyle(
            "SourceBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=13,
            textColor=muted,
            fontName="Helvetica",
            spaceAfter=3,
        )
        source_url_style = ParagraphStyle(
            "SourceUrl",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=muted,
            fontName="Helvetica",
            spaceAfter=12,
        )

        elements = []
        elements.append(Paragraph(_md_to_reportlab_html(display_title), doc_title_style))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=rule, spaceBefore=0, spaceAfter=12))

        raw_lines = body.split("\n")
        idx = 0
        while idx < len(raw_lines):
            line = raw_lines[idx].strip()
            if not line:
                elements.append(Spacer(1, 4))
                idx += 1
                continue

            if _is_table_row(line):
                table_lines = []
                while idx < len(raw_lines) and _is_table_row(raw_lines[idx]):
                    table_lines.append(raw_lines[idx])
                    idx += 1
                parsed_table = _parse_table_block(table_lines)
                if parsed_table:
                    hdr, data_rows = parsed_table
                    rendered_tbl = _render_reportlab_table(
                        hdr, data_rows, max_width=504.0, sources_map=sources_map
                    )
                    if rendered_tbl:
                        elements.append(Spacer(1, 4))
                        elements.append(rendered_tbl)
                        elements.append(Spacer(1, 8))
                continue

            if line.startswith("### "):
                elements.append(Paragraph(_md_to_reportlab_html(line[4:], sources_map=sources_map), h2_style))
            elif line.startswith("## "):
                elements.append(Paragraph(_md_to_reportlab_html(line[3:], sources_map=sources_map), h1_style))
            elif line.startswith("# "):
                elements.append(Paragraph(_md_to_reportlab_html(line[2:], sources_map=sources_map), h1_style))
            elif line.startswith(("- [ ]", "- [x]", "- [X]")):
                is_checked = line.startswith(("- [x]", "- [X]"))
                icon = "[x]" if is_checked else "[ ]"
                item_text = line[5:].strip()
                elements.append(
                    Paragraph(
                        f"<b>{icon}</b> {_md_to_reportlab_html(item_text, sources_map=sources_map)}",
                        bullet_style,
                    )
                )
            elif line.startswith(("- ", "* ", "• ")):
                bullet_text = line[2:].strip()
                elements.append(
                    Paragraph(f"• {_md_to_reportlab_html(bullet_text, sources_map=sources_map)}", bullet_style)
                )
            elif re.match(r"^\d+\.\s+", line):
                match = re.match(r"^(\d+)\.\s+(.*)", line)
                num, item_text = match.group(1), match.group(2)
                elements.append(
                    Paragraph(
                        f"<b>{num}.</b> {_md_to_reportlab_html(item_text, sources_map=sources_map)}",
                        bullet_style,
                    )
                )
            elif line.startswith(">"):
                quote_text = line.lstrip("> ").strip()
                elements.append(Paragraph(_md_to_reportlab_html(quote_text, sources_map=sources_map), quote_style))
            elif line.startswith("---"):
                elements.append(HRFlowable(width="100%", thickness=0.4, color=rule, spaceBefore=6, spaceAfter=8))
            else:
                elements.append(Paragraph(_md_to_reportlab_html(line, sources_map=sources_map), body_style))
            idx += 1

        if cited_sources:
            elements.append(PageBreak())
            elements.append(Paragraph("Fuentes", source_heading_style))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=rule, spaceBefore=0, spaceAfter=14))
            for i, s in cited_sources:
                creator = s.get("creator") or "creator"
                url = s.get("url") or ""
                summary = (s.get("summary") or "").strip()
                block = [
                    Paragraph(
                        f'<a name="source_{i}"/>[Source {i}]  @{creator}',
                        source_title_style,
                    )
                ]
                if summary:
                    block.append(Paragraph(summary, source_body_style))
                if url:
                    block.append(Paragraph(f'<a href="{url}"><u>{url}</u></a>', source_url_style))
                else:
                    block.append(Spacer(1, 10))
                elements.append(KeepTogether(block))

        doc.build(elements, onFirstPage=_draw_page_number, onLaterPages=_draw_page_number)
    else:
        lines = [f"# {display_title}", "", body.strip()]
        if cited_sources:
            lines.extend(["", "---", "", "## Fuentes", ""])
            for i, s in cited_sources:
                creator = s.get("creator") or ""
                url = s.get("url") or ""
                summary = (s.get("summary") or "").strip()
                lines.append(f"- **[Source {i}]** @{creator}")
                if summary:
                    lines.append(f"  {summary}")
                if url:
                    lines.append(f"  {url}")
                lines.append("")
        out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    return out.resolve()
