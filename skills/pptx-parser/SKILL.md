---
name: pptx-parser
description: >-
  Parse PowerPoint decks (.pptx) into clean Markdown plus a structured JSON
  element tree, in correct reading order. Use whenever you need the CONTENT out
  of a slide deck — titles, bullet text, tables (merged cells included), charts
  (categories and series values, recovered exactly from the XML, not guessed),
  pictures, grouped shapes, and speaker notes — for RAG/LLM or downstream code.
  Triggers: "이 PPT에서 텍스트랑 표, 차트 데이터까지 뽑아줘", "convert this deck.pptx
  to markdown with the chart numbers", "extract every slide's content and the
  speaker notes as JSON", "pull the tables out of this presentation",
  "이 슬라이드 내용 정리해줘". Orders each slide's shapes by geometry (top-to-bottom,
  left-to-right) because slides have no inherent reading order, and flags
  image-only or overlapping slides for review. Handles Korean+English. This is
  for READING CONTENT out of a deck — NOT for authoring or editing a new .pptx
  (use the pptx authoring skill), NOT for PDFs (use pdf-parser), and NOT for
  Word or Excel files.
---

# Unstructured PowerPoint Parser

## Why this skill exists

A slide is a free canvas — shapes are positioned anywhere, so the order
python-pptx returns them (z-order) is not the order a human reads them. A flat
text dump scrambles slides and drops what matters most: tables, charts (whose
data lives in the XML and can be read *exactly*), grouped shapes, and the
speaker notes. So this skill, per slide, **orders shapes by geometry** (the slide
analogue of reading order), recurses into groups, and extracts tables, charts,
pictures, and notes into the same structured element tree as the other parsers,
with confidence flags for the slides that need a human look.

## Workflow

```bash
cd <skill>/scripts
python pptx_parse.py /path/to/INPUT.pptx -o /path/to/OUTDIR
python pptx_parse.py /path/to/INPUT.pptx -o /path/to/OUTDIR --crosscheck   # markitdown second opinion
```

Then:

1. **Read the Markdown** — one `# Slide N: title` section each, shapes in reading
   order, chart data spelled out, notes included.
2. **Check flagged slides first** (`verify_slides` / the `🔎` note). Flags:
   `image-only-slide`, `needs-vision`, `overlapping-shapes-order-ambiguous`,
   `grouped-shapes`, `table-merged-cells`, `has-chart`, `empty-slide`.
3. **Image-only slides** (`image-only-slide`, `needs_vision: true`, listed in
   `vision_slides`) carry no extractable text — if the picture holds the message
   (a screenshot, a diagram), render/transcribe it with vision separately.
   Pictures are noted but not extracted here.
4. **Overlapping shapes** mean the geometric order may be wrong — eyeball that
   slide's order against the original.
5. **Charts**: categories + each series' values are read straight from the XML,
   so they're exact — but confirm the series got the labels you expect.

## Output format

**Markdown**: `# Slide N: title`, bullet text as `-`, tables as GFM (or `<table>`
HTML when merged), charts as a `**[chart]**` block with each series'
`category=value` pairs, speaker notes as `> 🗒 [notes] …`, pictures as a comment.
Low-confidence slides get an inline `🔎` note.

**JSON** element tree:

```json
{
  "source": "deck.pptx",
  "slide_count": 3,
  "min_confidence": 0.4,
  "verify_slides": [3],
  "vision_slides": [3],
  "slides": [
    {
      "index": 2, "title": "2. 재무 Financials", "confidence": 0.8,
      "needs_vision": false,
      "flags": ["table-merged-cells", "has-chart"],
      "elements": [
        {"type": "table", "slide": 2, "rows": [["Region","Sales H1",""], ...],
         "spans": [{"row":0,"col":1,"rowspan":1,"colspan":2}]},
        {"type": "chart", "slide": 2, "text": "Revenue",
         "chart": {"kind": "COLUMN_CLUSTERED (51)", "categories": ["Q1","Q2","Q3","Q4"],
                   "series": [{"name": "Revenue", "values": [260.0, 295.0, 330.0, 354.0]}]}}
      ]
    }
  ]
}
```

Element `type` is one of `heading`, `paragraph`, `list_item`, `table`, `chart`,
`image`, `note`. `list_item` carries its `level` (indent depth); tables may carry
`spans` (merged-cell anchors); charts carry the full `categories`/`series` data.

## Relationship to markitdown

markitdown converts `.pptx` to markdown for simple decks but loses geometric
order, merged-cell structure, and especially **chart data**. This skill recovers
all three. Use `--crosscheck` to get both and diff them.

## Tips and failure modes

- **An image-only slide is low-confidence by design** — the content is in the
  picture; transcribe it with vision if needed.
- **Group shapes are flattened** in reading order; if a group encodes meaning by
  layering, check it.
- **Chart kind shows as an enum** (e.g. `COLUMN_CLUSTERED (51)`) when the chart
  has no title — that's the chart type, not an error.

## Reference

`references/pptx_internals.md` documents geometry ordering, chart/table
extraction, the confidence model, and the JSON schema. `scripts/pptx_lib.py`
holds the logic; `pptx_parse.py` is a thin CLI over it.
