# xlsx-parser internals

Read this when a sheet is mis-segmented, a header is wrong, or you want to extend
the heuristics. All logic lives in `scripts/xlsx_lib.py`; `xlsx_parse.py` is a
thin CLI.

## Table of contents
1. Strategy & loading
2. Table-region detection
3. Header detection
4. Merged cells & extraction
5. Charts
6. Confidence model
7. JSON schema
8. Known limitations

## 1. Strategy & loading

A spreadsheet is structured but rarely a single clean table, so we **detect
regions then extract**, rather than dumping every cell. `load_dual()` loads the
workbook twice with openpyxl: `data_only=True` for cached values (what you
usually want) and `data_only=False` for formula strings (provenance). openpyxl
**does not evaluate formulas** — if a workbook was never saved by Excel, the
cached value is absent. Rather than emit a misleading blank, the cell then shows
its **formula string** (e.g. `=B2*C2`), the table note says *"no cached values —
formulas shown literally"*, and `formula-no-cache` is flagged (distinct from the
plain `formula-cells` flag, which means formulas with caches present).

## 2. Table-region detection (`detect_table_regions`)

Find the used bounding box, then recursively cut it on any fully-empty row
(`_is_empty_row`) or column (`_is_empty_col`), trimming empty borders first.
This separates **stacked** tables (empty-row gutter) and **side-by-side** tables
(empty-column gutter) without assuming one table at A1 — the usual reason a flat
read fails. A region that is a single row or single column is treated as a
title/unit **note**, not a table (`parse_sheet`).

Gotcha: if a stray value bridges the gutter between two tables (no fully-empty
separating row/col), they merge into one region. Clear the bridging cell.

## 3. Header detection (`detect_header_row`)

Two acceptance paths, returning `(row, confident)`:

- **A — labels over numbers.** A row that is ≥60% text with a markedly more
  numeric row beneath it.
- **B — numeric column headers.** The region's first row is fully populated and
  sits over a body whose **first column is textual row-labels**. This catches the
  very common financial shape where the headers are years/codes
  (`2023 | 2024 | 2025`) that *look* numeric but are labels. Without this, every
  such table would falsely flag `header-ambiguous`.

If neither path matches, the first region row is used and `header-ambiguous` is
flagged. `_looks_numeric` treats ints/floats and strings like `1,239` or `38%`
as numeric.

**Preamble split.** When the confident header sits *below* the region's first
row (a title/note got swept in without a blank-row gutter), `parse_sheet` peels
those leading rows off as a `note` so they don't pollute the table body — but
only when each is a single-cell "strip". A multi-cell row above the header is
left in place, because it is more likely the top of a **multi-row header** (e.g.
a merged super-header) than a title.

## 4. Merged cells & extraction (`extract_region`)

Merged ranges intersecting the region (`ws.merged_cells.ranges`) are mapped to
`spans` on the anchor cell (`{row, col, rowspan, colspan}`, 0-based within the
region); follower cells are emitted blank in `rows` and skipped by the HTML
renderer. `rows` always holds cached values as strings (full grid). Formula
presence is detected from the `data_only=False` load and recorded as a note.

Rendering (`element_to_markdown`): a table with `spans` renders as `<table>` with
`rowspan`/`colspan` (faithful to merges); a plain table renders as a GFM pipe
table (`_rows_to_gfm`). No spans are *inferred* beyond the real merges.

## 5. Charts (`extract_charts`)

`ws._charts` exposes chart objects. We read the kind (class name), the title
(from the rich-text run tree, best-effort), and each series' value reference
(`series.val.numRef.f`, an A1 range). The references are then **resolved to
concrete arrays**: `categories` and per-series `values` come from the reference's
embedded numeric cache when the file carries one (`_ref_cache`), else by reading
the referenced cells from the `data_only` workbook (`_resolve_ref`). Because the
data is cell references in the XML, this is exact — no vision needed, unlike a
chart baked into a PDF. `series_refs` is still emitted for provenance.

## 6. Confidence model (`parse_sheet`)

Per-sheet `confidence` in [0,1] = min of caps, with reason `flags`:

| condition | cap | flag |
|-----------|-----|------|
| more than one table region | 0.80 | `multiple-table-regions` |
| any merged cells | 0.75 | `merged-cells` |
| header not confidently found | 0.70 | `header-ambiguous` |
| formulas present (caches available) | 0.85 | `formula-cells` |
| formulas with no cached values | 0.65 | `formula-no-cache` |
| no content at all | 0.50 | `empty-sheet` |

Document-level `min_confidence` and `verify_sheets` (sheets < 0.75) surface the
risky sheets. The flags are advisory triage, not errors — a multi-table sheet is
common and fine, but it's where a wrong cut would hide.

## 7. JSON schema

```
document = {
  source: str, sheet_count: int,
  min_confidence: float, verify_sheets: [str, ...],
  sheets: [ {
    name: str, table_count: int, confidence: float, flags: [str, ...],
    elements: [ Element, ... ]
  } ]
}
Element = {
  type: "heading"|"paragraph"|"note"|"table"|"chart",
  sheet: str,
  text?: str,                 # note/paragraph/heading/chart label
  rows?: [[str,...]],         # table: full grid of cached values
  spans?: [{row,col,rowspan,colspan}],  # table: merged-cell anchors (0-based)
  ref?: str,                  # A1-style region (e.g. "A4:D7")
  note?: str,                 # e.g. "contains-formula(cached values shown)"
  chart?: {                   # chart only
    kind, title,
    series_refs: [str, ...],            # raw A1 references (provenance)
    categories?: [str, ...],            # resolved category labels
    series?: [{name, ref, values:[str,...]}, ...]   # resolved series
  }
}
```

## 8. Known limitations

- openpyxl doesn't compute formulas; on a sheet flagged `formula-no-cache` the
  cells show the formula *string* (not a value) — recalc in Excel/LibreOffice to
  get numbers.
- Header detection assumes a single header row; multi-row/hierarchical headers
  may need manual fixing (watch `header-ambiguous`).
- A value bridging the gutter between two tables fuses them into one region.
- Cell formatting (colors, number formats) is not captured — values only.
- Embedded images and pasted screenshots are not extracted here (a future vision
  pass, mirroring pdf-parser, would handle those).
