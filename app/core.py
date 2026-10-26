"""PDF 조작 핵심 로직 (GUI 비의존).

핵심 아이디어: 작업 문서는 '페이지 참조(PageRef)'들의 순서 있는 목록이다.
각 PageRef 는 (원본 파일, 원본 페이지 번호) 를 가리킨다.

- 합치기  = 여러 파일의 페이지를 한 목록에 모아 저장
- 정렬    = 목록 순서 변경 후 저장
- 추출    = 선택한 PageRef 들만 새 파일로 저장
- 분할    = 목록을 여러 구간으로 나눠 각각 저장
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pypdf import PdfReader, PdfWriter

# 진행률 콜백: (지금까지 처리한 페이지 수, 전체 페이지 수)
ProgressFn = Callable[[int, int], None]
# 취소 여부 콜백: True 면 작업 중단
CancelFn = Callable[[], bool]


class CancelledError(Exception):
    """사용자가 출력 작업을 취소했을 때 발생."""


@dataclass(frozen=True)
class PageRef:
    """원본 PDF의 특정 페이지에 대한 참조."""

    src_path: str          # 원본 PDF 경로
    src_index: int         # 원본 내 0-기반 페이지 번호

    @property
    def label(self) -> str:
        return f"{Path(self.src_path).name} p.{self.src_index + 1}"


class ReaderCache:
    """같은 파일을 반복해서 열지 않도록 PdfReader 를 캐싱."""

    def __init__(self) -> None:
        self._readers: dict[str, PdfReader] = {}

    def get(self, path: str) -> PdfReader:
        reader = self._readers.get(path)
        if reader is None:
            reader = PdfReader(path)
            self._readers[path] = reader
        return reader

    def page_count(self, path: str) -> int:
        return len(self.get(path).pages)


def load_page_refs(path: str, cache: ReaderCache | None = None) -> list[PageRef]:
    """PDF 파일의 모든 페이지에 대한 PageRef 목록을 만든다."""
    cache = cache or ReaderCache()
    count = cache.page_count(path)
    return [PageRef(path, i) for i in range(count)]


def export_pages(
    pages: list[PageRef],
    out_path: str,
    cache: ReaderCache | None = None,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> None:
    """주어진 순서의 PageRef 목록을 하나의 PDF 로 저장한다 (합치기/정렬/추출 공통)."""
    if not pages:
        raise ValueError("저장할 페이지가 없습니다.")

    cache = cache or ReaderCache()
    writer = PdfWriter()
    total = len(pages)
    for i, ref in enumerate(pages, start=1):
        if should_cancel and should_cancel():
            raise CancelledError()
        reader = cache.get(ref.src_path)
        writer.add_page(reader.pages[ref.src_index])
        if progress:
            progress(i, total)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)


def split_by_chunk(
    pages: list[PageRef],
    chunk_size: int,
    out_dir: str,
    base_name: str,
    cache: ReaderCache | None = None,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> list[str]:
    """N페이지씩 끊어서 여러 파일로 분할. 생성된 파일 경로 목록을 반환."""
    if chunk_size < 1:
        raise ValueError("묶음 크기는 1 이상이어야 합니다.")

    groups = [pages[i : i + chunk_size] for i in range(0, len(pages), chunk_size)]
    return _write_groups(groups, out_dir, base_name, cache, progress, should_cancel)


def split_at_points(
    pages: list[PageRef],
    split_before: list[int],
    out_dir: str,
    base_name: str,
    cache: ReaderCache | None = None,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> list[str]:
    """지정한 위치(해당 인덱스 '앞'에서 끊음) 기준으로 분할.

    split_before: 0-기반 페이지 인덱스 목록. 예) [3, 5] -> [0:3], [3:5], [5:]
    """
    cut = sorted({p for p in split_before if 0 < p < len(pages)})
    bounds = [0, *cut, len(pages)]
    groups = [pages[bounds[i] : bounds[i + 1]] for i in range(len(bounds) - 1)]
    groups = [g for g in groups if g]
    return _write_groups(groups, out_dir, base_name, cache, progress, should_cancel)


def _write_groups(
    groups: list[list[PageRef]],
    out_dir: str,
    base_name: str,
    cache: ReaderCache | None,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> list[str]:
    cache = cache or ReaderCache()
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)

    total = sum(len(g) for g in groups)
    done = 0
    written: list[str] = []
    width = max(2, len(str(len(groups))))
    for idx, group in enumerate(groups, start=1):
        writer = PdfWriter()
        for ref in group:
            if should_cancel and should_cancel():
                # 취소 시 이미 만든 파일들을 정리
                for p in written:
                    Path(p).unlink(missing_ok=True)
                raise CancelledError()
            writer.add_page(cache.get(ref.src_path).pages[ref.src_index])
            done += 1
            if progress:
                progress(done, total)

        out_path = out_dir_p / f"{base_name}_part{idx:0{width}d}.pdf"
        with open(out_path, "wb") as f:
            writer.write(f)
        written.append(str(out_path))
    return written
