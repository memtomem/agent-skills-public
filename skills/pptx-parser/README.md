# pptx-parser

*[한국어 가이드 → README.ko.md](README.ko.md)*

A Claude skill for parsing **PowerPoint decks** (`.pptx`) into clean
**Markdown** and a structured **JSON** element tree, in correct reading order.
It pulls out titles, bullet text, tables (merged cells included), charts
(categories and series values recovered exactly from the XML), pictures,
grouped shapes, and speaker notes. Handles Korean + English.

## Why

A slide is a free canvas — shapes are positioned anywhere, so the order
python-pptx returns them (z-order) is **not** the order a human reads them. A
flat text dump scrambles slides and drops what matters most: tables, charts
(whose data lives inside the XML and can be read *exactly*), grouped shapes, and
the speaker notes. This skill instead, per slide, **orders shapes by geometry**
(top-to-bottom, left-to-right — the slide analogue of reading order), recurses
into grouped shapes, and extracts tables, charts, pictures, and notes into the
same structured element tree as the other parsers, flagging the slides that need
a human look.

## Install

### Claude Code / Claude Desktop / Cowork

Drop the skill folder into a skills directory and your agent picks it up
automatically. From the repository root:

```bash
mkdir -p ~/.claude/skills
cp -R skills/pptx-parser ~/.claude/skills/
```

If you are already inside `skills/pptx-parser/`, use:

```bash
mkdir -p ~/.claude/skills/pptx-parser
cp -R . ~/.claude/skills/pptx-parser/
```

To scope it to one project, copy the folder into that project's
`.claude/skills/` directory instead. You can also build
`dist/pptx-parser.skill` from the repository root and use the app's **Save
skill** button:

```bash
uv run python scripts/build_all.py pptx-parser
```

Once installed, just mention a `.pptx` file — “이 PPT에서 텍스트랑 표, 차트
데이터까지 뽑아줘”, “convert this deck.pptx to markdown with the chart
numbers” — and the skill triggers; no special syntax needed. You can also invoke
it explicitly with `/pptx-parser`.

### Codex, Cursor, or any shell-capable agent

The `scripts/` are ordinary Python CLIs (dep: `python-pptx`; `markitdown` is an
optional cross-check). Copy `scripts/` into your project,
`pip install python-pptx`, and point your agent at `SKILL.md` for the
parse → check-flagged-slides → vision-transcribe → verify playbook.

## Workflow

Most users should ask their agent in plain language first:

- “이 PPT에서 텍스트랑 표, 차트 데이터까지 뽑아줘.”
- “Convert this deck.pptx to Markdown with the chart numbers.”
- “Extract every slide's content and the speaker notes as JSON.”
- “이 프레젠테이션에서 표만 뽑아줘.” / “Pull the tables out of this presentation.”

The agent orders each slide's shapes by geometry, reads tables/charts/notes,
flags image-only or overlapping slides, and performs vision transcription only
for the slides that need it.

For direct command-line use:

```bash
cd scripts

# parse -> OUTDIR/INPUT.md + INPUT.json
python pptx_parse.py INPUT.pptx -o OUTDIR

# add markitdown as a second opinion -> OUTDIR/INPUT.markitdown.md
python pptx_parse.py INPUT.pptx -o OUTDIR --crosscheck
```

See `SKILL.md` for the full workflow and `references/pptx_internals.md` for the
geometry ordering, chart/table extraction, the confidence model, and the JSON
element schema.

## Slide flags

Each slide carries a confidence score and a list of `flags`; low-confidence
slides also get an inline `🔎` note in the Markdown.

| flag | meaning | what to do |
|------|---------|------------|
| `image-only-slide` | no extractable text — the message is in the picture | render and transcribe it with vision separately |
| `needs-vision` | the slide needs a visual pass (e.g. image-only) | listed in `vision_slides`; transcribe with vision |
| `overlapping-shapes-order-ambiguous` | shapes overlap, so geometric order may be wrong | eyeball that slide's order against the original |
| `grouped-shapes` | a group was flattened into reading order | check it if the layering encodes meaning |
| `table-merged-cells` | the table has merged cells (emitted as `<table>` HTML) | confirm the merged spans read correctly |
| `has-chart` | chart data was recovered from the XML | confirm each series got the labels you expect |
| `empty-slide` | the slide has no extractable content | nothing to extract |

## Dependencies

`python-pptx` is required. `markitdown` is optional and used only for
`--crosscheck`.

```bash
pip install python-pptx
# optional, for --crosscheck:
pip install markitdown
```

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| A slide came out with no text | It's an `image-only-slide` (a screenshot or diagram) — the content lives in the picture; transcribe it with vision. Pictures are noted but not extracted here. |
| Shapes read out of order | The slide has `overlapping-shapes-order-ambiguous` — geometric order can be wrong when shapes overlap; eyeball it against the original. |
| Chart values look off | Categories and series are read straight from the XML, so they're exact — but confirm each series got the labels you expect (`has-chart`). |
| Chart type shows as `COLUMN_CLUSTERED (51)` | That's the chart's enum kind shown because it has no title — it's the type, not an error. |
| A picture wasn't extracted | By design — pictures are noted in the Markdown as a comment, not extracted as image files. |
| `ModuleNotFoundError: pptx` | `pip install python-pptx`, and run the scripts from the `scripts/` directory. |

## Tests

```bash
python -m pytest tests/pptx_parser/ -q
```

Fixtures are generated from scratch (never committed) by
`tests/pptx_parser/fixtures/make_fixtures.py`.
