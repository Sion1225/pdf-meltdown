"""PDF 에디터 메인 윈도우."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QSettings, QThreadPool, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QDialog,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
)

from .core import (
    PageRef,
    ReaderCache,
    export_pages,
    split_at_points,
    split_by_chunk,
)
from .i18n import LANGUAGES, tr
from .jobs import ExportSignals, ExportTask
from .render import (
    ThumbnailRenderer,
    ThumbnailSignals,
    ThumbnailTask,
    page_count,
)
from .style import PREVIEW_BG

PAGEREF_ROLE = Qt.UserRole + 1
TOKEN_ROLE = Qt.UserRole + 2
THUMB_BASE_W = 220   # 썸네일 렌더 해상도 (더 크게 보려면 미리보기 패널 사용)
THUMB_MIN = 90       # 표시 최소 너비
THUMB_MAX = 220      # 표시 최대 너비 (= 렌더 해상도)
THUMB_DEFAULT = 150
PREVIEW_W = 1100     # 큰 미리보기 렌더 해상도
PAGE_RATIO = 1.414   # 썸네일 칸 높이 비율(세로형 기준 여유)


class ThumbnailList(QListWidget):
    """Ctrl+휠로 썸네일 확대/축소 요청을 보내는 리스트."""

    zoomRequested = Signal(int)  # +1 확대 / -1 축소

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt 시그니처)
        if event.modifiers() & Qt.ControlModifier:
            self.zoomRequested.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
        else:
            super().wheelEvent(event)


class PreviewLabel(QLabel):
    """원본 픽스맵을 보관하고, 패널 크기에 맞춰 비율 유지 축소 표시."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(220)
        self.setStyleSheet(
            f"background:{PREVIEW_BG}; color:#aab2c0; border:none;"
        )
        self._source: QPixmap | None = None
        self.has_image = False

    def set_source(self, pixmap: QPixmap | None) -> None:
        self._source = pixmap
        self.has_image = pixmap is not None and not pixmap.isNull()
        self._rescale()

    def show_hint(self, text: str) -> None:
        self._source = None
        self.has_image = False
        self.setText(text)

    def _rescale(self) -> None:
        if self._source is None or self._source.isNull():
            return
        scaled = self._source.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 시그니처)
        super().resizeEvent(event)
        self._rescale()


class SplitDialog(QDialog):
    """분할 방식 선택 다이얼로그."""

    def __init__(self, total_pages: int, selected_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr.t("split_dlg_title"))
        self.total_pages = total_pages

        self.chunk_radio = QRadioButton(tr.t("split_chunk"))
        self.chunk_radio.setChecked(True)
        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(1, max(1, total_pages))
        self.chunk_spin.setValue(1)

        self.point_radio = QRadioButton(tr.t("split_points", n=selected_count))
        self.point_radio.setEnabled(selected_count > 0)

        group = QButtonGroup(self)
        group.addButton(self.chunk_radio)
        group.addButton(self.point_radio)

        form = QFormLayout()
        form.addRow(self.chunk_radio, self.chunk_spin)
        form.addRow(self.point_radio)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr.t("split_total", total=total_pages)))
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def use_chunk(self) -> bool:
        return self.chunk_radio.isChecked()

    @property
    def chunk_size(self) -> int:
        return self.chunk_spin.value()


class SettingsDialog(QDialog):
    """설정 버튼으로 여는 다이얼로그: 언어 / 미리보기 위치 선택 (즉시 적용)."""

    def __init__(self, main: "MainWindow") -> None:
        super().__init__(main)
        self.main = main
        self.setMinimumWidth(340)

        self.lbl_lang = QLabel()
        self.cmb_lang = QComboBox()
        for code, name in LANGUAGES:
            self.cmb_lang.addItem(name, code)  # 언어 이름은 원어 그대로
        self.cmb_lang.setCurrentIndex(max(0, self.cmb_lang.findData(tr.lang)))
        self.cmb_lang.currentIndexChanged.connect(self._lang_changed)

        self.lbl_pos = QLabel()
        self.cmb_pos = QComboBox()
        self.cmb_pos.addItem("", "left")
        self.cmb_pos.addItem("", "right")
        self.cmb_pos.setCurrentIndex(0 if main.preview_pos == "left" else 1)
        self.cmb_pos.currentIndexChanged.connect(self._pos_changed)

        self.form = QFormLayout()
        self.form.setContentsMargins(20, 18, 20, 12)
        self.form.setSpacing(14)
        self.form.addRow(self.lbl_lang, self.cmb_lang)
        self.form.addRow(self.lbl_pos, self.cmb_pos)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addWidget(self.buttons)
        self.retranslate()

    def _lang_changed(self, _index: int) -> None:
        self.main.set_language(self.cmb_lang.currentData())
        self.retranslate()  # 다이얼로그 자신도 즉시 갱신

    def _pos_changed(self, _index: int) -> None:
        self.main.set_preview_pos(self.cmb_pos.currentData())

    def retranslate(self) -> None:
        self.setWindowTitle(tr.t("settings_title"))
        self.lbl_lang.setText(tr.t("lbl_language"))
        self.lbl_pos.setText(tr.t("lbl_preview_pos"))
        self.cmb_pos.blockSignals(True)
        self.cmb_pos.setItemText(0, tr.t("preview_left"))
        self.cmb_pos.setItemText(1, tr.t("preview_right"))
        self.cmb_pos.blockSignals(False)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.settings = QSettings("PDFEditorApp", "PDFEditor")
        tr.set_language(str(self.settings.value("language", "ko")))
        self.preview_pos = str(self.settings.value("preview_pos", "left"))

        self.resize(1040, 680)

        self.cache = ReaderCache()
        self.renderer = ThumbnailRenderer(max_width=THUMB_BASE_W)  # 미리보기 전용
        self.thumb_w = THUMB_DEFAULT

        # 백그라운드 썸네일 렌더링
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(
            max(2, min(4, QThreadPool.globalInstance().maxThreadCount()))
        )
        self.thumb_signals = ThumbnailSignals()
        self.thumb_signals.done.connect(self._on_thumb_ready)
        self.thumb_signals.failed.connect(self._on_thumb_failed)

        # 파일 출력 전용 스레드 풀(썸네일 풀과 분리, 순차 실행)
        self.export_pool = QThreadPool(self)
        self.export_pool.setMaxThreadCount(1)
        self._pending: dict[int, QListWidgetItem] = {}
        self._token_seq = 0
        self._load_total = 0
        self._load_done = 0
        self._placeholder = self._make_placeholder()

        self.list = ThumbnailList()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)  # 아이템 위치는 레이아웃이 관리
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setSpacing(8)
        self.list.setWordWrap(True)
        # 대량 항목 성능: 칸 크기가 모두 같다고 알려주면 추가/썸네일 교체 때
        # 전체 레이아웃을 다시 계산하지 않는다. Batched 로 초기 배치도 나눠서 수행.
        self.list.setUniformItemSizes(True)
        self.list.setLayoutMode(QListWidget.Batched)
        self.list.setBatchSize(80)
        self.list.zoomRequested.connect(self._zoom_thumbs)

        self.preview = PreviewLabel()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.list)
        self.splitter.addWidget(self.preview)
        self.setCentralWidget(self.splitter)

        self._apply_thumb_size(self.thumb_w)

        self.list.itemSelectionChanged.connect(self._update_status)
        self.list.currentItemChanged.connect(self._update_preview)
        # 주의: rowsInserted/rowsRemoved 에 상태 갱신을 걸면 대량 추가 시 항목마다
        # 호출되어 느려진다. 페이지 수가 바뀌는 지점(열기/삭제/비우기)에서 직접 갱신한다.

        self._build_toolbar()
        self._build_size_control()

        self.set_preview_pos(self.preview_pos, save=False)
        self.retranslate()

    # ---- UI 구성 ----
    def _build_toolbar(self) -> None:
        tb = QToolBar("tools")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(tb)

        def act(slot, shortcut: str | None = None) -> QAction:
            a = QAction(self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            tb.addAction(a)
            return a

        self.act_open = act(self.open_pdfs, "Ctrl+O")
        tb.addSeparator()
        self.act_extract = act(self.extract_selected, "Ctrl+E")
        self.act_split = act(self.split_document, "Ctrl+Shift+S")
        self.act_save = act(self.save_all, "Ctrl+S")
        tb.addSeparator()
        self.act_remove = act(self.remove_selected, "Delete")
        self.act_clear = act(self.clear_all)

        # 오른쪽 끝으로 설정 버튼을 밀어낼 신축 공백
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.act_settings = act(self.open_settings)

    def _build_size_control(self) -> None:
        """상태바에 로딩 진행률 바와 썸네일 크기 슬라이더를 추가한다."""
        self.progress = QProgressBar()
        self.progress.setFixedWidth(190)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

        self.size_label = QLabel("")
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(THUMB_MIN, THUMB_MAX)
        self.size_slider.setValue(self.thumb_w)
        self.size_slider.setFixedWidth(150)
        self.size_slider.valueChanged.connect(self._apply_thumb_size)

        self.statusBar().addPermanentWidget(self.size_label)
        self.statusBar().addPermanentWidget(self.size_slider)

    # ---- 설정(미리보기 위치 / 언어) ----
    def open_settings(self) -> None:
        SettingsDialog(self).exec()

    def set_preview_pos(self, pos: str, save: bool = True) -> None:
        self.preview_pos = "left" if pos == "left" else "right"
        # insertWidget 은 이미 들어있는 위젯을 해당 위치로 이동시킨다.
        if self.preview_pos == "left":
            self.splitter.insertWidget(0, self.preview)
            self.splitter.setSizes([340, 700])
        else:
            self.splitter.insertWidget(1, self.preview)
            self.splitter.setSizes([700, 340])
        self.splitter.setStretchFactor(self.splitter.indexOf(self.list), 3)
        self.splitter.setStretchFactor(self.splitter.indexOf(self.preview), 2)
        if save:
            self.settings.setValue("preview_pos", self.preview_pos)
            self.settings.sync()  # 즉시 디스크(레지스트리)에 반영

    def set_language(self, code: str) -> None:
        tr.set_language(code)
        self.settings.setValue("language", code)
        self.settings.sync()  # 즉시 디스크(레지스트리)에 반영
        self.retranslate()

    def retranslate(self) -> None:
        """현재 언어로 모든 UI 텍스트를 다시 설정한다."""
        self.setWindowTitle(tr.t("app_title"))
        self.act_open.setText(tr.t("act_open"))
        self.act_extract.setText(tr.t("act_extract"))
        self.act_split.setText(tr.t("act_split"))
        self.act_save.setText(tr.t("act_save"))
        self.act_remove.setText(tr.t("act_remove"))
        self.act_clear.setText(tr.t("act_clear"))
        self.act_settings.setText(tr.t("act_settings"))

        self.size_label.setText(tr.t("lbl_thumb_size"))
        self.size_slider.setToolTip(tr.t("tip_thumb_size"))
        self.progress.setFormat(tr.t("progress_format"))

        if not self.preview.has_image:
            self.preview.show_hint(tr.t("preview_hint"))
        self._update_status()

    # ---- 썸네일 크기 / 미리보기 ----
    def _apply_thumb_size(self, width: int) -> None:
        """표시 크기만 변경한다(저장된 고해상도 썸네일을 축소 표시)."""
        self.thumb_w = max(THUMB_MIN, min(THUMB_MAX, int(width)))
        h = int(self.thumb_w * PAGE_RATIO)
        self.list.setIconSize(QSize(self.thumb_w, h))
        self.list.setGridSize(QSize(self.thumb_w + 24, h + 40))
        if hasattr(self, "size_slider") and self.size_slider.value() != self.thumb_w:
            self.size_slider.blockSignals(True)
            self.size_slider.setValue(self.thumb_w)
            self.size_slider.blockSignals(False)

    def _zoom_thumbs(self, direction: int) -> None:
        self._apply_thumb_size(self.thumb_w + direction * 20)

    def _update_preview(self, current: QListWidgetItem | None, _prev=None) -> None:
        if current is None:
            self.preview.show_hint(tr.t("preview_hint"))
            return
        ref = self._item_ref(current)
        try:
            pix = self.renderer.render(ref.src_path, ref.src_index, width=PREVIEW_W)
            self.preview.set_source(pix)
        except Exception as e:  # noqa: BLE001
            self.preview.show_hint(tr.t("preview_fail", label=ref.label))
            print(f"미리보기 렌더 실패: {ref.label}: {e}")

    # ---- 백그라운드 썸네일 로딩 ----
    def _make_placeholder(self) -> QIcon:
        h = int(THUMB_BASE_W * PAGE_RATIO)
        pix = QPixmap(THUMB_BASE_W, h)
        pix.fill(QColor("#dfe2e8"))
        return QIcon(pix)

    def _add_page_item(self, ref: PageRef) -> None:
        """즉시 placeholder 항목을 추가하고, 실제 썸네일은 백그라운드로 요청한다."""
        token = self._token_seq
        self._token_seq += 1

        item = QListWidgetItem(self._placeholder, ref.label)
        item.setData(PAGEREF_ROLE, (ref.src_path, ref.src_index))
        item.setData(TOKEN_ROLE, token)
        item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self.list.addItem(item)

        self._pending[token] = item
        self._load_total += 1
        self.pool.start(
            ThumbnailTask(
                token, ref.src_path, ref.src_index, THUMB_BASE_W, self.thumb_signals
            )
        )

    def _on_thumb_ready(self, token: int, image) -> None:
        item = self._pending.pop(token, None)
        if item is not None:  # 중간에 삭제되지 않았다면 반영
            item.setIcon(QIcon(QPixmap.fromImage(image)))
        self._load_done += 1
        self._update_progress()

    def _on_thumb_failed(self, token: int, message: str) -> None:
        item = self._pending.pop(token, None)
        if item is not None:
            print(f"썸네일 렌더 실패(token {token}): {message}")
        self._load_done += 1
        self._update_progress()

    def _update_progress(self) -> None:
        if self._load_done >= self._load_total:
            self.progress.hide()
            self._load_total = 0
            self._load_done = 0
            self._update_status()
            return
        self.progress.setRange(0, self._load_total)
        self.progress.setValue(self._load_done)
        if not self.progress.isVisible():
            self.progress.show()

    def _discard_pending(self, item: QListWidgetItem) -> None:
        """삭제되는 항목이 로딩 대기 중이면 집계에서 제외한다."""
        token = item.data(TOKEN_ROLE)
        if token is not None and token in self._pending:
            del self._pending[token]
            self._load_total -= 1

    # ---- 리스트 조작 헬퍼 ----
    def _item_ref(self, item: QListWidgetItem) -> PageRef:
        path, index = item.data(PAGEREF_ROLE)
        return PageRef(path, index)

    def _all_refs(self) -> list[PageRef]:
        return [self._item_ref(self.list.item(i)) for i in range(self.list.count())]

    def _selected_rows(self) -> list[int]:
        return sorted(self.list.row(i) for i in self.list.selectedItems())

    def _update_status(self) -> None:
        n = self.list.count()
        sel = len(self.list.selectedItems())
        self.statusBar().showMessage(tr.t("status_count", n=n, sel=sel))

    # ---- 액션 ----
    def open_pdfs(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr.t("dlg_open_title"), "", tr.t("filter_pdf")
        )
        if not paths:
            return
        added = 0
        self.list.setUpdatesEnabled(False)  # 대량 추가 동안 재그리기 억제
        try:
            for path in paths:
                try:
                    count = page_count(path)  # 렌더링 없이 페이지 수만 (빠름)
                except Exception as e:  # noqa: BLE001
                    QMessageBox.warning(self, tr.t("err_open"), f"{Path(path).name}\n{e}")
                    continue
                for i in range(count):
                    self._add_page_item(PageRef(path, i))  # placeholder 즉시 추가
                    added += 1
        finally:
            self.list.setUpdatesEnabled(True)
        self._update_status()
        if added:
            self._update_progress()  # 썸네일은 백그라운드에서 채워진다

    def _run_export(self, job, err_title: str, on_success) -> None:
        """출력 작업을 백그라운드로 실행하고 진행률 다이얼로그를 띄운다.

        job(report, should_cancel) -> result : jobs.ExportTask 가 호출
        on_success(result) -> None          : 완료 시 메인 스레드에서 호출
        """
        dlg = QProgressDialog(
            tr.t("exporting"), tr.t("cancel"), 0, 100, self
        )
        dlg.setWindowTitle(tr.t("exporting"))
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setMinimumDuration(300)   # 짧은 작업에선 깜빡이지 않게
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)

        signals = ExportSignals()
        task = ExportTask(job, signals)

        def on_progress(done: int, total: int) -> None:
            dlg.setMaximum(max(1, total))
            dlg.setValue(done)

        def finish() -> None:
            dlg.reset()
            dlg.close()

        # 워커 스레드에서 emit 되므로, 메인 스레드에서 슬롯이 실행되도록 큐 연결을 명시한다.
        signals.progress.connect(on_progress, Qt.QueuedConnection)
        signals.finished.connect(
            lambda result: (finish(), on_success(result)), Qt.QueuedConnection
        )
        signals.failed.connect(
            lambda msg: (finish(), QMessageBox.critical(self, err_title, msg)),
            Qt.QueuedConnection,
        )
        signals.cancelled.connect(
            lambda: (finish(), self.statusBar().showMessage(tr.t("msg_cancelled"))),
            Qt.QueuedConnection,
        )
        dlg.canceled.connect(task.cancel)

        # signals 를 self 에 보관해 작업 도중 GC 되지 않도록 한다.
        self._active_export = (signals, task, dlg)

        self.export_pool.start(task)
        dlg.show()

    def extract_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, tr.t("ttl_extract"), tr.t("msg_select_extract"))
            return
        refs = [self._item_ref(self.list.item(r)) for r in rows]
        out, _ = QFileDialog.getSaveFileName(
            self, tr.t("dlg_extract_save"), "extracted.pdf", tr.t("filter_pdf")
        )
        if not out:
            return

        def job(report, should_cancel):
            export_pages(refs, out, ReaderCache(), report, should_cancel)
            return out

        self._run_export(
            job,
            tr.t("err_extract"),
            lambda _r: QMessageBox.information(
                self, tr.t("ttl_done"), tr.t("msg_extracted", n=len(refs), path=out)
            ),
        )

    def save_all(self) -> None:
        refs = self._all_refs()
        if not refs:
            QMessageBox.information(self, tr.t("ttl_save"), tr.t("msg_no_pages_save"))
            return
        out, _ = QFileDialog.getSaveFileName(
            self, tr.t("dlg_save_all"), "merged.pdf", tr.t("filter_pdf")
        )
        if not out:
            return

        def job(report, should_cancel):
            export_pages(refs, out, ReaderCache(), report, should_cancel)
            return out

        self._run_export(
            job,
            tr.t("err_save"),
            lambda _r: QMessageBox.information(
                self, tr.t("ttl_done"), tr.t("msg_saved", n=len(refs), path=out)
            ),
        )

    def split_document(self) -> None:
        refs = self._all_refs()
        if not refs:
            QMessageBox.information(self, tr.t("ttl_split"), tr.t("msg_no_pages_split"))
            return

        selected = self._selected_rows()
        dlg = SplitDialog(len(refs), len(selected), self)
        if dlg.exec() != QDialog.Accepted:
            return

        out_dir = QFileDialog.getExistingDirectory(self, tr.t("dlg_split_dir"))
        if not out_dir:
            return

        use_chunk = dlg.use_chunk
        chunk_size = dlg.chunk_size
        base_name = "split"

        def job(report, should_cancel):
            if use_chunk:
                return split_by_chunk(
                    refs, chunk_size, out_dir, base_name, ReaderCache(),
                    report, should_cancel,
                )
            return split_at_points(
                refs, selected, out_dir, base_name, ReaderCache(),
                report, should_cancel,
            )

        self._run_export(
            job,
            tr.t("err_split"),
            lambda written: QMessageBox.information(
                self, tr.t("ttl_done"), tr.t("msg_split_done", n=len(written), dir=out_dir)
            ),
        )

    def remove_selected(self) -> None:
        for item in self.list.selectedItems():
            self._discard_pending(item)
            self.list.takeItem(self.list.row(item))
        self._update_progress()
        self._update_status()

    def clear_all(self) -> None:
        if self.list.count() == 0:
            return
        if (
            QMessageBox.question(self, tr.t("ttl_clear"), tr.t("msg_clear_confirm"))
            == QMessageBox.Yes
        ):
            self._pending.clear()
            self._load_total = 0
            self._load_done = 0
            self.pool.clear()  # 아직 시작 안 한 작업 취소
            self.list.clear()
            self.progress.hide()
            self._update_status()

    # ---- 이벤트 ----
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 시그니처)
        self._pending.clear()
        self.pool.clear()            # 대기 중 작업 제거
        self.pool.waitForDone(2000)  # 실행 중 작업은 잠시 대기
        self.export_pool.clear()
        self.export_pool.waitForDone(2000)
        self.renderer.close()
        super().closeEvent(event)
