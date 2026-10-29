"""스캔(이미지) 페이지 OCR → Markdown. xberg 의 PaddleOCR 백엔드 사용.

xberg 는 OCR 언어를 여러 개 받아도 첫 번째 모델만 쓰고, 신뢰도 점수도 주지 않는다.
그래서 언어는 직접 고른다: 잘못된 언어 모델로 읽으면 결과가 거의 비어 버리므로,
각 후보 결과에서 '그 언어 고유 문자 수'를 비교해 가장 많은 쪽을 택한다.
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
from typing import Callable

import pymupdf

from .native import clean_markdown

_MODEL_TIER = {"fast": "mobile", "accurate": "server"}
_HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]")
_JAPANESE = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")
_LATIN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
_SCRIPT = {"ko": _HANGUL, "ja": _JAPANESE, "en": _LATIN, "es": _LATIN}
# xberg 가 페이지 래스터를 이미지로 내보내며 남기는 자리표시자
_IMAGE_PLACEHOLDER = re.compile(r"^!\[[^\]]*\]\(image_\d+\.\w+\)\s*$", re.MULTILINE)


def available() -> bool:
    return importlib.util.find_spec("xberg") is not None


def _letters(text: str) -> int:
    return sum(1 for ch in text if ch.isalpha())


class OcrEngine:
    """페이지 단위 OCR. 문서 안에서 언어 판별 결과를 기억해 다음 페이지에 재사용한다."""

    def __init__(self, languages: tuple[str, ...], quality: str = "fast") -> None:
        langs = [l for l in languages if l in _SCRIPT] or ["en"]
        # 한국어·일본어 모델은 영문/숫자도 읽으므로, 둘 중 하나라도 있으면 영어 모델은 따로 돌리지 않는다.
        # 스페인어는 영어(라틴) 모델이 악센트·ñ 까지 읽으므로 영어 모델을 그대로 쓴다.
        cjk = [l for l in langs if l in ("ko", "ja")]
        self.candidates = cjk or ["en"]
        self.tier = _MODEL_TIER.get(quality, "mobile")
        self.current: str | None = None

    def page_markdown(self, doc: pymupdf.Document, index: int, pdf_bytes: bytes | None = None) -> str:
        """doc 의 index 페이지를 OCR 한다. pdf_bytes 를 주면(예: 수식을 표식으로 가린 페이지) 그것을 읽는다."""
        data = pdf_bytes if pdf_bytes is not None else single_page_pdf(doc, index)
        run: Callable[[str], str] = lambda lang: self._run(data, lang)  # noqa: E731

        if len(self.candidates) == 1:
            return run(self.candidates[0])

        if self.current is not None:
            text = run(self.current)
            if self._plausible(text, self.current):
                return text
            results = {self.current: text}
        else:
            results = {}
        # 처음이거나 결과가 이상하면 후보 언어를 모두 돌려 고른다.
        for lang in self.candidates:
            if lang not in results:
                results[lang] = run(lang)
        # 고유 문자 수가 같으면(영문·숫자뿐인 페이지 등) 지금 쓰던 언어를 유지한다.
        best = max(
            self.candidates,
            key=lambda l: (len(_SCRIPT[l].findall(results[l])), l == self.current),
        )
        self.current = best
        return results[best]

    @staticmethod
    def _plausible(text: str, lang: str) -> bool:
        compact = "".join(text.split())
        if not compact:
            return True  # 글자가 없는 페이지(그림만) — 재판별해도 소용없음
        letters = _letters(compact)
        # 잘못된 언어 모델은 글자를 거의 못 읽고 숫자·기호만 남긴다.
        if letters / len(compact) < 0.4:
            return False
        own = len(_SCRIPT[lang].findall(compact))
        latin = len(_LATIN.findall(compact))
        return own / letters >= 0.5 or latin / letters >= 0.6  # 영문 위주 페이지도 통과

    def _run(self, pdf_bytes: bytes, lang: str) -> str:
        import xberg

        cfg = xberg.ExtractionConfig(
            output_format="markdown",
            use_layout_for_markdown=True,
            layout=xberg.LayoutDetectionConfig(),
            force_ocr=True,
            use_cache=False,
            images=xberg.ImageExtractionConfig(extract_images=False),
            ocr=xberg.OcrConfig(
                backend="paddle-ocr",
                language=[lang],
                paddle_ocr_settings=xberg.PaddleOcrConfig(language=lang, model_tier=self.tier),
            ),
        )
        inp = xberg.ExtractInput(kind="bytes", bytes=pdf_bytes, mime_type="application/pdf")
        res = asyncio.run(xberg.extract(inp, cfg))
        if not res.results:
            raise RuntimeError("; ".join(str(e) for e in res.errors) or "OCR 결과가 없습니다.")
        return clean_markdown(_IMAGE_PLACEHOLDER.sub("", res.results[0].content))


def single_page_pdf(doc: pymupdf.Document, index: int) -> bytes:
    with pymupdf.open() as one:
        one.insert_pdf(doc, from_page=index, to_page=index)
        return one.tobytes()
