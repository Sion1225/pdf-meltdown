"""PDF → Markdown 변환 옵션과 결과."""

from __future__ import annotations

from dataclasses import dataclass, field

OCR_MODES = ("auto", "off", "force")          # 자동(필요한 페이지만) / 끄기 / 모든 페이지
OCR_QUALITIES = ("fast", "accurate")          # 빠름(mobile 모델) / 정확(server 모델)
OCR_LANGUAGES = ("en", "es", "ja", "ko")
IMAGE_MODES = ("folder", "embed", "none")     # 별도 폴더 / md에 포함 / 제외


@dataclass
class ConvertOptions:
    ocr_mode: str = "auto"
    ocr_quality: str = "fast"
    ocr_languages: tuple[str, ...] = OCR_LANGUAGES
    image_mode: str = "folder"
    attach_scan_images: bool = False   # OCR 한 페이지의 원본 이미지를 함께 넣을지
    page_separators: bool = False      # 페이지 사이에 구분선(---) 넣기
    formulas: bool = False             # 수식을 LaTeX 로 인식(xberg LaTeX-OCR, 페이지당 수 초 추가)


@dataclass
class ConvertResult:
    md_path: str
    pages: int = 0
    ocr_pages: int = 0
    images: int = 0
    formulas: int = 0
    warnings: list[str] = field(default_factory=list)
