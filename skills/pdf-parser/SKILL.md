---
name: pdf-parser
description: >-
  Parse messy, unstructured PDFs whose pages mix body text, multi-column
  layouts, ruled/borderless tables, charts, scanned pages, and images — into
  clean Markdown plus a structured JSON element tree. Use whenever the goal is to
  get CONTENT out of a non-linear PDF: financial/annual reports, research papers,
  brochures, slide exports, statistical yearbooks (통계연보), scanned contracts or
  invoices, government 공문·보고서, or any "convert/extract this PDF to
  text/markdown/data", "pull the tables out of this PDF into csv/pandas", "OCR
  this scanned PDF", "이 PDF에서 표랑 본문 뽑아줘" request — even when the user
  never says "parse", and especially when plain copy-paste would scramble
  columns, drop tables, or miss figures. Handles Korean+English and routes
  scanned pages to vision. NOT for PDF file manipulation (merging, splitting,
  rotating, compressing, password-protecting), NOT for filling PDF form fields,
  and NOT for non-PDF formats (.hwp → hwp-toolkit, .docx, .xlsx).
---

# Unstructured PDF Parser

## Why this skill exists

Real-world PDFs are not linear text. One page can carry two text columns, a
ruled financial table, a chart whose labels live inside the image, and a
scanned stamp — each of which a *different* tool reads best. Dumping
`pdftotext` over such a page scrambles reading order, silently drops tables,
and turns charts into nothing. The fix is not a bigger hammer; it is to look
at each page first, route it to the right extractor, and fall back to a vision
model only where local libraries genuinely can't see the content.

This skill follows a **hybrid** strategy on purpose:

- **Local-first** (PyMuPDF + pdfplumber/camelot) for everything with a real
  text layer — fast, free, exact, no hallucination risk.
- **Vision fallback** for scanned/image-only pages and charts whose meaning is
  locked inside pixels. This path also handles Korean OCR without needing
  tesseract language packs, because *you* (the model running this skill) read
  the rendered page image directly.

The output is always two things in lockstep: **Markdown** (for reading, RAG,
pasting into a doc) and **JSON** (an element tree with type, page, and bbox —
for downstream code).

## The workflow

Work through these steps. Don't skip triage — it is what makes the rest cheap.

### 1. Triage the document

```bash
cd <skill>/scripts
python pdf_triage.py /path/to/INPUT.pdf
```

This prints a per-page table: route (`text` / `mixed` / `table` / `scanned`),
character count, image coverage, table-line score, column count, and — crucially
— which pages are flagged 👁 for vision. Read it before doing anything else so
you know where the hard pages are. A document that is 40 clean text pages plus 2
scanned pages needs very different effort than one that is all infographics.

### 2. Run the local parse

```bash
python pdf_parse.py /path/to/INPUT.pdf -o /path/to/OUTDIR
```

Produces `OUTDIR/INPUT.md`, `OUTDIR/INPUT.json`, `OUTDIR/assets/` (extracted
images), and `OUTDIR/render/` (the pages that need vision, pre-rendered to PNG).
Text comes out in reading order with headings detected from font size; tables
render as GitHub-flavored Markdown; images are saved and linked. Pages that need
vision are left with a visible `⚠️` placeholder block that **embeds the rendered
page image** right below it — they are *not* silently empty. (Pass
`--no-vision-render` to skip the pre-rendering; `--dpi N` to change resolution.)

### 3. Transcribe the pages that need vision

Each `needs_vision` page already has its rendered PNG embedded in the placeholder
(`OUTDIR/render/page_NNN.png`). **Read** that PNG (it is a normal image — your
vision works on it directly, Korean included) and transcribe what you see into
Markdown: headings, paragraphs, and especially any table or chart. For a chart,
transcribe the title, axis labels, and the data series or values you can read —
don't just write "a chart". This is the step where the hybrid pays off.

If a page needs a sharper image, re-render it on its own at a higher DPI:

```bash
python pdf_parse.py /path/to/INPUT.pdf -o /path/to/OUTDIR --render --pages 3 --dpi 300
```

If you have many scanned pages and a local OCR engine is available, you may also
run `tesseract` as a first pass, but always sanity-check its output against the
rendered image — OCR garbles Korean and small fonts, and you can fix it on sight.

### 4. Merge and finalize

Replace each `⚠️` placeholder block in the `.md` with your transcription, and
update the matching `pages[].elements` in the `.json` (give vision-sourced
elements `"note": "vision"` so provenance is traceable). Keep page order intact.

### 5. Verify before delivering

Spend a moment checking the output is faithful — this is where parsing bugs
hide:

- Open the `.md` and skim it against the original page images. Did any table
  lose a column or merge two rows? Did a two-column page interleave wrongly?
- Confirm every page flagged 👁 actually got transcribed (no leftover `⚠️`).
- Spot-check numbers in tables against the source — a transposed digit in a
  financial table is worse than no table.
- Check Korean text didn't get mojibake'd (broken encoding).

Then deliver the `.md` and `.json` (and `assets/` if images matter). Tell the
user which pages used vision, so they know where to double-check.

## Output format

**Markdown**: headings as `#`/`##`/`###`, paragraphs as prose, tables as GFM
pipe tables, images as `![](assets/...)`. Markdown-special characters in the
extracted text are escaped so literal content (e.g. a line that starts `1.` or
`#`, or a `snake_case` token) renders verbatim instead of turning into list
items or emphasis. Vision pages embed their rendered image (`![](render/...)`)
inside the `⚠️` placeholder. HTML comments mark page boundaries and routes so the
structure stays inspectable.

**JSON** element tree:

```json
{
  "source": "report.pdf",
  "page_count": 12,
  "pages": [
    {
      "page": 1, "route": "mixed", "width": 595.0, "height": 842.0,
      "needs_vision": false, "reason": "text + 1 image (22% area)",
      "elements": [
        {"type": "heading", "page": 1, "level": 1, "text": "2025 연차보고서", "bbox": [...]},
        {"type": "paragraph", "page": 1, "text": "...", "bbox": [...]},
        {"type": "table", "page": 1, "rows": [["항목","금액"], ["매출","1,200"]], "note": "auto-detected"},
        {"type": "image", "page": 1, "path": "assets/p1_img0.png", "bbox": [...]}
      ]
    }
  ]
}
```

`type` is one of `heading`, `paragraph`, `table`, `image`. Every element carries
its `page`; most carry a `bbox` ([x0,y0,x1,y1] in PDF points) so downstream code
can re-locate it.

## Routes at a glance

| route | what it means | how it's handled |
|-------|---------------|------------------|
| `text` | clean text layer, single flow | PyMuPDF text, reading order |
| `mixed` | text + figures, and/or multi-column | text + image extract + interleave |
| `table` | ruled tables dominate | pdfplumber, camelot fallback |
| `scanned` | little/no text layer | render → vision transcription |

A `mixed` page with a big figure and little text is also flagged for vision,
because the content is probably inside the image.

## Tips and failure modes

- **Tables that come out empty or shifted**: extraction keys on ruling lines,
  so a *borderless* table (no drawn grid) may not be detected — and that is
  deliberate, because aligned prose columns otherwise get mangled into fake
  tables. When a real table is missed or comes out wrong, render that page and
  transcribe it via vision — don't ship a broken table.
- **Reading order looks scrambled**: likely an undetected column layout or a
  sidebar. Check the triage `col` count; for stubborn pages, vision
  transcription gives correct order.
- **Korean text is garbled in the `.md`**: that's almost always a scanned page
  read by OCR, not the local text path. Use the vision route instead.
- **Huge documents**: triage first, then only render the handful of pages that
  actually need vision rather than rendering everything.

## Reference

`references/pdf_internals.md` documents the page-classification heuristics, the
element schema, and how the extractors are layered — read it when debugging a
misrouted page or extending the routing rules. `scripts/pdf_lib.py` holds all
the logic; the two CLIs are thin wrappers over it.
