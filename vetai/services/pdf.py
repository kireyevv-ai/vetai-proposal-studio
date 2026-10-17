"""Формирование PDF коммерческого предложения (REQ-18..REQ-21).

PDF формируется по последней сохранённой версии; не включает служебные
предупреждения, статусы и диагностику. Используется ReportLab.
"""

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from vetai.models import SOURCE_PLACEHOLDER, ProposalDraft

BRAND_NAME = "VETAI"
_DOC_TITLE = "Коммерческое предложение"

_FONT_REGULAR = "VetaiSans"
_FONT_BOLD = "VetaiSans-Bold"
_fonts_registered = False

_FONT_CANDIDATES: tuple[tuple[Path, Path], ...] = (
    (
        Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans.ttf",
        Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf",
    ),
    (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
    (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/segoeuib.ttf")),
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ),
    (
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ),
)


def _register_fonts() -> None:
    global _fonts_registered
    if _fonts_registered:
        return
    regular = None
    bold = None
    for reg_path, bold_path in _FONT_CANDIDATES:
        if reg_path.exists():
            regular = reg_path
            bold = bold_path if bold_path.exists() else reg_path
            break
    if regular is None:
        raise RuntimeError(
            "Не найден Unicode-шрифт с поддержкой кириллицы для PDF. "
            "Добавьте TTF (например, DejaVuSans) в vetai/assets/fonts."
        )
    pdfmetrics.registerFont(TTFont(_FONT_REGULAR, str(regular)))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(bold)))
    _fonts_registered = True


def _format_date(dt: datetime) -> str:
    try:
        return dt.astimezone().strftime("%d.%m.%Y")
    except Exception:
        return dt.strftime("%d.%m.%Y")


def _on_page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(_FONT_REGULAR, 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"стр. {canvas.getPageNumber()}")
    canvas.drawString(18 * mm, 12 * mm, BRAND_NAME)
    canvas.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "brand": ParagraphStyle(
            "brand",
            fontName=_FONT_BOLD,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#14315a"),
            spaceAfter=2,
        ),
        "title": ParagraphStyle(
            "title",
            fontName=_FONT_BOLD,
            fontSize=15,
            leading=20,
            spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "meta",
            fontName=_FONT_REGULAR,
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#374151"),
            spaceAfter=8,
        ),
        "heading": ParagraphStyle(
            "heading",
            fontName=_FONT_BOLD,
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#14315a"),
            spaceBefore=12,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=_FONT_REGULAR,
            fontSize=10.5,
            leading=15,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
    }


def build_pdf(
    draft: ProposalDraft,
    client: str = "",
    *,
    title: str = _DOC_TITLE,
) -> bytes:
    _register_fonts()
    styles = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=22 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=title,
        author=BRAND_NAME,
    )

    story = []
    story.append(Paragraph(BRAND_NAME, styles["brand"]))
    story.append(Paragraph(title, styles["title"]))
    story.append(Spacer(1, 4))
    meta_parts = []
    if client:
        meta_parts.append(f"Клиент: {escape(client)}")
    meta_parts.append(f"Дата: {_format_date(draft.created_at)}")
    story.append(Paragraph(" · ".join(meta_parts), styles["meta"]))
    story.append(Spacer(1, 10))

    for section in draft.sections:
        if section.source == SOURCE_PLACEHOLDER or not section.text.strip():
            continue
        story.append(Paragraph(escape(section.title), styles["heading"]))
        for line in section.text.splitlines():
            line = line.strip()
            if not line:
                story.append(Spacer(1, 2))
                continue
            story.append(Paragraph(escape(line), styles["body"]))
        story.append(Spacer(1, 6))

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()


def pdf_page_count(pdf_bytes: bytes) -> int:
    try:
        return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))
    except Exception:
        return 0