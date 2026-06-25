# xlsx-parser

*[한국어 가이드 → README.ko.md](README.ko.md)*

A Claude skill for parsing **messy, unstructured spreadsheets** (`.xlsx`/`.xlsm`)
— workbooks that are *not* one tidy table starting at A1 — into clean
**Markdown** and a structured **JSON** element tree. Handles Korean + English.

## Why

A `.xlsx` is structured XML, so "just read it into a dataframe" is tempting — but
real sheets break that assumption. A single sheet often has a title row, a unit
note, then the real header three rows down, then the table, a blank gutter, and a
*second* table beside or below it; cells are merged for visual grouping; numbers
are formulas whose computed results you actually want; and charts sit on top.
Flattening all of that loses the structure you came for.

So this skill **detects table regions, then extracts** — the same triage-first
idea as `pdf-parser`, adapted to spreadsheets. It cuts each sheet on fully-empty
rows/columns so stacked and side-by-side tables come out separately, finds the
real header row (not always row 1), keeps merged cells truthful by rendering them
as HTML, surfaces formula values (or the formula itself when no cache exists),
resolves chart data from the XML, and flags the risky sheets for review.

## Install

### Claude Code / Claude Desktop / Cowork

Drop the skill folder into a skills directory and your agent picks it up
automatically. From the repository root:

```bash
mkdir -p ~/.claude/skills
cp -R skills/xlsx-parser ~/.claude/skills/
```

If you are already inside `skills/xlsx-parser/`, use:

```bash
mkdir -p ~/.claude/skills/xlsx-parser
cp -R . ~/.claude/skills/xlsx-parser/
```

To scope it to one project, copy the folder into that project's
`.claude/skills/` directory instead. You can also build `dist/xlsx-parser.skill`
from the repository root and use the app's **Save skill** button:

```bash
uv run python scripts/build_all.py xlsx-parser
```

Once installed, just mention an `.xlsx` file — “이 엑셀에서 표들 뽑아줘”, “extract
the tables from this messy spreadsheet” — and the skill triggers; no special
syntax needed. You can also invoke it explicitly with `/xlsx-parser`.

### Codex, Cursor, or any shell-capable agent

The `scripts/` are ordinary Python CLIs (required dep: `openpyxl`; `markitdown`
is optional, only for `--crosscheck`). Copy `scripts/` into your project,
`pip install openpyxl`, and point your agent at `SKILL.md` for the
triage → parse → verify playbook.

## Workflow

Most users should ask their agent in plain language first:

- “이 엑셀에서 표들 뽑아줘.”
- “Extract the tables from this messy spreadsheet.”
- “이 워크북 표 구조 그대로 정리해줘.”
- “Convert this xlsx to markdown/JSON for RAG.”

The agent detects the table regions on each sheet, extracts them to Markdown +
JSON, and points you at the low-confidence sheets to verify first.

For direct command-line use:

```bash
cd scripts

# parse -> OUTDIR/INPUT.md + INPUT.json
python xlsx_parse.py INPUT.xlsx -o OUTDIR

# optional: also dump markitdown's flat-markdown view as a second opinion
python xlsx_parse.py INPUT.xlsx -o OUTDIR --crosscheck
```

The console prints, per sheet, how many tables were found, the confidence, and
the flags, plus a `🔎 verify these sheets` list. See `SKILL.md` for the full
workflow (read → check segmentation → verify flagged sheets → confirm formulas)
and `references/xlsx_internals.md` for the region/header heuristics and the JSON
element schema.

## What it detects

| Capability | What you get |
|---|---|
| Table segmentation | Each sheet cut on empty rows/columns into separate regions; flag `multiple-table-regions` when a sheet holds more than one |
| Real-header detection | A heuristic finds the labels row even when it isn't row 1; ambiguous cases get the `header-ambiguous` flag |
| Merged cells | Rendered as HTML `<table>` with `rowspan`/`colspan` (a flat pipe table can't express them); flag `merged-cells` |
| Formula values | Cached results read where present (`formula-cells`); when the workbook has no cache, the **formula itself** is shown, flagged `formula-no-cache` |
| Charts | Category labels and series values **resolved to concrete arrays** from the chart XML, alongside the raw `series_refs` |
| Confidence | Every sheet gets a `confidence` score and `flags` so attention goes where a silent error is likely (`empty-sheet` for blank sheets) |

## Dependencies

`openpyxl` is required. `markitdown` is optional and used only by `--crosscheck`
to write a flat second-opinion view.

```bash
pip install openpyxl          # required
pip install markitdown        # optional, for --crosscheck
```

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| Two real tables merged into one | Usually there was no fully-empty gutter between them (a stray value bridged the gap). Clear the bridging cell or split manually. |
| One table split into two | A blank row/column inside the table looked like a gutter — fill the gap or merge the regions by hand. |
| Cells show `=…` instead of numbers (`formula-no-cache`) | openpyxl never evaluates formulas, so a workbook saved by a non-Excel tool has no cached values. Open + save once in Excel/LibreOffice to get computed numbers. |
| Header row mis-detected (`header-ambiguous`) | Wide pivots or 3+ stacked header rows can confuse detection — check the flag and fix the header rows by hand. |
| A title/note shows as a `note`, not a table row | Intended — keeping it out keeps the table's header clean. |
| Low-confidence sheets | Look at the `🔎 verify these sheets` list first; diff with `--crosscheck` (markitdown) to spot mis-segmentation quickly. |

## Tests

```bash
python -m pytest tests/xlsx_parser/ -q
```

Fixtures are generated from scratch (never committed) by
`tests/xlsx_parser/fixtures/make_fixtures.py`.
