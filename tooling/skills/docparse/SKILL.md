---
name: docparse
description: >-
  Use this skill to parse, search, or visually inspect local documents (PDF, DOCX, PPTX,
  XLSX/CSV, and images PNG/JPG/TIFF/WebP) with the pi-docparser tools: document_parse for
  text/JSON extraction, document_search for phrase locations + bounding boxes, and
  document_screenshot for visual page inspection. For very large PDFs, use the companion
  parse-huge-pdfs-chapter-by-chapter skill instead of a single parse.
license: MIT
compatibility: >-
  Requires document_parse; optionally benefits from document_search and document_screenshot
  (pi-docparser). Office formats may need LibreOffice on the host; scanned PDFs may need OCR.
metadata:
  author: pi + project overlay
  primary-interface: document_parse, document_search, document_screenshot
---

# Docparse

Use the dedicated document tools as the default interface. Do not fall back to `lit` CLI
commands unless the user explicitly asks for the raw command line or the tools are unavailable.

## Tool routing

- `document_parse` — extract text or JSON from a local document.
- `document_search` — find a phrase; returns page numbers + bounding boxes for citations.
- `document_screenshot` — render pages as PNGs when visual layout matters.

For known text: `document_search` first, then `document_screenshot` only for relevant pages.

## Efficient parsing

Choose the smallest useful output:

- `format: "text"` — read, summarize, quote, search, review.
- `format: "json"` — structured page data, text positions, bounding boxes.
- Avoid JSON unless coordinates/programmatic structure matter.

Stable JSON shape:

```json
{ "pages": [{ "pageNum": 1, "width": 612, "height": 792, "text": "...", "textItems": [] }], "text": "..." }
```

Limit scope early — pass an explicit `targetPages` (default `maxPages` is 100; hard cap 1000).
Parse in bounded chunks rather than whole documents.

## Very large PDFs

If a PDF is large (hundreds+ pages) or the task is "parse/convert/review this big PDF",
use the companion skill `parse-huge-pdfs-chapter-by-chapter` (map-based, de-duplicated,
chapter-split Markdown via the bundled CLI). Do not attempt a single whole-document parse.

## OCR

- `ocr: "off"` for native-text PDFs when OCR is unnecessary.
- Leave OCR automatic for scanned/image-heavy documents.
- `ocrLanguage` (single) or `ocrLanguages` (multilingual) when the language is known.
- Built-in Tesseract usually expects ISO 639-3 (`eng`, `deu`, `fra`, `jpn`); many HTTP OCR
  servers expect ISO 639-1 (`en`, `de`, `fr`, `ja`).
- Raise `dpi` only when OCR quality or screenshot readability needs it.
- Offline/custom data: pass `tessdataPath` (or `TESSDATA_PREFIX`).

## Search & screenshot workflow

- `document_search`: use when the user asks where text appears, for source/citation
  locations, or to find pages worth inspecting. Prefer `targetPages`; cap with `maxResults`.
- `document_screenshot`: use for charts/figures, handwriting/signatures, dense tables,
  visual layout, forms. Request 1–4 explicit pages per call; never `all`/`*`; make bounded
  repeated calls.

## Follow-up

`document_parse` writes output to temp files and returns paths; inspect them with `read`
only when the full content is needed. `document_screenshot` saves PNGs and inlines images
up to 3 MiB each / 12 MiB per result; inspect non-inlined PNG paths with `read`. Copy files
into the repo only when the user wants durable artifacts.

## Removed LiteParse v1 options (do not use)

`preciseBoundingBox`, `preserveLayoutAlignmentAcrossPages`.
Use `format: "json"` (textItems), `document_search`, `document_screenshot`, or `targetPages`.

## Constraints

- Office formats may require LibreOffice; image inputs are native.
- Password-protected docs: ask for the password, retry with `password`.
- Outputs are temporary by default; copy returned temp files if persistence is wanted.
- Accepts pi-style paths (`@relative/file.pdf`, `~/Documents/file.pdf`).

## High-value parameters

`path`, `format`, `targetPages`, `screenshotPages`, `ocr`, `ocrLanguage`, `ocrLanguages`,
`ocrServerUrl`, `numWorkers`, `maxPages`, `dpi`, `preserveSmallText`, `password`, `tessdataPath`.
Prefer a minimal set; add advanced options only when the task clearly benefits.
