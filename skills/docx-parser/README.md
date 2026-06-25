# docx-parser

*[한국어 가이드 → README.ko.md](README.ko.md)*

A Claude skill for parsing **messy, unstructured Word documents** (`.docx`) —
files that mix body text with tables in between, nested tables, merged cells,
bullet/numbered lists, text boxes, headers/footers, tracked changes, and
comments — into clean **Markdown** and a structured **JSON** element tree.
Handles Korean + English.

## Why

A `.docx` is structured XML, yet the obvious extraction — joining
`doc.paragraphs` — quietly drops or scrambles real content. python-docx exposes
paragraphs and tables as *separate* lists, so a table sitting between two
paragraphs loses its place. Tables nest inside cells; cells merge with
`gridSpan`/`vMerge`; bullet lists, text boxes (`w:txbxContent`),
headers/footers, tracked changes, and comments all live in places a flat read
never visits. This skill instead walks the document **in body order** — text
and tables interleaved correctly — and emits a structured element tree with a
confidence score and flags, so the risky documents surface for a human/LLM
check.

## Install

### Claude Code / Claude Desktop / Cowork

Drop the skill folder into a skills directory and your agent picks it up
automatically. From the repository root:

```bash
mkdir -p ~/.claude/skills
cp -R skills/docx-parser ~/.claude/skills/
```

If you are already inside `skills/docx-parser/`, use:

```bash
mkdir -p ~/.claude/skills/docx-parser
cp -R . ~/.claude/skills/docx-parser/
```

To scope it to one project, copy the folder into that project's
`.claude/skills/` directory instead. You can also build `dist/docx-parser.skill`
from the repository root and use the app's **Save skill** button:

```bash
uv run python scripts/build_all.py docx-parser
```

Once installed, just mention a `.docx` — “이 워드 문서에서 본문이랑 표 구조 그대로
뽑아줘”, “extract everything from this .docx to markdown keeping tables” — and
the skill triggers; no special syntax needed. You can also invoke it explicitly
with `/docx-parser`.

### Codex, Cursor, or any shell-capable agent

The `scripts/` are ordinary Python CLIs (dep: `python-docx`; `markitdown` is
optional, used only for `--crosscheck`). Copy `scripts/` into your project,
`pip install python-docx`, and point your agent at `SKILL.md` for the
parse → review-flags → verify playbook.

## Workflow

Most users should ask their agent in plain language first:

- “이 워드 문서에서 본문이랑 표 구조 그대로 뽑아줘.”
- “Extract everything from this .docx to markdown keeping tables.”
- “Convert this contract.docx to JSON.”
- “이 docx를 마크다운으로 정리해줘 — 표 박스랑 텍스트 박스도 빠뜨리지 말고.”

The agent walks the document in body order, keeps merged cells as HTML, recovers
text boxes, and surfaces a confidence score with flags for the items worth a
second look (tracked changes, nested tables, comments).

For direct command-line use:

```bash
cd scripts

# parse -> OUTDIR/INPUT.md + INPUT.json
python docx_parse.py INPUT.docx -o OUTDIR

# add a markitdown second opinion -> OUTDIR/INPUT.markitdown.md to diff against
python docx_parse.py INPUT.docx -o OUTDIR --crosscheck
```

See `SKILL.md` for the full workflow (output format and review steps) and
`references/docx_internals.md` for body-order iteration, merge handling, the
confidence model, and the JSON element schema.

## Flags

The parser emits flags so the documents that need a human/LLM check surface.
Read the top `🔎` note and the flags before trusting the output.

| flag | meaning | what to do |
|------|---------|------------|
| `tracked-changes-present` | document has pending insertions/deletions | text reflects current markup — decide if you want the accepted or original text, confirm in Word |
| `merged-cells` | a table has `gridSpan`/`vMerge` merges | rendered as `<table>` HTML — confirm the spans landed correctly |
| `nested-table` | a table nests inside another table's cell | kept as structured `nested` data and rendered as HTML in that cell — spot-check the inner rows |
| `textbox-content` | text was recovered from a text box | rendered as `📦 [text box]` blocks — verify none were missed (complex VML can hide more) |
| `comments-present` | the document carries review comments | check whether the comment text belongs in your extracted content |
| `embedded-images-not-extracted` | images are counted, not pulled out | if you need them, open the `.docx` (it's a zip) under `word/media/` |
| `needs-vision` | the document is *only* images (no text) | route it to a vision pass (`needs_vision: true`) |

## Dependencies

python-docx is required; markitdown is optional and only used by `--crosscheck`
to write a second-opinion Markdown to diff against.

```bash
pip install python-docx          # required
pip install markitdown           # optional, for --crosscheck
```

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| Insertions/deletions look wrong | Tracked changes are extracted as the *current* markup — accept or reject in Word first if you need a specific revision state. |
| A merged-cell table looks off | Merged cells render as `<table>` HTML rather than GFM — confirm the row/column spans match the original. |
| A text box seems missing | Text boxes are pulled as `📦 [text box]` blocks; complex VML / SmartArt may not fully surface — the `textbox-content` flag warns you to check. |
| Images didn't come out | Embedded images are counted, not extracted in this pass — open the `.docx` (it's a zip) under `word/media/` to get the raw files. |
| Output is empty / `needs_vision: true` | The document is image-only with no text layer — route it to a vision pass to transcribe the images. |
| `ModuleNotFoundError: docx` | `pip install python-docx` (the import name is `docx`), and run the scripts from the `scripts/` directory. |

## Tests

```bash
python -m pytest tests/docx_parser/ -q
```

Fixtures are generated from scratch (never committed) by
`tests/docx_parser/fixtures/make_fixtures.py`.
