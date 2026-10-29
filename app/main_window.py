"""PDF Meltdown 메인 윈도우."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QSettings, QThreadPool, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
)

from .core import (
    A4,
    PageRef,
    ReaderCache,
    export_pages,
    set_password,
    split_at_points,
    split_by_chunk,
)
from .convert import ConvertOptions, convert_pdf, ocr_available
from .dialogs import ImageExportDialog, SaveOptionsDialog
from .i18n import LANGUAGES, tr
from .images import IMAGE_EXTS, export_page_images, image_to_pdf, is_image
from .jobs import ExportSignals, ExportTask
from .postprocess import postprocess
from .render import (
    ThumbnailRenderer,
    ThumbnailSignals,
    ThumbnailTask,
    check_password,
    needs_password,
    page_count,
)
from .style import PREVIEW_BG

PAGEREF_ROLE = Qt.UserRole + 1
THUMB_BASE_W = 220   # 썸네일 렌더 해상도 (더 크게 보려면 미리보기 패널 사용)
THUMB_MIN = 90       # 표시 최소 너비
THUMB_MAX = 220      # 표시 최대 너비 (= 렌더 해상도)
THUMB_DEFAULT = 150
PREVIEW_W = 1100     # 큰 미리보기 렌더 해상도
PAGE_RATIO = 1.414   # 썸네일 칸 높이 비율(세로형 기준 여유)
UNDO_LIMIT = 100     # 되돌리기 최대 단계


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _rotate(pix: QPixmap, degrees: int) -> QPixmap:
    """썸네일/미리보기 표시용 회전(시계 방향)."""
    if not degrees:
        return pix
    return pix.transformed(QTransform().rotate(degrees), Qt.SmoothTransformation)


def dropped_files(event) -> list[str]:
    """드래그&드롭 이벤트에서 열 수 있는(PDF·이미지) 로컬 파일 경로만 추린다."""
    md = event.mimeData()
    if not md.hasUrls():
        return []
    paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
    return [p for p in paths if p.lower().endswith(".pdf") or is_image(p)]


class ThumbnailList(QListWidget):
    """Ctrl+휠 확대/축소 요청과, 탐색기에서 끌어다 놓은 파일을 알려주는 리스트."""

    zoomRequested = Signal(int)          # +1 확대 / -1 축소
    filesDropped = Signal(list, int)     # (파일 경로들, 놓은 위치 행 / 끝이면 -1)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt 시그니처)
        if event.modifiers() & Qt.ControlModifier:
            self.zoomRequested.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
        else:
            super().wheelEvent(event)

    # 내부 드래그(순서 변경)는 기본 동작에 맡기고, 외부 파일만 가로챈다.
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.source() is not self and dropped_files(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.source() is not self and dropped_files(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        files = dropped_files(event) if event.source() is not self else []
        if files:
            event.acceptProposedAction()
            self.filesDropped.emit(files, self.indexAt(event.position().toPoint()).row())
        else:
            super().dropEvent(event)


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


class ConvertDialog(QDialog):
    """PDF → Markdown 변환 옵션. 마지막 선택값을 QSettings 에 기억한다."""

    def __init__(self, settings: QSettings, total: int, selected: int, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(tr.t("convert_title"))
        self.setMinimumWidth(440)
        self._ocr_ok = ocr_available()

        self.cmb_scope = QComboBox()
        self.cmb_scope.addItem(tr.t("conv_scope_all", n=total), "all")
        self.cmb_scope.addItem(tr.t("conv_scope_selected", n=selected), "selected")
        if selected:
            self.cmb_scope.setCurrentIndex(1)
        else:
            self.cmb_scope.model().item(1).setEnabled(False)

        self.cmb_ocr = self._combo(
            [("auto", "conv_ocr_auto"), ("off", "conv_ocr_off"), ("force", "conv_ocr_force")],
            "convert/ocr_mode", "auto",
        )
        self.cmb_quality = self._combo(
            [("fast", "conv_quality_fast"), ("accurate", "conv_quality_accurate")],
            "convert/ocr_quality", "fast",
        )
        saved_langs = str(settings.value("convert/ocr_langs", "ko,ja,en")).split(",")
        self.lang_checks: dict[str, QCheckBox] = {}
        lang_row = QHBoxLayout()
        for code, name in LANGUAGES:  # 언어 이름은 원어 그대로
            cb = QCheckBox(name)
            cb.setChecked(code in saved_langs)
            self.lang_checks[code] = cb
            lang_row.addWidget(cb)
        lang_row.addStretch(1)

        self.cmb_images = self._combo(
            [("folder", "conv_img_folder"), ("embed", "conv_img_embed"), ("none", "conv_img_none")],
            "convert/image_mode", "folder",
        )
        self.chk_attach = QCheckBox(tr.t("conv_attach_scan"))
        self.chk_attach.setChecked(settings.value("convert/attach_scan", False, type=bool))
        self.chk_sep = QCheckBox(tr.t("conv_separators"))
        self.chk_sep.setChecked(settings.value("convert/separators", False, type=bool))
        self.chk_formulas = QCheckBox(tr.t("conv_formulas"))
        self.chk_formulas.setChecked(settings.value("convert/formulas", False, type=bool))
        self.chk_formulas.setEnabled(self._ocr_ok)  # 수식 모델도 OCR 엔진(xberg)에 들어 있다

        note = QLabel(tr.t("conv_note") if self._ocr_ok else tr.t("conv_ocr_missing"))
        note.setWordWrap(True)
        note.setStyleSheet("color: #73726B;")
        if not self._ocr_ok:
            self.cmb_ocr.setCurrentIndex(self.cmb_ocr.findData("off"))
            self.cmb_ocr.setEnabled(False)

        form = QFormLayout()
        form.setContentsMargins(20, 18, 20, 8)
        form.setSpacing(12)
        form.addRow(tr.t("conv_scope"), self.cmb_scope)
        form.addRow(tr.t("conv_ocr"), self.cmb_ocr)
        form.addRow(tr.t("conv_quality"), self.cmb_quality)
        form.addRow(tr.t("conv_langs"), lang_row)
        form.addRow(tr.t("conv_images"), self.cmb_images)
        form.addRow("", self.chk_attach)
        form.addRow("", self.chk_formulas)
        form.addRow("", self.chk_sep)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

        self.cmb_ocr.currentIndexChanged.connect(self._sync_enabled)
        self._sync_enabled()

    def _combo(self, items: list[tuple[str, str]], key: str, default: str) -> QComboBox:
        cmb = QComboBox()
        for value, label_key in items:
            cmb.addItem(tr.t(label_key), value)
        cmb.setCurrentIndex(max(0, cmb.findData(str(self.settings.value(key, default)))))
        return cmb

    def _sync_enabled(self) -> None:
        ocr_on = self._ocr_ok and self.cmb_ocr.currentData() != "off"
        for w in (self.cmb_quality, self.chk_attach, *self.lang_checks.values()):
            w.setEnabled(ocr_on)

    def _accept(self) -> None:
        if self.cmb_ocr.currentData() != "off" and not self.languages:
            QMessageBox.warning(self, self.windowTitle(), tr.t("msg_need_lang"))
            return
        s = self.settings
        s.setValue("convert/ocr_mode", self.cmb_ocr.currentData())
        s.setValue("convert/ocr_quality", self.cmb_quality.currentData())
        s.setValue("convert/ocr_langs", ",".join(self.languages))
        s.setValue("convert/image_mode", self.cmb_images.currentData())
        s.setValue("convert/attach_scan", self.chk_attach.isChecked())
        s.setValue("convert/separators", self.chk_sep.isChecked())
        s.setValue("convert/formulas", self.chk_formulas.isChecked())
        s.sync()
        self.accept()

    @property
    def use_selected(self) -> bool:
        return self.cmb_scope.currentData() == "selected"

    @property
    def languages(self) -> tuple[str, ...]:
        # 현재 UI 언어를 먼저 시도하도록 정렬(OCR 언어 판별 시 첫 후보가 됨)
        codes = [c for c in self.lang_checks if self.lang_checks[c].isChecked()]
        return tuple(sorted(codes, key=lambda c: c != tr.lang))

    def options(self) -> ConvertOptions:
        return ConvertOptions(
            ocr_mode=self.cmb_ocr.currentData(),
            ocr_quality=self.cmb_quality.currentData(),
            ocr_languages=self.languages,
            image_mode=self.cmb_images.currentData(),
            attach_scan_images=self.chk_attach.isChecked(),
            page_separators=self.chk_sep.isChecked(),
            formulas=self.chk_formulas.isEnabled() and self.chk_formulas.isChecked(),
        )


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

        # 썸네일: (파일, 페이지) 별로 한 번만 렌더링해 캐시하고(회전 전 원본), 같은 페이지를
        # 기다리는 항목(복제·되돌리기로 다시 만든 항목 등)은 진행 중인 작업 하나를 함께 기다린다.
        self._thumbs: dict[tuple[str, int], QPixmap] = {}
        self._inflight: dict[tuple[str, int], int] = {}      # key -> token
        self._token_key: dict[int, tuple[str, int]] = {}     # token -> key
        self._pending: dict[int, list[QListWidgetItem]] = {}  # token -> 기다리는 항목들
        self._token_seq = 0
        self._load_total = 0
        self._placeholder = self._make_placeholder()
        self._blank_icons: dict[tuple[float, float], QPixmap] = {}

        # 되돌리기: 목록 상태(PageRef 순서 목록) 스냅샷
        self._state: list[PageRef] = []
        self._undo: list[list[PageRef]] = []
        self._redo: list[list[PageRef]] = []
        self._commit_scheduled = False

        # 이미지 → PDF 변환 결과를 담는 세션 임시 폴더, 화면에 보일 원래 파일 이름
        self._tmpdir = tempfile.mkdtemp(prefix="pdfeditor_")
        self._display_names: dict[str, str] = {}

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
        self.list.filesDropped.connect(self.add_files)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_context_menu)
        self.setAcceptDrops(True)  # 미리보기·툴바 쪽에 놓아도 열리게

        self.preview = PreviewLabel()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.list)
        self.splitter.addWidget(self.preview)
        self.setCentralWidget(self.splitter)

        self._apply_thumb_size(self.thumb_w)

        self.list.itemSelectionChanged.connect(self._update_status)
        self.list.currentItemChanged.connect(self._update_preview)
        # 행 변화(열기·삭제·드래그 정렬 등)는 이벤트 루프 한 바퀴에 한 번만 되돌리기 기록에
        # 반영한다. 대량 추가 시 항목마다 무거운 작업을 하지 않도록 예약만 한다.
        model = self.list.model()
        model.rowsInserted.connect(self._schedule_commit)
        model.rowsRemoved.connect(self._schedule_commit)
        model.rowsMoved.connect(self._schedule_commit)

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

        def act(slot, shortcut=None, *, on_toolbar: bool = True) -> QAction:
            a = QAction(self)
            a.triggered.connect(slot)
            if shortcut is not None:
                a.setShortcut(QKeySequence(shortcut))
            # 메뉴 안의 동작도 단축키가 듣도록 창에 등록한다.
            self.addAction(a)
            if on_toolbar:
                tb.addAction(a)
            return a

        def menu_button(actions: list[QAction | None]) -> tuple[QToolButton, QMenu]:
            menu = QMenu(self)
            for a in actions:
                menu.addSeparator() if a is None else menu.addAction(a)
            btn = QToolButton()
            btn.setMenu(menu)
            btn.setPopupMode(QToolButton.InstantPopup)
            tb.addWidget(btn)
            return btn, menu

        self.act_open = act(self.open_pdfs, "Ctrl+O")
        tb.addSeparator()
        self.act_undo = act(self.undo, QKeySequence.Undo)
        self.act_redo = act(self.redo, QKeySequence.Redo)
        tb.addSeparator()
        self.act_rot_left = act(lambda: self.rotate_selected(-90), "Ctrl+L")
        self.act_rot_right = act(lambda: self.rotate_selected(90), "Ctrl+R")

        self.act_insert_blank = act(self.insert_blank_page, "Ctrl+B", on_toolbar=False)
        self.act_duplicate = act(self.duplicate_selected, "Ctrl+D", on_toolbar=False)
        self.act_remove = act(self.remove_selected, "Delete", on_toolbar=False)
        self.act_clear = act(self.clear_all, on_toolbar=False)
        self.btn_pages, self.menu_pages = menu_button(
            [self.act_insert_blank, self.act_duplicate, None, self.act_remove, self.act_clear]
        )
        tb.addSeparator()

        self.act_save = act(self.save_all, "Ctrl+S")
        self.act_save_adv = act(self.save_advanced, "Ctrl+Shift+E", on_toolbar=False)
        self.act_extract = act(self.extract_selected, "Ctrl+E", on_toolbar=False)
        self.act_split = act(self.split_document, "Ctrl+Shift+S", on_toolbar=False)
        self.act_export_images = act(self.export_images, on_toolbar=False)
        self.act_convert = act(self.convert_markdown, "Ctrl+M", on_toolbar=False)
        self.btn_export, self.menu_export = menu_button(
            [self.act_save_adv, None, self.act_extract, self.act_split, None,
             self.act_export_images, self.act_convert]
        )

        # 오른쪽 끝으로 설정 버튼을 밀어낼 신축 공백
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.act_settings = act(self.open_settings)
        self._update_undo_actions()

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
        for a, key in (
            (self.act_open, "act_open"), (self.act_undo, "act_undo"), (self.act_redo, "act_redo"),
            (self.act_rot_left, "act_rot_left"), (self.act_rot_right, "act_rot_right"),
            (self.act_insert_blank, "act_insert_blank"), (self.act_duplicate, "act_duplicate"),
            (self.act_remove, "act_remove"), (self.act_clear, "act_clear"),
            (self.act_save, "act_save"), (self.act_save_adv, "act_save_adv"),
            (self.act_extract, "act_extract"), (self.act_split, "act_split"),
            (self.act_export_images, "act_export_images"), (self.act_convert, "act_convert"),
            (self.act_settings, "act_settings"),
        ):
            a.setText(tr.t(key))
        # 툴바에는 짧은 이름, 전체 이름은 툴팁으로
        for a, short, full in (
            (self.act_open, "tb_open", "act_open"),
            (self.act_rot_left, "tb_rot_left", "act_rot_left"),
            (self.act_rot_right, "tb_rot_right", "act_rot_right"),
            (self.act_save, "tb_save", "act_save"),
        ):
            a.setIconText(tr.t(short))
            a.setToolTip(tr.t(full))
        self.btn_pages.setText(tr.t("menu_pages") + " ▾")
        self.btn_export.setText(tr.t("menu_export") + " ▾")

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
            if ref.is_blank:
                pix = self._blank_pixmap(ref.blank_size, PREVIEW_W)
            else:
                pix = _rotate(self.renderer.render(ref.src_path, ref.src_index, width=PREVIEW_W),
                              ref.rotation)
            self.preview.set_source(pix)
        except Exception as e:  # noqa: BLE001
            self.preview.show_hint(tr.t("preview_fail", label=self._label(ref)))
            print(f"미리보기 렌더 실패: {self._label(ref)}: {e}")

    # ---- 썸네일(캐시 + 백그라운드 로딩) ----
    def _make_placeholder(self) -> QIcon:
        h = int(THUMB_BASE_W * PAGE_RATIO)
        pix = QPixmap(THUMB_BASE_W, h)
        pix.fill(QColor("#dfe2e8"))
        return QIcon(pix)

    def _blank_pixmap(self, size: tuple[float, float], width: int) -> QPixmap:
        """빈 페이지 그림: 흰 바탕에 옅은 테두리, 페이지 비율 유지."""
        key = (size[0], size[1], width)
        pix = self._blank_icons.get(key)
        if pix is None:
            h = max(1, round(width * size[1] / size[0]))
            pix = QPixmap(width, h)
            pix.fill(QColor("#ffffff"))
            p = QPainter(pix)
            p.setPen(QColor("#d6d3c9"))
            p.drawRect(0, 0, width - 1, h - 1)
            p.end()
            self._blank_icons[key] = pix
        return pix

    def _label(self, ref: PageRef) -> str:
        if ref.is_blank:
            return tr.t("blank_page")
        name = self._display_names.get(ref.src_path)
        if name is not None:  # 이미지에서 만든 한 장짜리 PDF
            return name
        return ref.label

    def _apply_icon(self, item: QListWidgetItem) -> None:
        """항목의 현재 PageRef(회전 포함)에 맞는 아이콘을 즉시 설정하거나 렌더링을 요청한다."""
        ref = self._item_ref(item)
        if ref.is_blank:
            item.setIcon(QIcon(self._blank_pixmap(ref.blank_size, THUMB_BASE_W)))
            return
        key = (ref.src_path, ref.src_index)
        base = self._thumbs.get(key)
        if base is not None:
            item.setIcon(QIcon(_rotate(base, ref.rotation)))
            return
        item.setIcon(self._placeholder)
        token = self._inflight.get(key)
        if token is None:
            token = self._token_seq
            self._token_seq += 1
            self._inflight[key] = token
            self._token_key[token] = key
            self._load_total += 1
            self.pool.start(
                ThumbnailTask(token, ref.src_path, ref.src_index, THUMB_BASE_W, self.thumb_signals)
            )
        self._pending.setdefault(token, []).append(item)

    def _add_page_item(self, ref: PageRef, row: int | None = None) -> QListWidgetItem:
        """항목을 즉시 추가한다(썸네일은 캐시에 있으면 바로, 없으면 백그라운드로)."""
        item = QListWidgetItem(self._label(ref))
        item.setData(PAGEREF_ROLE, ref)
        item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        if row is None or row < 0:
            self.list.addItem(item)
        else:
            self.list.insertItem(row, item)
        self._apply_icon(item)
        return item

    def _on_thumb_ready(self, token: int, image) -> None:
        key = self._token_key.pop(token, None)
        pix = QPixmap.fromImage(image)
        if key is not None:
            self._thumbs[key] = pix
            self._inflight.pop(key, None)
        for item in self._pending.pop(token, []):
            try:
                item.setIcon(QIcon(_rotate(pix, self._item_ref(item).rotation)))
            except RuntimeError:  # 기다리는 동안 목록에서 지워진 항목
                pass
        self._update_progress()

    def _on_thumb_failed(self, token: int, message: str) -> None:
        key = self._token_key.pop(token, None)
        if key is not None:
            self._inflight.pop(key, None)
            print(f"썸네일 렌더 실패 {key}: {message}")
        self._pending.pop(token, None)
        self._update_progress()

    def _update_progress(self) -> None:
        if not self._inflight:
            self.progress.hide()
            self._load_total = 0
            self._update_status()
            return
        self.progress.setRange(0, self._load_total)
        self.progress.setValue(self._load_total - len(self._inflight))
        if not self.progress.isVisible():
            self.progress.show()

    def _forget_pending_items(self) -> None:
        """목록을 통째로 다시 만들 때: 기다리던 항목 참조만 버린다(렌더링은 계속 → 캐시에 남음)."""
        self._pending.clear()

    # ---- 리스트 조작 헬퍼 ----
    def _item_ref(self, item: QListWidgetItem) -> PageRef:
        return item.data(PAGEREF_ROLE)

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
        patterns = " ".join(["*.pdf", *(f"*{e}" for e in IMAGE_EXTS)])
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr.t("dlg_open_title"), "", f"{tr.t('filter_open')} ({patterns})"
        )
        if paths:
            self.add_files(paths)

    def add_files(self, paths: list[str], row: int = -1) -> None:
        """PDF·이미지 파일을 목록에 추가한다. row 가 0 이상이면 그 위치에 끼워 넣는다."""
        refs: list[PageRef] = []
        unlocked = False
        for path in paths:
            try:
                if is_image(path):
                    pdf = image_to_pdf(path, self._tmpdir)
                    self._display_names[pdf] = Path(path).name
                    refs.append(PageRef(pdf, 0))
                    continue
                if needs_password(path):
                    if not self._ask_password(path):
                        continue
                    unlocked = True
                count = page_count(path)  # 렌더링 없이 페이지 수만 (빠름)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, tr.t("err_open"), f"{Path(path).name}\n{e}")
                continue
            refs.extend(PageRef(path, i) for i in range(count))
        if not refs:
            return

        self.list.setUpdatesEnabled(False)  # 대량 추가 동안 재그리기 억제
        try:
            for i, ref in enumerate(refs):
                self._add_page_item(ref, row + i if row >= 0 else None)
        finally:
            self.list.setUpdatesEnabled(True)
        self._update_status()
        self._update_progress()  # 썸네일은 백그라운드에서 채워진다
        if unlocked:
            self.statusBar().showMessage(tr.t("msg_unlocked"), 8000)

    def _ask_password(self, path: str) -> bool:
        prompt = tr.t("pw_prompt", name=Path(path).name)
        for _ in range(3):
            pw, ok = QInputDialog.getText(self, tr.t("pw_title"), prompt, QLineEdit.Password)
            if not ok:
                return False
            if check_password(path, pw):
                set_password(path, pw)
                return True
            prompt = tr.t("pw_wrong") + "\n\n" + tr.t("pw_prompt", name=Path(path).name)
        return False

    # ---- 페이지 편집 ----
    def _target_items(self) -> list[QListWidgetItem]:
        """선택된 항목(목록 순서). 선택이 없으면 현재 항목."""
        items = sorted(self.list.selectedItems(), key=self.list.row)
        if not items and self.list.currentItem() is not None:
            items = [self.list.currentItem()]
        return items

    def rotate_selected(self, delta: int) -> None:
        items = self._target_items()
        if not items:
            return
        for item in items:
            item.setData(PAGEREF_ROLE, self._item_ref(item).rotated(delta))
            self._apply_icon(item)
        self._commit()  # 데이터만 바뀌어 행 신호가 없으므로 직접 기록
        if self.list.currentItem() in items:
            self._update_preview(self.list.currentItem())

    def insert_blank_page(self) -> None:
        items = self._target_items()
        size = A4
        if items:
            ref = self._item_ref(items[-1])
            if ref.is_blank:
                size = ref.blank_size
            else:
                w, h = self.renderer.page_size(ref.src_path, ref.src_index)
                size = (h, w) if ref.rotation in (90, 270) else (w, h)
        row = self.list.row(items[-1]) + 1 if items else self.list.count()
        item = self._add_page_item(PageRef.blank(size), row)
        self._select_only([item])
        self._update_status()

    def duplicate_selected(self) -> None:
        items = self._target_items()
        if not items:
            return
        row = self.list.row(items[-1]) + 1
        copies = [self._add_page_item(self._item_ref(it), row + i) for i, it in enumerate(items)]
        self._select_only(copies)
        self._update_status()
        self._update_progress()

    def _select_only(self, items: list[QListWidgetItem]) -> None:
        self.list.clearSelection()
        for it in items:
            it.setSelected(True)
        self.list.setCurrentItem(items[0])
        self.list.scrollToItem(items[0])

    def _show_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is not None and not item.isSelected():
            self._select_only([item])
        menu = QMenu(self)
        for a in (self.act_rot_left, self.act_rot_right, None, self.act_duplicate,
                  self.act_insert_blank, None, self.act_extract, self.act_remove):
            menu.addSeparator() if a is None else menu.addAction(a)
        menu.exec(self.list.viewport().mapToGlobal(pos))

    # ---- 되돌리기 / 다시 실행 ----
    def _snapshot(self) -> list[PageRef]:
        return self._all_refs()

    def _schedule_commit(self, *_args) -> None:
        if not self._commit_scheduled:
            self._commit_scheduled = True
            QTimer.singleShot(0, self._commit)

    def _commit(self) -> None:
        """현재 목록이 마지막 기록과 다르면 이전 상태를 되돌리기 스택에 쌓는다."""
        self._commit_scheduled = False
        current = self._snapshot()
        if current == self._state:
            return
        self._undo.append(self._state)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self._state = current
        self._update_undo_actions()

    def undo(self) -> None:
        self._commit()  # 아직 기록 안 된 변경이 있으면 먼저 반영
        if self._undo:
            self._redo.append(self._state)
            self._restore(self._undo.pop())

    def redo(self) -> None:
        self._commit()
        if self._redo:
            self._undo.append(self._state)
            self._restore(self._redo.pop())

    def _restore(self, state: list[PageRef]) -> None:
        self._state = state  # 다시 만드는 동안의 행 신호가 새 기록으로 잡히지 않게 먼저 맞춘다
        scroll = self.list.verticalScrollBar().value()
        self.list.setUpdatesEnabled(False)
        try:
            self._forget_pending_items()
            self.list.clear()
            for ref in state:
                self._add_page_item(ref)
        finally:
            self.list.setUpdatesEnabled(True)
        self.list.verticalScrollBar().setValue(scroll)
        self._update_undo_actions()
        self._update_status()
        self._update_progress()

    def _update_undo_actions(self) -> None:
        self.act_undo.setEnabled(bool(self._undo))
        self.act_redo.setEnabled(bool(self._redo))

    # ---- 창에 끌어다 놓기 ----
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if dropped_files(event):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        files = dropped_files(event)
        if files:
            event.acceptProposedAction()
            self.add_files(files)

    def _run_export(self, job, err_title: str, on_success, label: str | None = None) -> None:
        """출력 작업을 백그라운드로 실행하고 진행률 다이얼로그를 띄운다.

        job(report, should_cancel) -> result : jobs.ExportTask 가 호출
        on_success(result) -> None          : 완료 시 메인 스레드에서 호출
        """
        label = label or tr.t("exporting")
        dlg = QProgressDialog(label, tr.t("cancel"), 0, 100, self)
        dlg.setWindowTitle(label)
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

    def convert_markdown(self) -> None:
        all_refs = self._all_refs()
        if not all_refs:
            QMessageBox.information(self, tr.t("ttl_convert"), tr.t("msg_no_pages_convert"))
            return

        selected = self._selected_rows()
        dlg = ConvertDialog(self.settings, len(all_refs), len(selected), self)
        if dlg.exec() != QDialog.Accepted:
            return
        refs = (
            [self._item_ref(self.list.item(r)) for r in selected] if dlg.use_selected else all_refs
        )
        opts = dlg.options()

        out, _ = QFileDialog.getSaveFileName(
            self, tr.t("dlg_convert_save"), f"{self._default_stem(refs)}.md", tr.t("filter_md")
        )
        if not out:
            return
        if not out.lower().endswith(".md"):
            out += ".md"

        def job(report, should_cancel):
            # 현재 목록 순서/선택대로 임시 PDF 를 만든 뒤 변환한다. 진행률: 준비 10% + 변환 90%
            n = len(refs)
            with tempfile.TemporaryDirectory(prefix="pdfmd_") as tmp:
                src = str(Path(tmp) / "input.pdf")
                export_pages(refs, src, ReaderCache(), lambda d, _t: report(d, n * 10), should_cancel)
                return convert_pdf(
                    src, out, opts, lambda d, _t: report(n + d * 9, n * 10), should_cancel
                )

        def done(result) -> None:
            msg = tr.t(
                "msg_converted", n=result.pages, ocr=result.ocr_pages, img=result.images,
                path=result.md_path,
            )
            if result.formulas:
                msg += "\n" + tr.t("conv_formulas_done", n=result.formulas)
            if "ocr_unavailable" in result.warnings:
                msg += "\n\n" + tr.t("conv_ocr_skipped")
            QMessageBox.information(self, tr.t("ttl_done"), msg)

        self._run_export(job, tr.t("err_convert"), done, label=tr.t("converting"))

    def save_advanced(self) -> None:
        all_refs = self._all_refs()
        if not all_refs:
            QMessageBox.information(self, tr.t("ttl_save"), tr.t("msg_no_pages_save"))
            return
        selected = self._selected_rows()
        dlg = SaveOptionsDialog(self.settings, len(all_refs), len(selected), self)
        if dlg.exec() != QDialog.Accepted:
            return
        refs = [self._item_ref(self.list.item(r)) for r in selected] if dlg.use_selected else all_refs
        opts = dlg.options()
        out, _ = QFileDialog.getSaveFileName(
            self, tr.t("save_opts_title"), f"{self._default_stem(refs)}.pdf", tr.t("filter_pdf")
        )
        if not out:
            return

        def job(report, should_cancel):
            n = len(refs)
            if opts.is_plain:
                export_pages(refs, out, ReaderCache(), report, should_cancel)
                return out
            # 페이지 모으기(앞 절반) → 압축·쪽번호·워터마크·암호(뒤 절반)
            with tempfile.TemporaryDirectory(prefix="pdfsave_") as tmp:
                src = str(Path(tmp) / "merged.pdf")
                export_pages(refs, src, ReaderCache(), lambda d, _t: report(d, n * 2), should_cancel)
                postprocess(src, out, opts, lambda d, _t: report(n + d, n * 2), should_cancel)
            return out

        self._run_export(
            job,
            tr.t("err_save"),
            lambda path: QMessageBox.information(
                self, tr.t("ttl_done"),
                tr.t("msg_saved_adv", n=len(refs), size=_human_size(Path(path).stat().st_size),
                     path=path),
            ),
        )

    def export_images(self) -> None:
        all_refs = self._all_refs()
        if not all_refs:
            QMessageBox.information(self, tr.t("img_export_title"), tr.t("msg_no_pages"))
            return
        selected = self._selected_rows()
        dlg = ImageExportDialog(self.settings, len(all_refs), len(selected), self)
        if dlg.exec() != QDialog.Accepted:
            return
        refs = [self._item_ref(self.list.item(r)) for r in selected] if dlg.use_selected else all_refs
        out_dir = QFileDialog.getExistingDirectory(self, tr.t("dlg_img_dir"))
        if not out_dir:
            return
        fmt, dpi, base = dlg.fmt, dlg.dpi, self._default_stem(refs)

        def job(report, should_cancel):
            return export_page_images(refs, out_dir, base, fmt, dpi, report, should_cancel)

        self._run_export(
            job,
            tr.t("img_export_title"),
            lambda written: QMessageBox.information(
                self, tr.t("ttl_done"), tr.t("msg_images_done", n=len(written), dir=out_dir)
            ),
        )

    def _default_stem(self, refs: list[PageRef]) -> str:
        """저장 대화상자의 기본 파일 이름: 첫 번째 실제 페이지의 원래 파일 이름."""
        for ref in refs:
            if not ref.is_blank:
                return Path(self._display_names.get(ref.src_path, ref.src_path)).stem
        return "document"

    def remove_selected(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._update_status()

    def clear_all(self) -> None:
        if self.list.count() == 0:
            return
        if (
            QMessageBox.question(self, tr.t("ttl_clear"), tr.t("msg_clear_confirm"))
            == QMessageBox.Yes
        ):
            self._cancel_thumbnail_loading()
            self.list.clear()  # 되돌리기로 복구 가능
            self._update_status()

    def _cancel_thumbnail_loading(self) -> None:
        """아직 시작 안 한 썸네일 작업을 버린다(되돌리기로 다시 필요해지면 새로 요청됨)."""
        self.pool.clear()
        self._pending.clear()
        self._inflight.clear()
        self._token_key.clear()
        self._update_progress()

    # ---- 이벤트 ----
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 시그니처)
        self._cancel_thumbnail_loading()
        self.pool.waitForDone(2000)  # 실행 중 작업은 잠시 대기
        self.export_pool.clear()
        self.export_pool.waitForDone(2000)
        self.renderer.close()
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        super().closeEvent(event)
