"""PDF → Markdown 변환 전체 흐름.

페이지마다 엔진을 고른다:
- 텍스트 레이어가 있는 페이지 → native.py (구조·띄어쓰기·이미지 보존이 좋음)
- 스캔(이미지만) 페이지        → ocr.py    (xberg PaddleOCR, 한·일·영)
수식 인식을 켜면 두 경로 모두 formulas.py 가 수식 자리를 표식으로 바꿔 두었다가 LaTeX 로 되돌린다.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import quote

import pymupdf

from ..core import CancelFn, CancelledError, ProgressFn
from . import formulas, native, ocr
from .options import ConvertOptions, ConvertResult

_MIN_TEXT_CHARS = 30       # 이보다 글자가 적으면 '텍스트 없는 페이지'로 본다
_MIN_IMAGE_COVERAGE = 0.3  # 페이지 면적 대비 이미지 비율이 이 이상이면 스캔본으로 본다
_GARBLED_RATIO = 0.3       # 깨진 글자(U+FFFD) 비율이 이 이상이면 OCR 로 다시 읽는다
# 스캐너가 넣은 OCR 층: 페이지를 덮는 이미지 위에 보이지 않는(투명) 글자만 있는 경우
_SCAN_IMAGE_COVERAGE = 0.8
_INVISIBLE_TEXT_RATIO = 0.8
_VISIBLE_TEXT = pymupdf.mupdf.FZ_STEXT_FILLED | pymupdf.mupdf.FZ_STEXT_STROKED


def needs_ocr(page: pymupdf.Page, mode: str) -> bool:
    if mode == "off":
        return False
    if mode == "force":
        return True
    text = "".join(page.get_text("text").split())
    if text and text.count("�") / len(text) >= _GARBLED_RATIO:
        return True
    coverage = _image_coverage(page)
    if len(text) >= _MIN_TEXT_CHARS:
        # 스캐너/다른 프로그램이 미리 넣은 OCR 층은 품질을 믿을 수 없으므로 다시 읽는다.
        return (coverage >= _SCAN_IMAGE_COVERAGE
                and _invisible_text_ratio(page) >= _INVISIBLE_TEXT_RATIO)
    return coverage >= _MIN_IMAGE_COVERAGE


def _image_coverage(page: pymupdf.Page) -> float:
    page_area = abs(page.rect) or 1
    covered = sum(abs(pymupdf.Rect(info["bbox"]) & page.rect) for info in page.get_image_info())
    return covered / page_area


def _invisible_text_ratio(page: pymupdf.Page) -> float:
    total = invisible = 0
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                n = len(span["text"].strip())
                total += n
                if not span["char_flags"] & _VISIBLE_TEXT:
                    invisible += n
    return invisible / total if total else 0.0


def convert_pdf(
    pdf_path: str,
    out_md: str,
    opts: ConvertOptions,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> ConvertResult:
    out = Path(out_md)
    assets_dir = out.with_name(f"{out.stem}_assets")
    assets_existed = assets_dir.exists()
    result = ConvertResult(md_path=str(out))
    ocr_engine = ocr.OcrEngine(opts.ocr_languages, opts.ocr_quality) if ocr.available() else None
    use_formulas = opts.formulas and ocr.available()  # 수식 모델도 xberg 에 들어 있다

    try:
        with pymupdf.open(pdf_path) as doc:
            native_conv = native.NativeConverter(doc)
            total = doc.page_count
            parts: list[str] = []
            skipped_ocr = 0
            for i in range(total):
                if should_cancel and should_cancel():
                    raise CancelledError()
                page = doc[i]
                wants_ocr = needs_ocr(page, opts.ocr_mode)
                found = (formulas.detect(ocr.single_page_pdf(doc, i), page.rect)
                         if use_formulas else [])
                if wants_ocr and ocr_engine is not None:
                    masked = formulas.mask_scan(page, found) if found else None
                    md = ocr_engine.page_markdown(doc, i, masked)
                    result.ocr_pages += 1
                    if opts.attach_scan_images and opts.image_mode != "none":
                        md += "\n\n" + _page_image(page, i, opts.image_mode, assets_dir)
                        result.images += opts.image_mode == "folder"
                else:
                    if wants_ocr and not page.get_text("text").strip():
                        skipped_ocr += 1  # OCR 엔진이 없는데 기존 텍스트 층도 없음
                    if found:
                        with formulas.mask_digital(doc, i, found) as masked_doc:
                            md, n = native_conv.page_markdown(i, opts.image_mode, assets_dir,
                                                              source=masked_doc)
                    else:
                        md, n = native_conv.page_markdown(i, opts.image_mode, assets_dir)
                    result.images += n
                if found:
                    md, used = formulas.restore(md, found)
                    result.formulas += used
                parts.append(md)
                if progress:
                    progress(i + 1, total)
            result.pages = total

        if skipped_ocr:
            result.warnings.append("ocr_unavailable")
        sep = "\n\n---\n\n" if opts.page_separators else "\n\n"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(sep.join(p for p in parts if p) + "\n", encoding="utf-8")
    except BaseException:
        # 취소/실패 시 이번 변환이 새로 만든 이미지 폴더는 정리한다.
        if not assets_existed and assets_dir.exists():
            shutil.rmtree(assets_dir, ignore_errors=True)
        raise

    # 이미지가 하나도 없으면 빈 폴더를 남기지 않는다.
    if not assets_existed and assets_dir.exists() and not any(assets_dir.iterdir()):
        assets_dir.rmdir()
    return result


def _page_image(page: pymupdf.Page, index: int, image_mode: str, assets_dir: Path) -> str:
    """OCR 한 페이지의 원본을 이미지로 붙인다(스캔본 속 사진/도표 보존용)."""
    pix = page.get_pixmap(dpi=110)
    if image_mode == "embed":
        import base64

        data = base64.b64encode(pix.tobytes("png")).decode("ascii")
        return f"![page {index + 1}](data:image/png;base64,{data})"
    assets_dir.mkdir(parents=True, exist_ok=True)
    name = f"page{index + 1:03d}_scan.png"
    pix.save(str(assets_dir / name))
    return f"![page {index + 1}]({quote(f'{assets_dir.name}/{name}')})"
