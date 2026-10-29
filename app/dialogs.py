"""고급 저장 / 이미지로 내보내기 다이얼로그. 마지막 선택값을 QSettings 에 기억한다(암호 제외)."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from .i18n import tr
from .postprocess import COMPRESS_LEVELS, NUMBER_FORMATS, NUMBER_POSITIONS, SaveOptions


def scope_combo(total: int, selected: int) -> QComboBox:
    """전체/선택 페이지 범위 콤보. 선택이 있으면 '선택'이 기본."""
    cmb = QComboBox()
    cmb.addItem(tr.t("conv_scope_all", n=total), "all")
    cmb.addItem(tr.t("conv_scope_selected", n=selected), "selected")
    if selected:
        cmb.setCurrentIndex(1)
    else:
        cmb.model().item(1).setEnabled(False)
    return cmb


def _combo(items: list[tuple[str, str]], current: str) -> QComboBox:
    cmb = QComboBox()
    for value, label in items:
        cmb.addItem(label, value)
    cmb.setCurrentIndex(max(0, cmb.findData(current)))
    return cmb


def _spin(lo: int, hi: int, value: int, suffix: str = "") -> QSpinBox:
    sp = QSpinBox()
    sp.setRange(lo, hi)
    sp.setValue(value)
    sp.setSuffix(suffix)
    return sp


def _form(group: QGroupBox) -> QFormLayout:
    form = QFormLayout(group)
    form.setContentsMargins(12, 10, 12, 10)
    form.setSpacing(8)
    return form


class SaveOptionsDialog(QDialog):
    """고급 저장: 범위 + 압축 + 쪽번호 + 워터마크 + 암호."""

    def __init__(self, settings: QSettings, total: int, selected: int, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(tr.t("save_opts_title"))
        self.setMinimumWidth(460)
        s = settings
        d = SaveOptions()

        self.cmb_scope = scope_combo(total, selected)
        self.cmb_compress = _combo(
            [(c, tr.t(f"compress_{c}")) for c in COMPRESS_LEVELS],
            str(s.value("save/compress", d.compress)),
        )

        # 쪽번호
        self.grp_numbers = QGroupBox(tr.t("grp_numbers"))
        self.grp_numbers.setCheckable(True)
        self.grp_numbers.setChecked(s.value("save/numbers", False, type=bool))
        samples = {"{n}": "1", "{n} / {total}": "1 / 10", "- {n} -": "- 1 -"}
        self.cmb_num_format = _combo([(f, samples[f]) for f in NUMBER_FORMATS],
                                     str(s.value("save/number_format", d.number_format)))
        self.cmb_num_pos = _combo(
            [(p, tr.t("pos_" + p.replace("-", "_"))) for p in NUMBER_POSITIONS],
            str(s.value("save/number_position", d.number_position)),
        )
        self.spin_start = _spin(0, 99999, int(s.value("save/number_start", d.number_start)))
        f = _form(self.grp_numbers)
        f.addRow(tr.t("num_format"), self.cmb_num_format)
        f.addRow(tr.t("num_position"), self.cmb_num_pos)
        f.addRow(tr.t("num_start"), self.spin_start)

        # 워터마크
        self.grp_wm = QGroupBox(tr.t("grp_watermark"))
        self.grp_wm.setCheckable(True)
        self.grp_wm.setChecked(s.value("save/watermark_on", False, type=bool))
        self.edit_wm = QLineEdit(str(s.value("save/watermark", "")))
        self.spin_opacity = _spin(5, 90, int(s.value("save/watermark_opacity", 15)), " %")
        self.spin_angle = _spin(-90, 90, int(s.value("save/watermark_angle", d.watermark_angle)), "°")
        self.spin_size = _spin(10, 200, int(s.value("save/watermark_size", d.watermark_size)), " pt")
        f = _form(self.grp_wm)
        f.addRow(tr.t("wm_text"), self.edit_wm)
        f.addRow(tr.t("wm_opacity"), self.spin_opacity)
        f.addRow(tr.t("wm_angle"), self.spin_angle)
        f.addRow(tr.t("wm_size"), self.spin_size)

        # 암호 (기억하지 않음)
        self.grp_pw = QGroupBox(tr.t("grp_password"))
        self.grp_pw.setCheckable(True)
        self.grp_pw.setChecked(False)
        self.edit_pw = QLineEdit()
        self.edit_pw.setEchoMode(QLineEdit.Password)
        self.edit_pw2 = QLineEdit()
        self.edit_pw2.setEchoMode(QLineEdit.Password)
        f = _form(self.grp_pw)
        f.addRow(tr.t("pw_new"), self.edit_pw)
        f.addRow(tr.t("pw_confirm"), self.edit_pw2)
        note = QLabel(tr.t("pw_note"))
        note.setWordWrap(True)
        note.setStyleSheet("color: #73726B;")
        f.addRow(note)

        top = QFormLayout()
        top.setSpacing(10)
        top.addRow(tr.t("conv_scope"), self.cmb_scope)
        top.addRow(tr.t("grp_compress"), self.cmb_compress)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 12)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addWidget(self.grp_numbers)
        layout.addWidget(self.grp_wm)
        layout.addWidget(self.grp_pw)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if self.grp_wm.isChecked() and not self.edit_wm.text().strip():
            QMessageBox.warning(self, self.windowTitle(), tr.t("msg_wm_empty"))
            return
        if self.grp_pw.isChecked() and (
            not self.edit_pw.text() or self.edit_pw.text() != self.edit_pw2.text()
        ):
            QMessageBox.warning(self, self.windowTitle(), tr.t("msg_pw_mismatch"))
            return
        s = self.settings
        s.setValue("save/compress", self.cmb_compress.currentData())
        s.setValue("save/numbers", self.grp_numbers.isChecked())
        s.setValue("save/number_format", self.cmb_num_format.currentData())
        s.setValue("save/number_position", self.cmb_num_pos.currentData())
        s.setValue("save/number_start", self.spin_start.value())
        s.setValue("save/watermark_on", self.grp_wm.isChecked())
        s.setValue("save/watermark", self.edit_wm.text())
        s.setValue("save/watermark_opacity", self.spin_opacity.value())
        s.setValue("save/watermark_angle", self.spin_angle.value())
        s.setValue("save/watermark_size", self.spin_size.value())
        s.sync()
        self.accept()

    @property
    def use_selected(self) -> bool:
        return self.cmb_scope.currentData() == "selected"

    def options(self) -> SaveOptions:
        return SaveOptions(
            compress=self.cmb_compress.currentData(),
            page_numbers=self.grp_numbers.isChecked(),
            number_format=self.cmb_num_format.currentData(),
            number_position=self.cmb_num_pos.currentData(),
            number_start=self.spin_start.value(),
            watermark=self.edit_wm.text().strip() if self.grp_wm.isChecked() else "",
            watermark_opacity=self.spin_opacity.value() / 100,
            watermark_angle=self.spin_angle.value(),
            watermark_size=self.spin_size.value(),
            password=self.edit_pw.text() if self.grp_pw.isChecked() else "",
        )


class ImageExportDialog(QDialog):
    """페이지를 이미지 파일로 내보내기: 범위, 형식, 해상도."""

    def __init__(self, settings: QSettings, total: int, selected: int, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(tr.t("img_export_title"))
        self.setMinimumWidth(360)

        self.cmb_scope = scope_combo(total, selected)
        self.cmb_format = _combo([("png", "PNG"), ("jpg", "JPG")],
                                 str(settings.value("images/format", "png")))
        self.cmb_dpi = _combo([(str(v), f"{v} DPI") for v in (150, 300, 500)],
                              str(settings.value("images/dpi", "150")))

        form = QFormLayout()
        form.setContentsMargins(20, 18, 20, 8)
        form.setSpacing(12)
        form.addRow(tr.t("conv_scope"), self.cmb_scope)
        form.addRow(tr.t("img_format"), self.cmb_format)
        form.addRow(tr.t("img_dpi"), self.cmb_dpi)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        self.settings.setValue("images/format", self.fmt)
        self.settings.setValue("images/dpi", str(self.dpi))
        self.settings.sync()
        self.accept()

    @property
    def use_selected(self) -> bool:
        return self.cmb_scope.currentData() == "selected"

    @property
    def fmt(self) -> str:
        return self.cmb_format.currentData()

    @property
    def dpi(self) -> int:
        return int(self.cmb_dpi.currentData())
