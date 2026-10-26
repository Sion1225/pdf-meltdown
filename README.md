# PDF 에디터

PySide6 기반 데스크톱 PDF 편집기. **페이지 분할 · PDF 합치기 · 페이지 정렬 · 페이지 추출** 기능을 제공합니다.
Windows / macOS 공통 코드입니다(현재 Windows에서 개발·검증).

## 동작 방식

모든 기능은 하나의 모델로 통합되어 있습니다: 여러 PDF를 열면 모든 페이지가
썸네일 목록에 모입니다. 이 목록을 조작해서 작업합니다.

| 기능 | 사용법 |
| --- | --- |
| **합치기** | 여러 PDF를 열어 목록에 모은 뒤 **전체 저장(합치기)** |
| **정렬** | 썸네일을 **드래그**해서 순서 변경 후 저장 |
| **추출** | 원하는 페이지를 선택(Ctrl/Shift) 후 **선택 추출** |
| **분할** | **분할** → N페이지씩 묶거나, 선택한 페이지 '앞'에서 끊기 |

### 성능 / 반응성

- **열기는 즉시**: 페이지 수만 읽어 회색 placeholder로 목록을 바로 채우고, 실제 썸네일은
  백그라운드 스레드 풀에서 **병렬 렌더링**됩니다(대용량 PDF에서도 UI가 멈추지 않음).
- 로딩 중에는 상태바에 **진행률 바**가 표시되고, 완료되는 페이지부터 썸네일이 채워집니다.
- 썸네일은 320px로 한 번만 렌더링 후 표시 크기만 조절하므로, 크기 변경은 즉각적입니다.

## 설치

```powershell
cd pdf_editor
python -m pip install -r requirements.txt
```

## 실행

```powershell
python run.py
```

## 단축키

| 키 | 동작 |
| --- | --- |
| Ctrl+O | PDF 열기/추가 |
| Ctrl+E | 선택 추출 |
| Ctrl+Shift+S | 분할 |
| Ctrl+S | 전체 저장(합치기) |
| Delete | 선택 삭제 |

## 구조

```
pdf_editor/
  run.py              # 실행 진입점
  app/
    core.py           # PDF 조작 로직 (pypdf) — GUI 비의존
    render.py         # 썸네일 렌더링 (PyMuPDF)
    main_window.py    # GUI (PySide6)
```

## 배포 (선택)

PyInstaller로 단일 실행 파일을 만들 수 있습니다.

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name "PDF에디터" run.py
```

macOS에서도 동일하게 `.app` 번들을 생성할 수 있습니다(해당 OS에서 빌드 필요).
