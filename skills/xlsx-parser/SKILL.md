---
name: xlsx-parser
description: >-
  Parse messy, unstructured spreadsheets (.xlsx/.xlsm) into clean Markdown plus a
  structured JSON element tree — for sheets that are NOT one tidy table starting
  at A1. Use whenever a workbook has several tables stacked or side-by-side on one
  sheet, a header that isn't the first row (titles/notes above it), merged cells,
  formulas whose computed values you need, charts, or many sheets — the cases
  where "just read it into a dataframe" produces garbage. Triggers: "이 엑셀에서
  표들 뽑아줘", "extract the tables from this messy spreadsheet", "convert this
  xlsx to markdown/JSON for RAG", "pull each table out of every sheet",
  "이 워크북 표 구조 그대로 정리해줘". Handles Korean+English, preserves merged
  cells as HTML, and flags low-confidence sheets for review. This is for READING
  CONTENT out of a spreadsheet — NOT for building or editing a new spreadsheet
  (use the xlsx authoring skill), NOT for PDFs (use pdf-parser), and NOT for Word
  or PowerPoint files.
---

# Unstructured Spreadsheet Parser

## Why this skill exists

A `.xlsx` is structured XML, so it's tempting to "read it into a dataframe" — but
real sheets are not one clean table. A single sheet often has a title row, a unit
note, then the real header three rows down, then the table, a blank gutter, and a
second table; cells are merged for visual grouping; numbers are formulas whose
results you actually want; and charts sit on top. Flattening all of that loses
the structure you came for.

So this skill **detects table regions, then extracts** — the same triage-first
idea as `pdf-parser`, adapted to spreadsheets:

- **Find the tables.** Each sheet is cut on fully-empty rows/columns into
  rectangular regions, so stacked and side-by-side tables come out separately
  instead of being smeared into one grid.
- **Find the real header.** It isn't always row 1; a heuristic spots the labels
  row (including the common "year columns over text row-labels" shape).
- **Keep merged cells truthful.** Regions with merges render as HTML
  (`rowspan`/`colspan`), which a flat pipe table cannot express.
- **Show formula results honestly.** Cached values are read where present
  (`formula-cells`); when a workbook has none, the cell shows the **formula
  itself** instead of a misleading blank, flagged `formula-no-cache`.
- **Recover charts exactly.** A chart's data lives in the XML (cell references),
  so the category labels and series values are **resolved to concrete arrays**,
  not guessed.
- **Flag the risky sheets.** Every sheet gets a `confidence` score and `flags`
  so attention goes where a silent error is likely.

Output is Markdown (for reading/RAG) plus a JSON element tree (for code) — the
same lockstep as `pdf-parser`.

## Workflow

```bash
cd <skill>/scripts

# parse -> OUTDIR/INPUT.md + INPUT.json
python xlsx_parse.py /path/to/INPUT.xlsx -o /path/to/OUTDIR

# optional: also dump markitdown's plain-markdown view as a second opinion
python xlsx_parse.py /path/to/INPUT.xlsx -o /path/to/OUTDIR --crosscheck
```

The console prints, per sheet, how many tables were found, the confidence, and
the flags, plus a `verify these sheets` list. Then:

1. **Read the Markdown** against the original workbook. For each sheet, check the
   detected tables match what a human would call a table — did two adjacent
   tables get merged, or one table get split?
2. **Look at flagged sheets first** (`verify_sheets` / the `🔎` note). Flags:
   `multiple-table-regions`, `merged-cells`, `header-ambiguous`, `formula-cells`,
   `empty-sheet`.
3. **Check merged-cell tables** (rendered as HTML) — confirm the spans landed on
   the right header.
4. **Confirm formula values.** If a sheet is flagged `formula-cells` and values
   look blank, the workbook was never recalculated/saved by Excel (openpyxl
   doesn't compute formulas); open it in Excel once, or compute the values.
5. **Cross-check when unsure.** `--crosscheck` writes markitdown's flat view next
   to ours — diffing the two quickly reveals whether a sheet was mis-segmented.

## Output format

**Markdown**: one `# Sheet: NAME` section per sheet; tables as GFM pipe tables,
or `<table>` HTML when they contain merged cells; title/unit strips as plain
notes; charts as a `**[chart]**` line with kind + data references; low-confidence
sheets get an inline `🔎` note.

**JSON** element tree:

```json
{
  "source": "messy.xlsx",
  "sheet_count": 4,
  "min_confidence": 0.5,
  "verify_sheets": ["Empty"],
  "sheets": [
    {
      "name": "Finance", "table_count": 2, "confidence": 0.80,
      "flags": ["multiple-table-regions"],
      "elements": [
        {"type": "note", "sheet": "Finance", "text": "2025 재무 요약 …", "ref": "A1:A2"},
        {"type": "table", "sheet": "Finance", "ref": "A4:D7",
         "rows": [["항목 Item","2023","2024","2025"], ["매출 Revenue","980","1050","1239"]]},
        {"type": "table", "sheet": "Finance", "ref": "A11:B13", "rows": [["부문 Segment","비중%"], ...]}
      ]
    }
  ]
}
```

Element `type` is one of `heading`, `paragraph`, `note`, `table`, `chart`. Table
elements carry a `ref` (A1-style region), optional `spans` (merged-cell anchors:
`{row, col, rowspan, colspan}`, 0-based within the region), and an optional
`note` (e.g. `contains-formula(cached values shown)`, or `…(no cached values —
formulas shown literally)`). A `chart` element carries `categories` and resolved
`series` values alongside the raw `series_refs`.

## Relationship to markitdown

markitdown converts `.xlsx` to markdown well and is a fine quick path for a
single tidy sheet. This skill adds what markitdown flattens: per-sheet **table
segmentation**, **merged-cell fidelity** (HTML spans), **formula provenance**,
**chart data**, and **confidence flags**. Use `--crosscheck` to get both and diff
them; trust the structured output, use markitdown as the sanity check.

## Tips and failure modes

- **A title or note becomes its own "note" element**, not a table row — that's
  intended; it keeps the table's header clean.
- **Two real tables merged into one** usually means there was no fully-empty
  gutter between them (e.g. one stray value bridged the gap). Clear the bridging
  cell or split manually.
- **`formula-no-cache` (cells show `=…` instead of numbers)**: openpyxl never
  evaluates formulas, so a workbook saved by a non-Excel tool has no cached
  values — the formula string is surfaced as provenance. Open+save in
  Excel/LibreOffice once to get computed numbers.
- **Wide pivot tables / 3+ stacked headers** can confuse header detection; check
  the `header-ambiguous` flag and fix the header rows by hand.

## Reference

`references/xlsx_internals.md` documents region detection, header heuristics,
merged-cell rendering, the confidence model, and the JSON schema.
`scripts/xlsx_lib.py` holds the logic; `xlsx_parse.py` is a thin CLI over it.
