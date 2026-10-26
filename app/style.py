"""모던 라이트 테마 QSS. run.py 에서 Fusion 베이스 위에 적용한다."""

from __future__ import annotations

# 색상 팔레트 — Claude(Anthropic) 스타일: 따뜻한 아이보리 + 코랄 액센트
BG = "#F5F4EE"          # 창 배경(웜 아이보리)
SURFACE = "#FBFAF6"     # 툴바/상태바(살짝 밝은 아이보리)
BORDER = "#E7E3D7"      # 경계선(웜 그레이)
TEXT = "#1F1E1C"        # 기본 글자(잉크)
MUTED = "#73726B"       # 보조 글자
ACCENT = "#D97757"      # 강조(클로드 코랄)
ACCENT_HOVER = "#C8664A"
ACCENT_DARK = "#B2543B"
ACCENT_SOFT = "#F3E4DC"  # 강조 연한 배경(코랄 틴트)
LIST_BG = "#EDEBE2"     # 썸네일 영역(웜 라이트)
PREVIEW_BG = "#262624"  # 미리보기 패널(클로드 다크, 흰 페이지가 돋보이도록)


STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Malgun Gothic", "Yu Gothic UI", "Meiryo", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}

/* 상단 도구 모음 */
QToolBar {{
    background: {SURFACE};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 7px 10px;
    spacing: 6px;
}}
QToolBar::separator {{
    background: {BORDER};
    width: 1px;
    margin: 4px 8px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 13px;
    color: {TEXT};
    font-weight: 500;
}}
QToolButton:hover {{
    background: {ACCENT_SOFT};
    border-color: #dfe3ff;
    color: {ACCENT};
}}
QToolButton:pressed {{ background: #e0e4ff; }}

/* 메뉴 */
QMenuBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; padding: 2px 6px; }}
QMenuBar::item {{ background: transparent; padding: 6px 11px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}

/* 썸네일 리스트 */
QListView {{
    background: {LIST_BG};
    border: none;
    padding: 10px;
    outline: 0;
}}
QListView::item {{
    color: {MUTED};
    border: 1px solid transparent;
    border-radius: 12px;
    padding: 6px;
}}
QListView::item:hover {{ background: #e3e7f1; }}
QListView::item:selected {{
    background: #dfe4ff;
    color: {ACCENT_DARK};
    border: 1px solid {ACCENT};
}}

/* 스크롤바 */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #c5cad4; border-radius: 6px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: #a9b0bf; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #c5cad4; border-radius: 6px; min-width: 32px; }}
QScrollBar::handle:horizontal:hover {{ background: #a9b0bf; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* 상태바 */
QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {MUTED}; }}

/* 진행률 */
QProgressBar {{
    background: #e7eaf0;
    border: none;
    border-radius: 7px;
    height: 14px;
    text-align: center;
    color: {MUTED};
    font-size: 11px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 7px; }}

/* 슬라이더 */
QSlider::groove:horizontal {{ height: 4px; background: #d6dae2; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {SURFACE};
    border: 2px solid {ACCENT};
    width: 14px; height: 14px;
    margin: -7px 0;
    border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{ border-color: {ACCENT_HOVER}; }}

/* 버튼 / 입력 */
QPushButton {{
    background: {ACCENT};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton:pressed {{ background: {ACCENT_DARK}; }}
QSpinBox, QComboBox {{
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 10px;
    background: #ffffff;
    min-height: 20px;
}}
QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {MUTED};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT_DARK};
    outline: 0;
}}
QRadioButton {{ padding: 5px 2px; spacing: 8px; }}
QDialog QLabel {{ color: {TEXT}; }}

/* 툴팁 */
QToolTip {{
    background: #2b303b;
    color: #ffffff;
    border: none;
    padding: 6px 9px;
    border-radius: 6px;
}}

/* 분할선(스플리터) */
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}
"""
