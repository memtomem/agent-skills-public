# pdf-parser

*[한국어 가이드 → README.ko.md](README.ko.md)*

A Claude skill for parsing **unstructured PDFs** — documents that mix body
text, multi-column layouts, ruled and borderless tables, charts, infographics,
scanned pages, and embedded images — into clean **Markdown** and a structured
**JSON** element tree. Handles Korean + English.

## Why

`pdftotext` over a real-world report scrambles columns, drops tables, and turns
charts into nothing. This skill instead **triages each page**, routes it to the
extractor that reads it best, and falls back to a vision model only where local
libraries genuinely can't see the content (scanned pages, charts whose data
lives inside pixels). The vision path also covers Korean OCR with no tesseract
language pack required.

## Install

### Claude Code / Claude Desktop / Cowork

Drop the skill folder into a skills directory and your agent picks it up
automatically:

```bash
# available in every project (recommended)
cp -R pdf-parser ~/.claude/skills/

# or scoped to one project
cp -R pdf-parser <your-project>/.claude/skills/
```

(Equivalently, build `dist/pdf-parser.skill` with `python scripts/build_all.py
pdf-parser` and use the app's **Save skill** button.) Once installed, just
mention a PDF — “이 PDF에서 표랑 본문 뽑아줘”, “convert this report.pdf to
markdown” — and the skill triggers; no special syntax needed. You can also
invoke it explicitly with `/pdf-parser`.

### Codex, Cursor, or any shell-capable agent

The `scripts/` are ordinary Python CLIs (deps: `pymupdf`, `pdfplumber`). Copy
`scripts/` into your project, `pip install pymupdf pdfplumber`, and point your
agent at `SKILL.md` for the triage → parse → vision-transcribe → verify
playbook.

## Workflow

```bash
cd scripts

# 1. triage — see each page's route and which need vision
python pdf_triage.py INPUT.pdf

# 2. local parse -> OUTDIR/INPUT.md + INPUT.json + assets/ + render/
#    vision pages are auto-rendered and embedded in the .md placeholders
python pdf_parse.py INPUT.pdf -o OUTDIR

# 3. read each embedded render/page_NNN.png and transcribe it into the placeholder
#    (re-render one sharper if needed: --render --pages N --dpi 300)
```

See `SKILL.md` for the full workflow (including the merge + verify steps) and
`references/pdf_internals.md` for the page-classification heuristics and the
JSON element schema.

## Routes

| route | meaning | handling |
|-------|---------|----------|
| `text` | clean text layer | PyMuPDF, reading order |
| `mixed` | text + figures / multi-column | text + image extract |
| `table` | ruled tables dominate | pdfplumber / camelot |
| `scanned` | little/no text layer | render → vision transcription |

## Dependencies

PyMuPDF and pdfplumber are required; camelot and tesseract are used
opportunistically if present. Install: `pip install pymupdf pdfplumber`.

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| A table came out empty or shifted | Borderless tables (no drawn grid) aren't detected locally by design — render the page (`pdf_parse.py … --render`) and transcribe it via vision. |
| A two-column page reads out of order | A 3+ column or text-wrapped-around-a-figure layout can scramble; check the triage `col` count and use vision for that page. |
| Korean text looks garbled | That's a scanned page being read as an image, not a text layer — use the vision route, don't rely on OCR. |
| `error: … is password-protected` | Pass `--password PASSWORD`, or remove the password in a PDF viewer and retry. |
| `ModuleNotFoundError: fitz` / `pdfplumber` | `pip install pymupdf pdfplumber`, and run the scripts from the `scripts/` directory. |

## Tests

```bash
python -m pytest tests/pdf_parser/ -q
```

Fixtures are generated from scratch (never committed) by
`tests/pdf_parser/fixtures/make_fixtures.py`.
