# PDF Meltdown

**English** | [日本語](README.ja.md) | [한국어](README.ko.md)

**Merge, split and reorder your PDFs — or melt them down into Markdown you can actually use.**

An offline desktop PDF tool built with PySide6. It converts **PDFs in English, Spanish, Japanese and Korean
to Markdown** (OCR for scans, tables, images, formulas as LaTeX) and organizes pages
(merge, split, reorder, extract, rotate). Everything runs on your own computer.
One codebase for Windows and macOS (currently developed and tested on Windows).
UI languages: English · Español · 日本語 · 한국어 (follows the OS language on first launch; change it in Settings).

## How it works

Every feature works on one model: when you open PDFs or images, all their pages go into a single
thumbnail list. You work by editing that list, and every change can be undone.

| Feature | How to use it |
| --- | --- |
| **Open** | **Open**, or **drag and drop** PDFs and images (PNG, JPG, …) onto the window. Each image becomes one A4 page |
| **Password-protected PDFs** | Enter the password when opening, then edit as usual. A plain save writes the file without a password |
| **Merge** | Collect several files in the list, then **Save** |
| **Reorder** | **Drag** thumbnails |
| **Rotate** | **↺ / ↻** (selected pages, 90°) |
| **Blank / duplicate pages** | **Pages ▾** → Insert blank page / Duplicate pages |
| **Undo** | **Undo / Redo** (up to 100 steps) |
| **Extract / split** | **Export ▾** → Extract selected / Split (every N pages, or before selected pages) |
| **Advanced save** | **Export ▾ → Advanced save**: compression (medium/strong), page numbers, watermark, password (AES-256) |
| **Export as images** | **Export ▾** → PNG/JPG at 150/300/500 DPI |
| **PDF → Markdown** | **Export ▾** → writes a `.md` file from the list in its current order (all pages or the selection) |

Right-click a thumbnail for rotate, duplicate, remove and more.

### PDF → Markdown

Each page is handled by the engine that suits it.

- **Digital pages** (with a text layer) → PyMuPDF (pymupdf4llm): headings, lists, paragraphs, tables and images,
  keeping the reading order of multi-column layouts
- **Scanned pages** (images only) → xberg PaddleOCR: English, Spanish, Japanese and Korean OCR.
  If you select several languages, the language is detected per page
  - Invisible OCR layers added by scanners (a full-page image with transparent text) are unreliable, so these pages are OCR'd again.
- **Formulas → LaTeX** (optional, adds a few seconds per page): xberg LaTeX-OCR finds formulas. A formula on its own line
  becomes `$$…$$`, and one inside a sentence becomes `$…$`. Works on both scanned and digital pages (short inline formulas
  inside sentences may be missed).
- Options: OCR auto/off/all pages, OCR model fast/accurate, images in a folder/embedded/excluded,
  attach the original scan image, page separators
- Images are saved as `name_assets/page003_01.png` and linked with relative paths.

Known limitations: tables without borders may come out as plain text, and merged cells are duplicated.
Photos inside scanned pages are not cropped out separately; turn on "Also attach scanned page images" if you need them.
Markdown cannot express position, so the output keeps the structure (headings, paragraphs, lists, tables, order),
not the visual layout.

### Performance

- **Opening is instant**: the list fills with gray placeholders right away, and real thumbnails are rendered
  **in parallel** on a background thread pool, so the UI never freezes, even on very large PDFs.
- While loading, a **progress bar** appears in the status bar, and thumbnails fill in as each page finishes.
- Thumbnails are rendered once at 220 px and only scaled for display, so resizing is immediate.
- Save, extract, split and convert run in the background with a progress dialog you can cancel.

## Installation

```powershell
git clone https://github.com/Sion1225/pdf-meltdown.git
cd pdf-meltdown
python -m pip install -r requirements.txt
# Optional: OCR for scanned pages and formula recognition
python -m pip install -r requirements-markdown.txt
```

## Running

```powershell
python run.py
```

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| Ctrl+O | Open / add |
| Ctrl+Z / Ctrl+Y | Undo / redo |
| Ctrl+L / Ctrl+R | Rotate left / right |
| Ctrl+B | Insert blank page |
| Ctrl+D | Duplicate pages |
| Delete | Remove selected |
| Ctrl+S | Save all (merge) |
| Ctrl+Shift+E | Advanced save |
| Ctrl+E | Extract selected |
| Ctrl+Shift+S | Split |
| Ctrl+M | Convert to Markdown |

On macOS, use ⌘ instead of Ctrl.

## Project structure

```
pdf-meltdown/
  run.py              # entry point
  app/
    core.py           # page model (PageRef: rotation, blank pages) and save/split (pypdf), GUI-independent
    postprocess.py    # advanced save: compression, page numbers, watermark, password (PyMuPDF)
    images.py         # image → PDF page, page → image file
    render.py         # thumbnail rendering, opening encrypted PDFs (PyMuPDF)
    jobs.py           # background export jobs (progress/cancel)
    convert/          # PDF → Markdown (pipeline: per-page engine choice, native: PyMuPDF, ocr: xberg,
                      #                 formulas: formulas → LaTeX)
    dialogs.py        # advanced save / image export dialogs
    i18n.py           # UI strings (en, es, ja, ko)
    main_window.py    # GUI (PySide6)
```

## License

PyMuPDF is licensed under AGPL-3.0, so this project is distributed under [AGPL-3.0](LICENSE) as well.

## Packaging (optional)

You can build a standalone app with PyInstaller.

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name "PDF Meltdown" run.py
```

The same command builds a `.app` bundle on macOS (it must be built on that OS).
