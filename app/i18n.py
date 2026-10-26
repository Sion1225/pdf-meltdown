"""간단한 사전 기반 다국어(i18n) 지원.

Qt Linguist(.ts/.qm) 툴체인 대신, 작은 앱에 맞게 문자열 사전으로 처리한다.
런타임에 언어를 바꾸면 MainWindow.retranslate() 가 모든 텍스트를 다시 설정한다.
"""

from __future__ import annotations

# (코드, 표시 이름) — 표시 이름은 각 언어 원어 그대로 둔다.
LANGUAGES = [("ko", "한국어"), ("en", "English"), ("ja", "日本語")]

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ko": {
        "app_title": "PDF 에디터",
        "act_open": "PDF 열기 / 추가",
        "act_extract": "선택 추출",
        "act_split": "분할",
        "act_save": "전체 저장 (합치기)",
        "act_remove": "선택 삭제",
        "act_clear": "전체 비우기",
        "act_settings": "설정",
        "settings_title": "설정",
        "lbl_language": "언어",
        "lbl_preview_pos": "미리보기 위치",
        "preview_left": "왼쪽",
        "preview_right": "오른쪽",
        "lbl_thumb_size": "썸네일 크기",
        "progress_format": "썸네일 로딩 %v / %m",
        "status_count": "총 {n}페이지 · 선택 {sel}페이지",
        "preview_hint": "페이지를 선택하면\n여기에 크게 표시됩니다.",
        "preview_fail": "미리보기 실패\n{label}",
        "dlg_open_title": "PDF 열기 (여러 개 선택 가능)",
        "filter_pdf": "PDF 파일 (*.pdf)",
        "err_open": "열기 실패",
        "ttl_extract": "추출",
        "msg_select_extract": "추출할 페이지를 먼저 선택하세요.",
        "dlg_extract_save": "선택 페이지 추출 저장",
        "err_extract": "추출 실패",
        "ttl_done": "완료",
        "msg_extracted": "{n}페이지를 추출했습니다.\n{path}",
        "ttl_save": "저장",
        "msg_no_pages_save": "저장할 페이지가 없습니다.",
        "dlg_save_all": "전체 저장 (현재 순서대로 합치기)",
        "err_save": "저장 실패",
        "msg_saved": "{n}페이지를 저장했습니다.\n{path}",
        "ttl_split": "분할",
        "msg_no_pages_split": "분할할 페이지가 없습니다.",
        "dlg_split_dir": "분할 파일을 저장할 폴더 선택",
        "err_split": "분할 실패",
        "msg_split_done": "{n}개 파일로 분할했습니다.\n저장 위치: {dir}",
        "ttl_clear": "전체 비우기",
        "msg_clear_confirm": "모든 페이지를 목록에서 지울까요?",
        "exporting": "파일 출력 중…",
        "cancel": "취소",
        "msg_cancelled": "출력이 취소되었습니다.",
        "split_dlg_title": "PDF 분할",
        "split_total": "총 {total}페이지를 분할합니다.",
        "split_chunk": "N페이지씩 묶어서 분할",
        "split_points": "선택한 페이지 '앞'에서 분할 (현재 {n}곳 선택)",
        "tip_thumb_size": "썸네일 크기 (리스트에서 Ctrl+휠로도 조절)",
    },
    "en": {
        "app_title": "PDF Editor",
        "act_open": "Open / Add PDF",
        "act_extract": "Extract Selected",
        "act_split": "Split",
        "act_save": "Save All (Merge)",
        "act_remove": "Remove Selected",
        "act_clear": "Clear All",
        "act_settings": "Settings",
        "settings_title": "Settings",
        "lbl_language": "Language",
        "lbl_preview_pos": "Preview position",
        "preview_left": "Left",
        "preview_right": "Right",
        "lbl_thumb_size": "Thumbnail size",
        "progress_format": "Loading thumbnails %v / %m",
        "status_count": "{n} pages · {sel} selected",
        "preview_hint": "Select a page to\npreview it here.",
        "preview_fail": "Preview failed\n{label}",
        "dlg_open_title": "Open PDF (multiple allowed)",
        "filter_pdf": "PDF files (*.pdf)",
        "err_open": "Open failed",
        "ttl_extract": "Extract",
        "msg_select_extract": "Select the pages to extract first.",
        "dlg_extract_save": "Save extracted pages",
        "err_extract": "Extraction failed",
        "ttl_done": "Done",
        "msg_extracted": "Extracted {n} page(s).\n{path}",
        "ttl_save": "Save",
        "msg_no_pages_save": "There are no pages to save.",
        "dlg_save_all": "Save all (merge in current order)",
        "err_save": "Save failed",
        "msg_saved": "Saved {n} page(s).\n{path}",
        "ttl_split": "Split",
        "msg_no_pages_split": "There are no pages to split.",
        "dlg_split_dir": "Choose a folder to save split files",
        "err_split": "Split failed",
        "msg_split_done": "Split into {n} file(s).\nLocation: {dir}",
        "ttl_clear": "Clear All",
        "msg_clear_confirm": "Remove all pages from the list?",
        "exporting": "Exporting file…",
        "cancel": "Cancel",
        "msg_cancelled": "Export cancelled.",
        "split_dlg_title": "Split PDF",
        "split_total": "Splitting {total} page(s).",
        "split_chunk": "Split every N pages",
        "split_points": "Split before selected pages ({n} selected)",
        "tip_thumb_size": "Thumbnail size (also Ctrl+Wheel on the list)",
    },
    "ja": {
        "app_title": "PDF エディター",
        "act_open": "PDFを開く / 追加",
        "act_extract": "選択を抽出",
        "act_split": "分割",
        "act_save": "すべて保存 (結合)",
        "act_remove": "選択を削除",
        "act_clear": "すべてクリア",
        "act_settings": "設定",
        "settings_title": "設定",
        "lbl_language": "言語",
        "lbl_preview_pos": "プレビュー位置",
        "preview_left": "左",
        "preview_right": "右",
        "lbl_thumb_size": "サムネイルサイズ",
        "progress_format": "サムネイル読み込み %v / %m",
        "status_count": "全{n}ページ · 選択{sel}ページ",
        "preview_hint": "ページを選択すると\nここに大きく表示されます。",
        "preview_fail": "プレビュー失敗\n{label}",
        "dlg_open_title": "PDFを開く (複数選択可)",
        "filter_pdf": "PDFファイル (*.pdf)",
        "err_open": "オープン失敗",
        "ttl_extract": "抽出",
        "msg_select_extract": "抽出するページを先に選択してください。",
        "dlg_extract_save": "選択ページを抽出して保存",
        "err_extract": "抽出に失敗しました",
        "ttl_done": "完了",
        "msg_extracted": "{n}ページを抽出しました。\n{path}",
        "ttl_save": "保存",
        "msg_no_pages_save": "保存するページがありません。",
        "dlg_save_all": "すべて保存 (現在の順序で結合)",
        "err_save": "保存に失敗しました",
        "msg_saved": "{n}ページを保存しました。\n{path}",
        "ttl_split": "分割",
        "msg_no_pages_split": "分割するページがありません。",
        "dlg_split_dir": "分割ファイルの保存フォルダを選択",
        "err_split": "分割に失敗しました",
        "msg_split_done": "{n}個のファイルに分割しました。\n保存先: {dir}",
        "ttl_clear": "すべてクリア",
        "msg_clear_confirm": "すべてのページをリストから削除しますか？",
        "exporting": "ファイル出力中…",
        "cancel": "キャンセル",
        "msg_cancelled": "出力をキャンセルしました。",
        "split_dlg_title": "PDF分割",
        "split_total": "全{total}ページを分割します。",
        "split_chunk": "Nページごとに分割",
        "split_points": "選択したページの「前」で分割 (現在 {n} 箇所選択)",
        "tip_thumb_size": "サムネイルサイズ (リストでCtrl+ホイールでも調整可)",
    },
}


class Translator:
    def __init__(self, lang: str = "ko") -> None:
        self._lang = lang if lang in TRANSLATIONS else "ko"

    @property
    def lang(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        if lang in TRANSLATIONS:
            self._lang = lang

    def t(self, key: str, **kwargs) -> str:
        table = TRANSLATIONS.get(self._lang, TRANSLATIONS["ko"])
        text = table.get(key) or TRANSLATIONS["ko"].get(key, key)
        return text.format(**kwargs) if kwargs else text


# 앱 전역에서 공유하는 번역기 인스턴스
tr = Translator()
