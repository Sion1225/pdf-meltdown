"""이미지 ↔ PDF.

- 이미지 → PDF: 이미지 한 장을 A4 한 페이지(가로 이미지는 가로 A4)에 비율 유지로 맞춰 넣는다.
- PDF → 이미지: 목록의 페이지들을 PNG/JPG 파일로 내보낸다(회전·빈 페이지 반영).
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from .core import A4, CancelFn, CancelledError, PageRef, ProgressFn
from .render import open_doc

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")


def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def image_to_pdf(image_path: str, out_dir: str) -> str:
    """이미지를 한 페이지짜리 PDF 로 만들어 out_dir 에 저장하고 경로를 반환한다."""
    with pymupdf.open(image_path) as img:
        frame = img[0].rect  # 이미지 크기(pt)
        portrait = frame.height >= frame.width
        w, h = A4 if portrait else (A4[1], A4[0])
        with pymupdf.open() as doc:
            page = doc.new_page(width=w, height=h)
            page.insert_image(page.rect, filename=image_path, keep_proportion=True)
            out = Path(out_dir) / f"{Path(image_path).stem}_{abs(hash(image_path)) % 10**8}.pdf"
            doc.save(out, garbage=3, deflate=True)
    return str(out)


def export_page_images(
    pages: list[PageRef],
    out_dir: str,
    base_name: str,
    fmt: str = "png",
    dpi: int = 150,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> list[str]:
    """페이지들을 이미지 파일로 저장한다. 생성된 파일 경로 목록 반환."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    width = max(3, len(str(len(pages))))
    docs: dict[str, pymupdf.Document] = {}
    written: list[str] = []
    try:
        for i, ref in enumerate(pages, start=1):
            if should_cancel and should_cancel():
                for p in written:
                    Path(p).unlink(missing_ok=True)
                raise CancelledError()
            pix = _render(ref, dpi, docs)
            path = out / f"{base_name}_p{i:0{width}d}.{fmt}"
            if fmt == "jpg":
                pix.save(str(path), jpg_quality=90)
            else:
                pix.save(str(path))
            written.append(str(path))
            if progress:
                progress(i, len(pages))
    finally:
        for d in docs.values():
            d.close()
    return written


def _render(ref: PageRef, dpi: int, docs: dict[str, pymupdf.Document]) -> pymupdf.Pixmap:
    zoom = dpi / 72
    if ref.is_blank:
        w, h = ref.blank_size
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, round(w * zoom), round(h * zoom)), 0)
        pix.set_rect(pix.irect, (255, 255, 255))
        return pix
    doc = docs.get(ref.src_path)
    if doc is None:
        doc = docs[ref.src_path] = open_doc(ref.src_path)
    matrix = pymupdf.Matrix(zoom, zoom).prerotate(ref.rotation)
    return doc.load_page(ref.src_index).get_pixmap(matrix=matrix, alpha=False)
