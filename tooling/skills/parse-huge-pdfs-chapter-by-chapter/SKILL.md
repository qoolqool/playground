---
name: parse-huge-pdfs-chapter-by-chapter
description: >
  Parse very large PDFs (hundreds to thousands of pages) into de-duplicated,
  chapter-split Markdown without flooding the model context. Use when asked to
  parse, extract, convert, or review a big PDF, when a document is too long for
  one parse call, or when the document_parse limits get in the way (100-page
  default, 1000-page hard cap, text/json output only). Ships a CLI script that
  drives the LiteParse engine directly plus a chapter-map workflow.
---

# Parse Huge PDFs Chapter by Chapter

`pi-docparser`'s `document_parse` tool is the right interface for normal
documents, but it cannot produce Markdown and it hides the full text in a temp
file. Very large PDFs also hit its hard limits. This skill provides a script
that drives the bundled LiteParse engine directly, de-duplicates pages, and
writes one Markdown file per chapter.

## Files in this skill

```
parse-huge-pdfs-chapter-by-chapter/
├── SKILL.md
└── parse-pdf-to-markdown.mjs        # the CLI
```

No chapter maps are shipped. Each document gets its own map, generated with
`--dump-map` and reviewed before the final run.

## When to Use

- Parsing a PDF that is hundreds to thousands of pages.
- Converting a large PDF to Markdown for chunked or LLM consumption.
- Any time `document_parse` is awkward: text/json only, a 1000-page cap, or an
  output that must not enter model context.

## Procedure

1. Confirm the PDF is native text (parse pages 1-3 with `ocr:"off"`); if so keep
   OCR off. The script does this by default.
2. Run once with `--dump-map=FILE` to auto-detect chapter boundaries.
3. Review and correct the map file before the final run: auto-detected titles and
   boundaries are a draft, not a result.
4. Run the script with the reviewed map. It parses in 1000-page chunks, drops
   duplicate pages, splits by the map, and writes per-chapter `.md` files plus
   `INDEX.md` and `<label>.full.md`.
5. Never `read` the whole `.full.md` into context. Use `grep`/`head`/`sed`, or
   `read` with offset+limit, on the per-chapter files.

### Commands

Run these from the skill directory (or prefix the script with its full path).

```bash
# First pass on a new PDF: auto-detect boundaries and capture the map for review
node parse-pdf-to-markdown.mjs big.pdf out/dir --dump-map=out/dir/big.map.txt

# Reliable run with the reviewed chapter map
node parse-pdf-to-markdown.mjs big.pdf out/dir \
  --label=my-document \
  --map=out/dir/big.map.txt
```

Options: `--label`, `--map=FILE`, `--dump-map=FILE`, `--no-dedup`,
`--keep-headers`. The map format is one boundary per line, `PAGE|TITLE`; pages
are 1-based original PDF page numbers and the last boundary runs to the end of
the document.

## How detection works

1. **Font-size detection (preferred).** A chapter starts on pages whose first
   text item uses the recurring largest heading font size. This works on
   documents that carry real font sizes.
2. **Markdown-heading detection (fallback).** For HTML-to-PDF exports where every
   font size is 1, it uses the first level-1/2 Markdown heading on a page when it
   looks like a document or section title. This is approximate; refine with a map.

## Pitfalls

- **`document_parse` has no Markdown output.** Only `text` and `json` are
  exposed, so this script calls `@llamaindex/liteparse` directly. The module is
  auto-resolved from the installed pi packages; set `LITEPARSE_MODULE` to an
  explicit `dist/lib.js` path when resolution fails.
- **`targetPages` is validated against `maxPages`.** A range longer than
  `maxPages` (default 100) errors with "Page selection contains more than N
  selected pages". LiteParse hard-caps at 1000 pages per call and the script
  chunks automatically.
- **Large documents are often duplicated page for page.** HTML-to-PDF exports
  repeat whole sections, and the repetition is invisible in a page count. Read
  the reported `duplicates` figure before splitting, or the chapters repeat many
  times over.
- **No PDF outlines or bookmarks.** Boundaries must be derived, by map or by the
  detectors above.
- **Font quirks.** Some exports set `fontSize == 1` for all text and carry
  heading weight in `fontName`; others use real sizes. The dual detector covers
  both shapes.
- **Heading classification is unstable across page subsets.** Levels and text can
  change depending on which pages are parsed together. Always parse the whole
  document, and treat auto-detected boundaries and titles as a draft.
- **"Pages parsed" is not the total page count.** It is only the pages in that
  call.
- **A few tables lose cells** when the source laid them out as vector graphics.
  That is an extraction limitation, not a pipeline bug.

## Verification

- The run reports `page count`, `pages`, `unique`, and `duplicates`; `unique`
  must be less than or equal to `pages`.
- The sum of the "Unique pages" column in `INDEX.md` equals the reported
  `unique`.
- Each chapter file starts with `# <title>` and carries `<!-- source page N -->`
  markers; concatenated chapters cover pages 1..total with no gaps (check
  `99-uncategorised.md`).
- Model context only ever contains the short script output or explicitly
  grepped excerpts, never the full parsed document.
