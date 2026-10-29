"""저장 후처리: 압축, 쪽번호, 워터마크, 암호 (PyMuPDF).

core.export_pages 로 만든 PDF 를 열어 옵션을 적용한 뒤 최종 파일로 저장한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .core import CancelFn, CancelledError, ProgressFn

COMPRESS_LEVELS = ("none", "medium", "strong")
NUMBER_FORMATS = ("{n}", "{n} / {total}", "- {n} -")
NUMBER_POSITIONS = ("bottom-center", "bottom-right", "top-right")

# (목표 DPI, JPEG 품질) — 목표보다 해상도가 높은 이미지만 다시 압축한다.
_COMPRESS = {"medium": (150, 75), "strong": (96, 55)}
_MARGIN = 24  # pt


@dataclass
class SaveOptions:
    compress: str = "none"
    page_numbers: bool = False
    number_format: str = "{n}"
    number_position: str = "bottom-center"
    number_start: int = 1
    watermark: str = ""            # 비어 있으면 워터마크 없음
    watermark_opacity: float = 0.15
    watermark_angle: int = 45
    watermark_size: int = 60
    password: str = ""

    @property
    def is_plain(self) -> bool:
        """후처리할 것이 없으면 True (그냥 export 결과를 쓰면 됨)."""
        return (self.compress == "none" and not self.page_numbers
                and not self.watermark and not self.password)


def postprocess(
    src: str,
    out: str,
    opts: SaveOptions,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> None:
    font = pymupdf.Font("cjk")  # 한·중·일·영 모두 그릴 수 있는 Droid Sans Fallback
    stamped = False
    with pymupdf.open(src) as doc:
        total = doc.page_count
        for i, page in enumerate(doc):
            if should_cancel and should_cancel():
                raise CancelledError()
            if opts.page_numbers or opts.watermark:
                # 회전을 내용에 반영해 두면 보이는 방향 그대로의 좌표로 도장을 찍을 수 있다.
                if page.rotation:
                    page.remove_rotation()
                # 원본 내용이 좌표 변환을 되돌리지 않고 끝나면 덧붙인 글자가 뒤집히므로 q/Q 로 감싼다.
                if not page.is_wrapped:
                    page.wrap_contents()
                if opts.watermark:
                    _stamp_watermark(page, opts, font)
                if opts.page_numbers:
                    label = opts.number_format.format(n=opts.number_start + i,
                                                      total=opts.number_start + total - 1)
                    _stamp_number(page, label, opts.number_position, font)
                stamped = True
            if progress:
                progress(i + 1, total)

        if opts.compress in _COMPRESS:
            dpi, quality = _COMPRESS[opts.compress]
            doc.rewrite_images(dpi_threshold=dpi + 20, dpi_target=dpi, quality=quality)
        if stamped:
            doc.subset_fonts()  # 4MB 가량의 CJK 폰트에서 쓴 글자만 남긴다

        kwargs = {"garbage": 3, "deflate": True}
        if opts.compress != "none":
            kwargs.update(garbage=4, deflate_images=True, deflate_fonts=True, clean=True,
                          use_objstms=1)
        if opts.password:
            kwargs.update(encryption=pymupdf.PDF_ENCRYPT_AES_256,
                          user_pw=opts.password, owner_pw=opts.password)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        doc.save(out, **kwargs)


def _stamp_number(page: pymupdf.Page, label: str, position: str, font: pymupdf.Font) -> None:
    size = 10
    rect = page.rect
    width = font.text_length(label, fontsize=size)
    if position == "bottom-right":
        x, y = rect.x1 - _MARGIN - width, rect.y1 - _MARGIN
    elif position == "top-right":
        x, y = rect.x1 - _MARGIN - width, rect.y0 + _MARGIN + size
    else:  # bottom-center
        x, y = rect.x0 + (rect.width - width) / 2, rect.y1 - _MARGIN
    tw = pymupdf.TextWriter(rect)
    tw.append((x, y), label, font=font, fontsize=size)
    tw.write_text(page, color=(0.25, 0.25, 0.25))


def _stamp_watermark(page: pymupdf.Page, opts: SaveOptions, font: pymupdf.Font) -> None:
    rect = page.rect
    size = opts.watermark_size
    width = font.text_length(opts.watermark, fontsize=size)
    max_width = (rect.width ** 2 + rect.height ** 2) ** 0.5 * 0.8  # 대각선 길이의 80%
    if width > max_width:  # 긴 문구는 페이지를 벗어나지 않게 줄인다
        size *= max_width / width
        width = max_width
    center = pymupdf.Point(rect.x0 + rect.width / 2, rect.y0 + rect.height / 2)
    # 글자 덩어리의 중심이 페이지 중심에 오도록 기준선 시작점을 잡는다.
    start = pymupdf.Point(center.x - width / 2, center.y + size * 0.35)
    tw = pymupdf.TextWriter(rect)
    tw.append(start, opts.watermark, font=font, fontsize=size)
    tw.write_text(
        page,
        color=(0.5, 0.5, 0.5),
        opacity=opts.watermark_opacity,
        morph=(center, pymupdf.Matrix(opts.watermark_angle)),  # 화면 기준 반시계(오른쪽 위로) 방향
    )
