"""텍스트 레이어가 있는(디지털) 페이지 → Markdown. PyMuPDF 2.0에 포함된 pymupdf4llm 사용.

pymupdf4llm 의 레이아웃 모델 모드는 2단 문서의 읽기 순서를 자주 뒤섞으므로(단 중간에 다른 단이
끼어듦), 열(column) 감지로 순서를 잡는 기존(legacy) 모드를 쓴다.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import quote

import pymupdf

# CJK 문자(한글·가나·한자·전각) — 고정폭 CJK 폰트 본문이 코드(`...`)로 오인되는 것을 되돌릴 때 사용
_CJK = "ᄀ-ᇿ぀-ヿ㄰-㆏㐀-䶿一-鿿가-힯＀-￯"
_CJK_CHAR = re.compile(f"[{_CJK}]")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD_HEADING = re.compile(r"^(#{1,6}) \*\*(.+?)\*\*\s*$", re.MULTILINE)
_LIST_INDENT = re.compile(r"^ {1,3}([-*+] |\d+\. )", re.MULTILINE)
_BULLET_GLYPH = re.compile(r"^[ \t]*[•・▪◦●○■□‣⁃][ \t]*(?=\S)", re.MULTILINE)
_DATA_IMAGE = re.compile(r"!\[([^\]]*)\]\(data:image/(\w+);base64,([A-Za-z0-9+/=\s]+?)\s*\)")


class NativeConverter:
    """문서 하나에 대한 변환기. 제목 크기 분석(IdentifyHeaders)을 문서당 한 번만 수행한다."""

    def __init__(self, doc: pymupdf.Document) -> None:
        import pymupdf4llm  # 무거운 import 는 실제 사용 시점에

        pymupdf4llm.use_layout(False)
        self._p4l = pymupdf4llm
        self.doc = doc
        self._headers = None

    def page_markdown(
        self, index: int, image_mode: str, assets_dir: Path, source: pymupdf.Document | None = None
    ) -> tuple[str, int]:
        """한 페이지를 Markdown 으로 변환한다. (markdown, 저장한 이미지 수) 반환.

        source 를 주면(예: 수식을 표식으로 바꾼 한 장짜리 문서) 그 첫 페이지를 변환하되,
        제목 크기 기준과 이미지 이름(index)은 원본 문서 기준을 쓴다.
        """
        if self._headers is None:
            self._headers = self._p4l.IdentifyHeaders(self.doc)
        # 이미지는 항상 data URI 로 받아 직접 저장한다. pymupdf4llm 의 write_images 는
        # 경로의 공백·괄호를 '_'/'-' 로 바꾼 위치에 저장하려다 실패하는 버그가 있다.
        md = self._p4l.to_markdown(
            source if source is not None else self.doc,
            pages=[0 if source is not None else index],
            hdr_info=self._headers,
            ignore_code=True,
            embed_images=image_mode != "none",
            ignore_images=image_mode == "none",
            dpi=150,
            show_progress=False,
        )
        md = clean_markdown(md)
        images = 0
        if image_mode == "folder":
            md, images = _save_images(md, assets_dir, index)
        elif image_mode == "embed":
            md = _DATA_IMAGE.sub(lambda m: _data_link(m.group(1), m.group(2), m.group(3)), md)
        return md, images


def clean_markdown(md: str) -> str:
    """pymupdf4llm / OCR 결과 공통 정리."""
    lines = []
    for line in md.splitlines():
        # 고정폭 CJK 폰트 본문은 코드(`...`)로 오인된다 — CJK 가 섞인 줄의 인라인 코드는 벗긴다.
        if _CJK_CHAR.search(line):
            line = _INLINE_CODE.sub(r"\1", line)
        lines.append(line.rstrip())
    md = "\n".join(lines)
    md = _BOLD_HEADING.sub(r"\1 \2", md)
    md = _LIST_INDENT.sub(r"\1", md)
    md = _BULLET_GLYPH.sub("- ", md)
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def _data_link(alt: str, fmt: str, b64: str) -> str:
    return f"![{alt}](data:image/{fmt};base64,{''.join(b64.split())})"


def _save_images(md: str, assets_dir: Path, index: int) -> tuple[str, int]:
    """data URI 이미지를 'page003_01.png' 파일로 저장하고 md 기준 상대경로 링크로 바꾼다."""
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        ext = "jpg" if m.group(2).lower() == "jpeg" else m.group(2).lower()
        name = f"page{index + 1:03d}_{count:02d}.{ext}"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / name).write_bytes(base64.b64decode("".join(m.group(3).split())))
        return f"![{m.group(1)}]({quote(f'{assets_dir.name}/{name}')})"

    return _DATA_IMAGE.sub(repl, md), count
