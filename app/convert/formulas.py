"""수식 인식(LaTeX).

xberg 의 LaTeX-OCR 모델로 페이지의 수식 위치와 LaTeX 를 얻은 뒤, 수식 자리를 'FX01' 같은 표식으로
바꾼 페이지를 평소처럼 변환하고, 결과의 표식을 LaTeX 로 되돌린다. 표식은 변환기(OCR 또는 텍스트 추출)가
자기 레이아웃·읽기 순서대로 본문에 넣어 주므로, 좌표로 문단 위치를 맞출 필요가 없다.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import pymupdf

_DPI = 300
# OCR 이 0/1 을 O/I/l 로 읽는 경우까지 허용
_TOKEN = re.compile(r"(\$\$\s*)?F\s*X\s*([0-9OoIl|]{2})(\s*\$\$)?")
_DIGIT = str.maketrans("OoIl|", "00111")


@dataclass
class Formula:
    rect: pymupdf.Rect  # 페이지 좌표(위 기준)
    latex: str


def token(i: int) -> str:
    return f"FX{i:02d}"


def detect(page_pdf: bytes, page_rect: pymupdf.Rect) -> list[Formula]:
    """한 페이지짜리 PDF 에서 수식을 찾는다(OCR 없이 레이아웃 + LaTeX-OCR 만)."""
    import xberg

    cfg = xberg.ExtractionConfig(
        output_format="markdown",
        use_layout_for_markdown=True,  # 이게 켜져야 레이아웃·수식 모델이 돈다
        use_cache=False,
        disable_ocr=True,
        include_document_structure=True,
        layout=xberg.LayoutDetectionConfig(formula_model="latex_ocr"),
        images=xberg.ImageExtractionConfig(extract_images=False),
    )
    inp = xberg.ExtractInput(kind="bytes", bytes=page_pdf, mime_type="application/pdf")
    doc = asyncio.run(xberg.extract(inp, cfg)).results[0]

    # 레이아웃 '수식 영역' 노드에서 온 항목은 LaTeX 가 아니라 OCR 글자이고 좌표도 픽셀 단위라 뺀다.
    node_boxes = {
        (n.bbox.x0, n.bbox.y0, n.bbox.x1, n.bbox.y1)
        for n in (doc.document.nodes if doc.document else [])
        if n.bbox is not None and str(n.content.node_type) == "formula"
    }
    found = []
    height = page_rect.height
    bounds = page_rect + (-2, -2, 2, 2)
    for f in doc.formulas or []:
        b = f.bbox
        latex = (f.latex or "").strip()
        if not latex or b is None or (b.x0, b.y0, b.x1, b.y1) in node_boxes:
            continue
        rect = pymupdf.Rect(b.x0, height - b.y1, b.x1, height - b.y0)  # 아래 기준 → 위 기준
        if not rect.is_empty and rect in bounds:
            found.append(Formula(rect, latex))
    found.sort(key=lambda f: (round(f.rect.y0), f.rect.x0))
    return found


def mask_scan(page: pymupdf.Page, formulas: list[Formula]) -> bytes:
    """스캔 페이지: 수식 영역을 흰색으로 지우고 표식을 그린 '이미지만 있는' 한 장짜리 PDF."""
    rect = page.rect
    with pymupdf.open() as tmp:
        p = tmp.new_page(width=rect.width, height=rect.height)
        p.insert_image(p.rect, pixmap=page.get_pixmap(dpi=_DPI))
        for i, f in enumerate(formulas, 1):
            p.draw_rect(f.rect, color=None, fill=(1, 1, 1))
            size = _token_size(f.rect)
            p.insert_text((f.rect.x0 + 2, f.rect.y0 + f.rect.height / 2 + size * 0.35),
                          token(i), fontsize=size, fontname="helv")
        pix = p.get_pixmap(dpi=_DPI)  # 표식까지 그림으로 굳힌다(텍스트 층 없이)
    with pymupdf.open() as flat:
        fp = flat.new_page(width=rect.width, height=rect.height)
        fp.insert_image(fp.rect, pixmap=pix)
        return flat.tobytes()


def mask_digital(doc: pymupdf.Document, index: int, formulas: list[Formula]) -> pymupdf.Document:
    """디지털 페이지: 수식 영역의 글자·선·그림을 지우고 그 자리에 표식 글자를 쓴 한 장짜리 문서."""
    one = pymupdf.open()
    one.insert_pdf(doc, from_page=index, to_page=index)
    page = one[0]
    for i, f in enumerate(formulas, 1):
        page.add_redact_annot(f.rect, text=token(i), fontname="helv",
                              fontsize=_token_size(f.rect), align=pymupdf.TEXT_ALIGN_LEFT)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    return one


def restore(md: str, formulas: list[Formula]) -> tuple[str, int]:
    """표식을 LaTeX 로 바꾼다. 표식만 있는 줄은 $$…$$(별도 줄 수식), 문장 속이면 $…$. (결과, 바꾼 수)"""
    used = 0

    def latex_for(m: re.Match) -> str | None:
        i = int(m.group(2).translate(_DIGIT)) - 1
        return formulas[i].latex if 0 <= i < len(formulas) else None

    lines = []
    for line in md.split("\n"):
        m = _TOKEN.fullmatch(line.strip())
        if m and (latex := latex_for(m)) is not None:
            lines.append(f"$${latex}$$")
            used += 1
            continue

        def inline(m: re.Match) -> str:
            nonlocal used
            latex = latex_for(m)
            if latex is None:
                return m.group(0)
            used += 1
            return f"${latex}$"

        lines.append(_TOKEN.sub(inline, line))
    return "\n".join(lines), used


def _token_size(rect: pymupdf.Rect) -> float:
    return max(7.0, min(rect.height * 0.8, 14.0))
