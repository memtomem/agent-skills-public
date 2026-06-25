# pptx-parser internals

All logic lives in `scripts/pptx_lib.py`; `pptx_parse.py` is a thin CLI.

## 1. Geometry ordering (the keystone)

Slides have no reading order — shapes are placed by `top`/`left` (EMU).
`_iter_shapes_in_order()` flattens group shapes recursively and sorts by
`(top, left)`, the slide analogue of top-to-bottom, left-to-right reading. This
is why a flat z-order dump scrambles slides and this skill doesn't.

`_overlap()` checks whether two text shapes' bounding boxes intersect; if any do,
the geometric order is genuinely ambiguous and the slide is flagged
`overlapping-shapes-order-ambiguous`.

## 2. Text frames

`_emit_text_frame()` walks paragraphs. The title placeholder is *not* re-emitted
as an element (it's captured once as `slide["title"]` and shown in the header).

**Bullet classification.** A paragraph is a `list_item` when its own `pPr`
carries an explicit bullet (`a:buChar`/`a:buAutoNum`), or — when the bullet is
left implicit — when the shape is a **body placeholder** (`_is_body_placeholder`:
BODY/OBJECT/SUBTITLE) or the paragraph is indented (`level > 0`). An explicit
`a:buNone` forces `paragraph`. This fixes the common case where the *first*
bullet of a body placeholder is `level 0` yet still a list item — it used to
render as prose. `list_item` carries its `level` (indent depth) for nested
bullets; the Markdown indents accordingly.
Speaker notes (`slide.notes_slide.notes_text_frame`) are appended as a `note`
element with `note: "speaker-notes"`.

## 3. Tables (`parse_table`)

`shape.has_table` → walk `table.cell(r, c)`. python-pptx exposes merges directly:
`cell.is_spanned` (a covered follower, emitted blank), `cell.is_merge_origin`
with `cell.span_height`/`cell.span_width` (→ a span `{rowspan, colspan}` on the
anchor). Rendering: HTML with `rowspan`/`colspan` when spans exist, else GFM.

## 4. Charts (`parse_chart`) — exact, not vision

`shape.has_chart` → the chart's data is in the XML, so it is read precisely:
`chart.plots[0].categories` and, per `chart.series`, `series.name` +
`series.values`. This is the big advantage over a chart baked into a PDF (pixels):
no vision needed. The `kind` is `chart.chart_type` (an enum repr); `title` comes
from `chart_title` when present.

## 5. Pictures & confidence

Pictures (`MSO_SHAPE_TYPE.PICTURE`) are noted but not extracted. An **image-only
slide** (pictures, no text) sets a slide-level **`needs_vision: true`** and the
`needs-vision` flag, so callers can route it to OCR/transcription deterministically
(parity with pdf-parser) rather than inferring intent from a low score. Per-slide
`confidence` = min of caps:

| condition | cap | flag |
|-----------|-----|------|
| overlapping text shapes | 0.70 | `overlapping-shapes-order-ambiguous` |
| grouped shapes | 0.85 | `grouped-shapes` |
| picture(s) but no text | 0.40 | `image-only-slide` + `needs-vision` |
| merged-cell table | 0.80 | `table-merged-cells` |
| chart present | (no penalty) | `has-chart` |
| nothing extracted | 0.50 | `empty-slide` |

Document-level `min_confidence` and `verify_slides` (< 0.75) surface risky
slides; `vision_slides` lists every slide with `needs_vision`.

## 6. JSON schema

```
document = { source, slide_count, min_confidence,
             verify_slides[], vision_slides[], slides[] }
slide = { index, title, confidence, needs_vision: bool, flags[], elements[] }
Element = {
  type: "heading"|"paragraph"|"list_item"|"table"|"chart"|"image"|"note",
  slide: int, text?: str,
  level?: int,                                              # list_item indent depth
  rows?: [[str,...]], spans?: [{row,col,rowspan,colspan}],   # table
  chart?: {kind, title, categories[], series:[{name, values[]}]}  # chart
}
```

## 7. Known limitations

- Picture content is not extracted; an image-only slide is flagged
  `image-only-slide` + `needs_vision` for a vision pass.
- Geometric order can still be wrong for heavily overlapping layouts (flagged).
- SmartArt is treated as shapes/text, not reconstructed as a diagram.
- Animation/build order is ignored — only final slide content is read.
