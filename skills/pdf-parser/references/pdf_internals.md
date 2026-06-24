# PDF parser internals

Read this when a page is misrouted, a table comes out wrong, or you want to
extend the routing rules. All logic lives in `scripts/pdf_lib.py`; the CLIs
(`pdf_triage.py`, `pdf_parse.py`) are thin wrappers.

## Table of contents
1. The hybrid strategy
2. Page classification (triage)
3. Text extraction & reading order
4. Heading detection
5. Table extraction
6. Image extraction & the vision fallback
7. The JSON element schema
8. Known limitations

## 1. The hybrid strategy

No single extractor wins on every page, so each page is *classified* and then
*routed*. Local libraries handle anything with a real text layer (fast, exact,
no hallucination). A vision model handles only what local tools cannot see —
scanned pages and charts whose data lives inside pixels. The vision path is also
the Korean-OCR path: the model reads the rendered page image directly, so no
tesseract Korean language pack is required.

Two libraries do the heavy lifting:
- **PyMuPDF (`fitz`)** — text with positions/fonts, drawings (for table-line
  detection), embedded images, and page rendering.
- **pdfplumber** — table detection on ruled (lined) tables, via its default
  line strategy. **camelot** is used opportunistically as a second opinion if
  it imports.

## 2. Page classification (triage)

`classify_page()` computes cheap signals and picks a route. Signals:

- `char_count` — stripped length of the text layer.
- `block_count` — number of text blocks (`get_text("dict")`).
- `image_area_ratio` — fraction of page area covered by raster images
  (deduplicated by placement rect; `_image_area_ratio`).
- `table_line_score` — count of long horizontal/vertical strokes and table-sized
  rectangles in the vector drawings (`_table_line_score`). A cheap proxy, not a
  full table detector — it only decides whether to *try* the table extractor.
- `columns` — 1 or 2, estimated from the left-edge clustering of text blocks
  (`_estimate_columns`); deliberately conservative to avoid scrambling
  single-column reading order.

Routing order (first match wins) — see `classify_page` for exact thresholds:

1. **scanned** — `char_count < 30` and `image_area_ratio > 0.55`, or an empty
   text layer. Sets `needs_vision=True`.
2. **table** — `table_line_score >= 8` and not too much text.
3. **mixed** — meaningful image coverage (`>0.18`), or 2 columns, or images
   alongside text. If a big figure (`>0.45`) sits over thin text (`<400` chars),
   also sets `needs_vision=True` (content is probably inside the figure).
4. **text** — the default clean case.

Thresholds are gentle on purpose: misrouting toward `mixed`/vision is cheaper
than dropping content. To tune, edit the constants inline in `classify_page`.

## 3. Text extraction & reading order

`extract_text_elements()` uses `page.get_text("dict")` blocks. Blocks are sorted
top-to-bottom (`_sort_blocks_reading_order`); for 2-column pages the left column
is emitted fully before the right. The y-key is quantized (`y/3`) so that
slightly misaligned blocks on the same visual line don't ping-pong by x.

Paragraph/heading blocks whose center falls inside a detected table's bbox are
dropped in `parse_page` (`_drop_text_inside_tables`) so table cells aren't
printed twice (once as a table, once as loose text). The check is 2-D (x **and**
y): a band-only check would also drop text sitting *beside* a table at the same
height — e.g. a right-column paragraph level with a left-column table.

## 4. Heading detection

`_body_font_size()` takes the modal rounded span size as the body size. A block
is a heading if its max span size is ≥1.35× body (level by ratio: ≥1.8→H1,
≥1.45→H2, else H3), or if it is short, bold, and ≥1.1× body (→H3). Font-size
heuristics beat hard-coded patterns because they generalize across templates and
languages — Korean reports rarely use "1. / 1.1" numbering consistently.

## 5. Table extraction

`extract_tables()` tries pdfplumber first (`find_tables()` + `Table.extract()`),
then camelot `lattice` then `stream` if importable. Each candidate is normalized (cells
whitespace-collapsed, empty rows dropped). The candidate with the most non-empty
cells wins — this avoids emitting an empty husk when one engine misfires. Output
is `Element(type="table", rows=[[...]])`; `_rows_to_markdown` renders GFM,
pad-aligning ragged rows and inline-escaping each cell (so a literal `|`, `_`,
`*`, etc. can't break out of the grid).

Each candidate carries a bbox so the table can be slotted into reading order and
its loose text suppressed (otherwise the numbers print twice). pdfplumber's
`Table.bbox` is already top-left origin and used as-is. camelot reports cell
coordinates in PDF points with a **bottom-left** origin, so `_camelot_table_bbox`
flips them to top-left using the **mediabox** height — the reference pdfminer
uses, and thus the same one pdfplumber's `top` is measured against (verified:
`pdfplumber page.height == mediabox height`). `parse_page` threads
`page.mediabox.height` for this, deliberately **not** `PageInfo.height` /
`page.rect.height`, which PyMuPDF reports as the *cropbox* height; the two differ
when a page's cropbox is inset, and using the cropbox height would shift camelot
bboxes relative to pdfplumber's. Without a height — or on any structural surprise
in camelot's objects — it returns None and the table falls back to bbox-less
behaviour rather than getting a wrong box.

Table extraction is **gated on ruling-line evidence** (`parse_page` only calls
it when `route == table` or `table_line_score >= 4`). This is intentional:
running table extraction on every multi-column page turns ordinary two-column
prose into a garbage table, because aligned text columns look table-shaped to
the extractor. The cost is that a fully *borderless* table (no drawn grid, no
line score) won't be detected locally — route those to vision. `find_tables`
itself uses the line strategy, so it wouldn't catch a truly borderless table
anyway. When a real table is missed or wrong, render the page and transcribe it.

## 6. Image extraction & the vision fallback

`extract_images()` saves embedded rasters above a size threshold
(`min_area_ratio=0.03` of page area) so bullets/logos/rules don't spam the
output. CMYK images are converted to RGB before saving.

`render_page_png()` rasterizes a whole page (default 200 DPI) for the vision
model. By default `build_document(render_vision=True, ...)` (which the CLI turns
on) pre-renders every `needs_vision` page to `render/page_NNN.png`, records the
path as `page["render"]`, and `to_markdown` embeds it (`![](render/...)`) inside
the `⚠️` placeholder so the model can **Read** it immediately. The workflow then
is: the model Reads the embedded/rendered PNG → transcribes to Markdown → the
placeholder block in the `.md`/`.json` is replaced. Vision-sourced elements
should carry `"note": "vision"` for provenance. `--render` (standalone) still
exists to re-render specific pages at a different DPI; `--no-vision-render` skips
the auto-render. Both `render_page_png` and the build-time render share
`_save_page_png` (rasterize an already-open page) so the file is opened once.
When a page is shown via its render image, `to_markdown` drops any *full-page*
raster element (`_covers_most_of_page`, ≥90% of page area) so a scanned page
isn't pictured twice; partial figures (e.g. a chart on a mixed page) are kept.
In-document image links are joined with `posixpath` so the `.md` stays portable
(forward slashes) regardless of host OS.

Markdown rendering escapes markdown-special characters in extracted heading and
paragraph text (`_escape_md`): inline markers (`` \ ` * _ [ ] < > ~ |``) always,
plus line-leading block markers (`#`, `>`, `-`/`+` bullets, `1.`/`1)` ordered
lists, `---`/`===` rules) for running text. Table cells use the inline-only form
(a leading `-` in a cell is data, not a bullet). This keeps literal PDF content
from being reinterpreted as formatting, while leaving ordinary prose (and CJK
text, which has no specials) untouched.

## 7. The JSON element schema

```
document = {
  source: str, page_count: int,
  pages: [ {
    page: int, route: str, width: float, height: float,
    needs_vision: bool, reason: str,
    render?: str,          # path to the page PNG, when needs_vision + render_vision
    elements: [ Element, ... ]
  } ]
}
Element = {
  type: "heading"|"paragraph"|"table"|"image",
  page: int,
  bbox?: [x0,y0,x1,y1]   # PDF points, top-left origin
  text?: str,            # heading/paragraph
  level?: int,           # heading only (1-3)
  rows?: [[str,...]],    # table only
  path?: str,            # image only
  note?: str             # provenance: "auto-detected" (tables); the agent sets "vision" on merge
}
```

`Element.to_dict()` omits empty fields to keep the JSON compact.

## 8. Known limitations

- The local editor reads, it does not reconstruct: rotated text, equations, and
  handwriting need vision.
- Column detection handles 1–2 columns; 3+ column layouts (some newspapers) may
  scramble — route those pages to vision.
- `table_line_score` keys on vector strokes; tables drawn as a background image
  won't be detected locally and will surface via the `scanned`/`mixed` vision
  flag instead.
- Reading order across a page that wraps text *around* a figure is approximate.
