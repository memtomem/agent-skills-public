# docx-parser internals

All logic lives in `scripts/docx_lib.py`; `docx_parse.py` is a thin CLI.

## 1. Body-order iteration (the keystone)

`iter_block_items()` walks the body XML children (`w:p`, `w:tbl`) and wraps them
as python-docx `Paragraph`/`Table` in true document order. This is the whole
point: `doc.paragraphs` and `doc.tables` are separate sequences, so a table
between two paragraphs would otherwise lose its position. The same function
recurses into table cells (`_Cell`), which is how nested tables are reached.

## 2. Paragraph classification

- **Heading**: style name `Heading N` (→ level N, capped 6) or `Title` (→ 1).
- **List item**: a `w:numPr` in the paragraph properties, or a style starting
  with `List`.
- **Text box**: `_para_textboxes()` scans the paragraph for `w:txbxContent`
  (DrawingML/VML) and pulls the `w:t` runs — python-docx never exposes these, so
  their text would be silently dropped.
- Otherwise a plain paragraph.

## 3. Tables — nested & merged (`parse_table`)

Rows are read cell by cell from `w:tr`/`w:tc`. Merges:

- **Horizontal** (`w:gridSpan val="n"`) → a span `{colspan: n}` on the anchor;
  `n-1` follower cells are emitted blank.
- **Vertical** (`w:vMerge`): `val="restart"` opens an anchor with `rowspan: 1`;
  each later `w:vMerge` (continue) increments that anchor's `rowspan` and emits a
  blank follower. Anchor positions are tracked per column.

A cell containing its own table is captured **structurally**, not flattened:
`parse_table` recurses and records each nested table in a `nested` list as
`{row, col, rows, spans, nested}` keyed by the parent cell's position (the cell's
own text stays in `rows`). A table with a `nested` entry renders as HTML, where
the nested table is produced by the *same* escaping renderer and appended inside
its parent cell. Crucially, **all cell text is escaped** (`_esc`) — nothing in a
`rows` string is ever trusted as HTML, so literal `<table>`/`<script>` text in a
source document can't inject raw markup. Otherwise rendering mirrors xlsx-parser
— HTML with `rowspan`/`colspan` when spans exist, else a GFM pipe table.

## 4. Document signals & confidence

Detected from XML / relationships:

| signal | how | cap | flag |
|--------|-----|-----|------|
| tracked changes | `w:ins` / `w:del` in body | 0.65 | `tracked-changes-present` |
| text box content | `w:txbxContent` found | 0.80 | `textbox-content` |
| nested table | table inside a cell | 0.75 | `nested-table` |
| merged cells | gridSpan/vMerge | 0.80 | `merged-cells` |
| comments | a `comments` relationship | 0.85 | `comments-present` |
| embedded images | `a:blip` count | 0.85 | `embedded-images-not-extracted` |
| image-only document | images present, no text | 0.40 | `needs-vision` |

`confidence` = min of the caps that fire; `needs_review` = confidence < 0.75.
Headers/footers are appended as `note` elements (deduped). Images are counted and
summarized, not extracted. A document that is **image-dominant** (embedded images
with no extractable text) additionally sets a document-level
**`needs_vision: true`** + the `needs-vision` flag, so callers route it to a
vision pass deterministically (parity with pdf-parser / pptx-parser) — a future
pass would pull `word/media/`.

## 5. JSON schema

```
document = { source, element_count, confidence, flags[],
             needs_review, needs_vision, elements[] }
Element = {
  type: "heading"|"paragraph"|"list_item"|"table"|"textbox"|"note"|"image",
  text?: str, level?: int,
  rows?: [[str,...]], spans?: [{row,col,rowspan,colspan}],   # table
  nested?: [{row, col, rows, spans, nested}],   # table: nested tables by cell pos
  note?: str
}
```

## 6. Known limitations

- Nested tables are kept as structured `nested` data and rendered as HTML inside
  the parent cell; very deep nesting stays correct but gets visually dense.
- Tracked-change text reflects current markup, not a chosen accept/reject state.
- SmartArt and complex DrawingML text may not fully surface (flagged).
- Images are counted only; extraction is a future pass.
- Hierarchical/multi-row table headers aren't specially modeled.
