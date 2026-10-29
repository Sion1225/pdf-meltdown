"""PDF Meltdown 실행 진입점.

    python run.py
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.style import STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("PDFEditorApp")
    app.setApplicationName("PDF Meltdown")
    app.setStyle("Fusion")          # 플랫폼 간 일관된 베이스 스타일
    app.setStyleSheet(STYLESHEET)   # 그 위에 모던 테마 적용

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
