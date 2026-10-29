# PDF Meltdown

[English](README.md) | **한국어**

**굳어 있는 PDF를 녹여서 다시 쓸 수 있는 Markdown으로.**

PySide6 기반 오프라인 데스크톱 PDF 도구. **영어·스페인어·일본어·한국어 문서의 PDF → Markdown 변환**(스캔본 OCR·표·이미지·수식 LaTeX)과
페이지 정리(합치기·분할·정렬·추출·회전)를 제공합니다. 모든 처리는 내 컴퓨터에서 이루어집니다.
Windows / macOS 공통 코드입니다(현재 Windows에서 개발·검증).
화면 언어: English · Español · 日本語 · 한국어 (처음 실행 시 OS 언어를 따름, 설정에서 변경).

## 동작 방식

모든 기능은 하나의 모델로 통합되어 있습니다: PDF·이미지를 열면 모든 페이지가
썸네일 목록에 모입니다. 이 목록을 조작해서 작업하고, 모든 조작은 되돌릴 수 있습니다.

| 기능 | 사용법 |
| --- | --- |
| **열기** | **열기/추가**, 또는 탐색기에서 PDF·이미지(PNG/JPG 등)를 창에 **끌어다 놓기**. 이미지는 A4 한 페이지가 됨 |
| **암호 PDF** | 열 때 암호 입력 → 편집 가능. 그냥 저장하면 암호가 풀린 파일로 저장 |
| **합치기** | 여러 파일을 목록에 모은 뒤 **전체 저장** |
| **정렬** | 썸네일을 **드래그**해서 순서 변경 |
| **회전** | **↺ / ↻** (선택 페이지 90°) |
| **빈 페이지·복제** | **페이지 ▾** → 빈 페이지 삽입 / 페이지 복제 |
| **되돌리기** | **되돌리기 / 다시 실행** (최대 100단계) |
| **추출·분할** | **내보내기 ▾** → 선택 추출 / 분할(N페이지씩 또는 선택 페이지 앞에서) |
| **고급 저장** | **내보내기 ▾ → 고급 저장**: 압축(보통/강함) · 쪽번호 · 워터마크 · 암호(AES-256) |
| **이미지로 내보내기** | **내보내기 ▾** → PNG/JPG, 72/150/300 DPI |
| **Markdown 변환** | **내보내기 ▾** → 현재 목록 순서(전체 또는 선택 페이지)대로 `.md` 생성 |

썸네일을 우클릭하면 회전·복제·삭제 등을 바로 쓸 수 있습니다.

### Markdown 변환

페이지마다 알맞은 엔진을 골라 씁니다.

- **디지털 페이지**(텍스트 레이어 있음) → PyMuPDF(pymupdf4llm): 제목·목록·단락·표·이미지, 다단 읽기 순서 보존
- **스캔 페이지**(이미지뿐) → xberg PaddleOCR: 영어·스페인어·일본어·한국어 OCR. 여러 언어를 고르면 페이지마다 자동 판별
  - 스캐너가 미리 넣어 둔 보이지 않는 OCR 층(전면 이미지 + 투명 글자)은 품질을 믿을 수 없어 다시 OCR 합니다.
- **수식 → LaTeX**(선택, 페이지당 수 초 추가): xberg LaTeX-OCR 로 수식을 찾아, 단독 줄 수식은 `$$…$$`,
  문장 속 수식은 `$…$` 로 넣습니다. 스캔·디지털 페이지 모두 지원(문장 속 짧은 인라인 수식은 감지되지 않을 수 있음).
- 옵션: OCR 자동/끄기/전체, OCR 모델 빠름/정확, 이미지 별도 폴더/md에 포함/제외, 스캔 원본 이미지 첨부, 페이지 구분선
- 이미지는 `문서명_assets/page003_01.png` 형태로 저장되고 상대경로로 링크됩니다.

알려진 한계: 테두리 없는 표는 일반 텍스트로 나올 수 있고, 병합 셀은 칸이 복제됩니다.
스캔 페이지 속 사진은 따로 잘라내지 못하므로 필요하면 "스캔 원본 이미지 첨부"를 켜세요.
Markdown은 위치를 표현할 수 없어 시각적 배치가 아닌 구조(제목·단락·목록·표·순서)를 보존합니다.

### 성능 / 반응성

- **열기는 즉시**: 페이지 수만 읽어 회색 placeholder로 목록을 바로 채우고, 실제 썸네일은
  백그라운드 스레드 풀에서 **병렬 렌더링**됩니다(대용량 PDF에서도 UI가 멈추지 않음).
- 로딩 중에는 상태바에 **진행률 바**가 표시되고, 완료되는 페이지부터 썸네일이 채워집니다.
- 썸네일은 220px로 한 번만 렌더링 후 표시 크기만 조절하므로, 크기 변경은 즉각적입니다.
- 저장·추출·분할·변환은 백그라운드에서 실행되며 진행률 다이얼로그에서 취소할 수 있습니다.

## 설치

```powershell
git clone https://github.com/Sion1225/pdf-meltdown.git
cd pdf-meltdown
python -m pip install -r requirements.txt
# 스캔 페이지 OCR까지 쓰려면 (선택)
python -m pip install -r requirements-markdown.txt
```

## 실행

```powershell
python run.py
```

## 단축키

| 키 | 동작 |
| --- | --- |
| Ctrl+O | 열기/추가 |
| Ctrl+Z / Ctrl+Y | 되돌리기 / 다시 실행 |
| Ctrl+L / Ctrl+R | 왼쪽 / 오른쪽 회전 |
| Ctrl+B | 빈 페이지 삽입 |
| Ctrl+D | 페이지 복제 |
| Delete | 선택 삭제 |
| Ctrl+S | 전체 저장(합치기) |
| Ctrl+Shift+E | 고급 저장 |
| Ctrl+E | 선택 추출 |
| Ctrl+Shift+S | 분할 |
| Ctrl+M | Markdown 변환 |

macOS에서는 Ctrl 대신 ⌘ 키입니다.

## 구조

```
pdf-meltdown/
  run.py              # 실행 진입점
  app/
    core.py           # 페이지 모델(PageRef: 회전·빈 페이지)과 저장/분할 (pypdf) — GUI 비의존
    postprocess.py    # 고급 저장: 압축·쪽번호·워터마크·암호 (PyMuPDF)
    images.py         # 이미지 → PDF 페이지, 페이지 → 이미지 파일
    render.py         # 썸네일 렌더링, 암호 PDF 열기 (PyMuPDF)
    jobs.py           # 백그라운드 출력 작업(진행률/취소)
    convert/          # PDF → Markdown (pipeline: 페이지별 엔진 선택, native: PyMuPDF, ocr: xberg,
                      #                 formulas: 수식 → LaTeX)
    dialogs.py        # 고급 저장 / 이미지 내보내기 다이얼로그
    i18n.py           # 화면 문구 (en, es, ja, ko)
    main_window.py    # GUI (PySide6)
```

## 라이선스

PyMuPDF가 AGPL-3.0이므로 이 프로젝트도 [AGPL-3.0](LICENSE)으로 배포합니다.

## 배포 (선택)

PyInstaller로 단일 실행 파일을 만들 수 있습니다.

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name "PDF Meltdown" run.py
```

macOS에서도 동일하게 `.app` 번들을 생성할 수 있습니다(해당 OS에서 빌드 필요).
