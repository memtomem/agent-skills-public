# Changelog

All notable changes to this collection are documented here.

## [Unreleased]

### Added
- Initial `memtomem-skills` collection monorepo.
- **hwp-toolkit 0.2.0** — read / analyze / edit Hangul Word Processor files:
  - Binary `.hwp` 5.x text extraction (inline-control aware), structure &
    metadata inspection, find-replace and index-based cell editing with a full
    OLE2 compound-file rewriter that preserves untouched streams byte-for-byte.
  - `.hwpx` (OWPML zip) reading support; multi-section documents extracted with
    `=== section ===` headers.
  - `.hwpx` editing via `hwp_edit.py replace` / `replace_text()`: rewrites only
    the edited `Contents/section*.xml` and copies every other zip member
    through verbatim (STORED `mimetype` stays first), preserving inline elements
    (`<hp:lineBreak/>`, `<hp:tab/>`, markup) in edited runs.
  - `.hwpx` extraction now resolves `<hp:lineBreak/>`→newline and `<hp:tab/>`→
    tab and strips other inline markup, instead of leaking raw XML tags.
  - pytest suite with from-scratch fixtures; `scripts/build_all.py` packaging.
- **pdf-parser 0.1.0** — triage messy PDFs and extract text/tables/images into
  Markdown plus a JSON element tree:
  - Per-page **triage** (`pdf_triage.py`) routes each page `text` / `mixed` /
    `table` / `scanned` from cheap signals (char count, image coverage,
    table-line score, column estimate) and flags the pages that need vision.
  - **Local-first** extraction: PyMuPDF text in reading order with font-size
    heading detection; pdfplumber tables as GFM (camelot as an opportunistic
    second opinion); embedded rasters saved under `assets/`.
  - **Vision fallback**: scanned / image-only / figure pages pre-render to PNG
    under `render/` and keep a visible `⚠️` placeholder embedding the image for a
    vision model to transcribe — handles Korean OCR without tesseract packs.
  - Output is Markdown + a JSON element tree (type / page / bbox); PyMuPDF +
    pdfplumber required, camelot and tesseract optional.
- **xlsx-parser 0.1.0** — parse messy spreadsheets (`.xlsx`/`.xlsm`) into
  Markdown plus a JSON element tree:
  - Detects table *regions* per sheet (cut on fully-empty rows/columns) so
    stacked and side-by-side tables come out separately; a heuristic finds the
    real header row (not always row 1).
  - Merged cells render as HTML (`rowspan`/`colspan`); formula cells show the
    cached value, or the formula itself (flagged `formula-no-cache`) when a
    workbook carries no cache.
  - Chart category labels and series values resolved to concrete arrays from the
    XML cell references; per-sheet `confidence` score + `flags` surface risky
    sheets. Optional `--crosscheck` dumps a markitdown second opinion.
- **docx-parser 0.1.0** — parse messy Word documents (`.docx`) into Markdown plus
  a JSON element tree:
  - Walks the document in **body order**, so tables interleaved between
    paragraphs keep their place (python-docx exposes paragraphs and tables as
    separate lists); recurses into nested tables.
  - Merged cells (`gridSpan`/`vMerge`) render as HTML; recovers text boxes
    (`w:txbxContent`) as `📦 [text box]` blocks; headers/footers and comments
    preserved as HTML comments.
  - Flags `tracked-changes-present`, `nested-table`, `comments-present`,
    `needs-vision` (image-only) and more, with a `confidence` score; embedded
    images are counted, not extracted. Optional `--crosscheck` markitdown view.
- **pptx-parser 0.1.0** — parse PowerPoint decks (`.pptx`) into Markdown plus a
  JSON element tree, in reading order:
  - Orders each slide's shapes by geometry (top-to-bottom, left-to-right) since
    slides have no inherent reading order; recurses into grouped shapes.
  - Extracts titles, bullet text, tables (merged cells as HTML), pictures, and
    speaker notes (`🗒 [notes]`); chart categories + series values read exactly
    from the XML.
  - Per-slide `confidence` + flags (`image-only-slide`, `needs-vision`,
    `overlapping-shapes-order-ambiguous`, `has-chart`, …); image-only slides
    route to a vision pass. Optional `--crosscheck` markitdown view.
