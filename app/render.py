"""PyMuPDF(fitz) 로 PDF 페이지 썸네일을 렌더링한다."""

from __future__ import annotations

import threading
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF 1.24+ 권장 이름
except ImportError:  # pragma: no cover - 구버전 호환
    import fitz

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QImage, QPixmap

from .core import password_for


def open_doc(path: str) -> fitz.Document:
    """암호가 등록된 파일이면 인증까지 마친 문서를 연다."""
    doc = fitz.open(path)
    if doc.needs_pass:
        doc.authenticate(password_for(path) or "")
    return doc


def needs_password(path: str) -> bool:
    with fitz.open(path) as doc:
        return bool(doc.needs_pass)


def check_password(path: str, password: str) -> bool:
    with fitz.open(path) as doc:
        return doc.authenticate(password) > 0


class ThumbnailRenderer:
    """(파일, 페이지) -> QPixmap 썸네일. 문서 핸들과 결과를 캐싱한다."""

    def __init__(self, max_width: int = 160) -> None:
        self.max_width = max_width
        self._docs: dict[str, fitz.Document] = {}
        self._cache: dict[tuple[str, float, int, int], QPixmap] = {}

    def _doc(self, path: str) -> fitz.Document:
        doc = self._docs.get(path)
        if doc is None:
            doc = open_doc(path)
            self._docs[path] = doc
        return doc

    def page_size(self, src_path: str, src_index: int) -> tuple[float, float]:
        rect = self._doc(src_path).load_page(src_index).rect
        return rect.width, rect.height

    def render(self, src_path: str, src_index: int, width: int | None = None) -> QPixmap:
        target_w = width or self.max_width
        mtime = Path(src_path).stat().st_mtime
        key = (src_path, mtime, src_index, target_w)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        page = self._doc(src_path).load_page(src_index)
        rect = page.rect
        scale = target_w / rect.width if rect.width else 1.0
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        image = QImage(
            pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
        )
        # QImage 는 pix.samples 버퍼를 참조만 하므로 복사해서 소유권을 가진다.
        pixmap = QPixmap.fromImage(image.copy())
        self._cache[key] = pixmap
        return pixmap

    def close(self) -> None:
        for doc in self._docs.values():
            doc.close()
        self._docs.clear()
        self._cache.clear()


def page_count(path: str) -> int:
    """PDF 페이지 수만 빠르게 얻는다 (렌더링 없음)."""
    with open_doc(path) as doc:
        return doc.page_count


# --- 백그라운드(스레드 풀) 썸네일 렌더링 ---------------------------------
# PyMuPDF 문서 핸들은 스레드 간 공유하면 안전하지 않으므로, 각 워커 스레드가
# 자기만의 문서 핸들을 thread-local 로 열어 재사용한다.

_tls = threading.local()


def _worker_doc(path: str) -> fitz.Document:
    docs: dict[str, fitz.Document] = getattr(_tls, "docs", None)
    if docs is None:
        docs = _tls.docs = {}
    doc = docs.get(path)
    if doc is None:
        doc = docs[path] = open_doc(path)
    return doc


def render_qimage(src_path: str, src_index: int, width: int) -> QImage:
    """워커 스레드에서 호출: QImage(스레드 안전)를 반환. QPixmap 변환은 GUI 스레드에서."""
    page = _worker_doc(src_path).load_page(src_index)
    rect = page.rect
    scale = width / rect.width if rect.width else 1.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
    return image.copy()  # fitz 버퍼와 분리


class ThumbnailSignals(QObject):
    done = Signal(int, QImage)   # (token, 렌더된 이미지)
    failed = Signal(int, str)    # (token, 오류 메시지)


class ThumbnailTask(QRunnable):
    """QThreadPool 에 올려 백그라운드에서 한 페이지를 렌더링하는 작업."""

    def __init__(
        self,
        token: int,
        src_path: str,
        src_index: int,
        width: int,
        signals: ThumbnailSignals,
    ) -> None:
        super().__init__()
        self.token = token
        self.src_path = src_path
        self.src_index = src_index
        self.width = width
        self.signals = signals

    def run(self) -> None:  # noqa: D401
        try:
            image = render_qimage(self.src_path, self.src_index, self.width)
            self.signals.done.emit(self.token, image)
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(self.token, str(e))
