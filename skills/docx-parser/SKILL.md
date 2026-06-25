---
name: docx-parser
description: >-
  Parse messy, unstructured Word documents (.docx) into clean Markdown plus a
  structured JSON element tree — preserving the things a naive text dump loses.
  Use whenever a .docx mixes text with tables in between, nested tables, merged
  cells, bullet/numbered lists, text boxes, headers/footers, tracked changes, or
  comments, and you want faithful content for RAG/LLM or downstream code.
  Triggers: "이 워드 문서에서 본문이랑 표 구조 그대로 뽑아줘", "extract everything from
  this .docx to markdown keeping tables", "convert this contract.docx to JSON",
  "pull the tables and text boxes out of this Word file", "이 docx를 마크다운으로
  정리해줘". Walks the document in body order (text and tables interleaved
  correctly), keeps merged cells as HTML, recovers text boxes, and flags tracked
  changes / nested tables / comments for review. Handles Korean+English. This is
  for READING CONTENT out of a Word file — NOT for authoring or editing a new
  .docx (use the docx authoring skill), NOT for PDFs (use pdf-parser), and NOT
  for Excel or PowerPoint files.
---

# Unstructured Word Parser

## Why this skill exists

A `.docx` is structured XML, yet the obvious extraction — joining
`doc.paragraphs` — quietly drops or scrambles real content. python-docx exposes
paragraphs and tables as *separate* lists, so a table sitting between two
paragraphs loses its place. Tables nest inside cells; cells merge with
`gridSpan`/`vMerge`; bullet lists, text boxes (`w:txbxContent`), headers/footers,
tracked changes, and comments all live in places a flat read never visits.

So this skill walks the document **in body order** and emits a structured element
tree — the same shape as `pdf-parser` / `xlsx-parser` — with a confidence score
and flags so the risky documents surface for a human/LLM check.

## Workflow

```bash
cd <skill>/scripts
python docx_parse.py /path/to/INPUT.docx -o /path/to/OUTDIR
python docx_parse.py /path/to/INPUT.docx -o /path/to/OUTDIR --crosscheck   # markitdown second opinion
```

Then:

1. **Read the Markdown** against the original. Body order should match: text,
   the interleaved tables, lists, all where they belong.
2. **Check the flags / `🔎` note first.** Flags: `tracked-changes-present`,
   `textbox-content`, `nested-table`, `merged-cells`, `comments-present`,
   `embedded-images-not-extracted`, `needs-vision` (image-only document).
3. **Tracked changes**: the extracted text reflects the current markup; if the
   document has pending insertions/deletions, decide whether you want the
   accepted or original text and confirm against Word.
4. **Merged-cell tables** render as HTML — confirm the spans landed correctly.
5. **Text boxes** are pulled out as `📦 [text box]` blocks; verify none were
   missed (complex VML can hide more).
6. **Embedded images** are counted but not extracted in this pass — if you need
   them, open the .docx (it's a zip) under `word/media/`. A document that is
   *only* images (no text) sets `needs_vision: true` so you can route it to a
   vision pass.

## Output format

**Markdown**: headings `#`/`##`/…, paragraphs as prose, lists as `-`, tables as
GFM (or `<table>` HTML when merged), text boxes as `> 📦 [text box] …`,
headers/footers and notes as HTML comments. A low-confidence document gets a top
`🔎` note.

**JSON** element tree:

```json
{
  "source": "contract.docx",
  "element_count": 15,
  "confidence": 0.75,
  "flags": ["merged-cells", "nested-table", "textbox-content"],
  "needs_review": false,
  "needs_vision": false,
  "elements": [
    {"type": "heading", "text": "1. 개요 Overview", "level": 1},
    {"type": "paragraph", "text": "..."},
    {"type": "table", "rows": [["항목 Item","2024","2025"], ["매출 Revenue","1050","1239"]]},
    {"type": "list_item", "text": "디지털 전환 가속"},
    {"type": "table", "rows": [...], "spans": [{"row":0,"col":1,"rowspan":1,"colspan":2}]},
    {"type": "textbox", "text": "중요 공지 …", "note": "text recovered from a text box"}
  ]
}
```

Element `type` is one of `heading`, `paragraph`, `list_item`, `table`, `textbox`,
`note`, `image`. Table elements may carry `spans` (merged-cell anchors, 0-based),
`nested` (nested tables as structured `{row, col, rows, spans}` by cell position),
and a `note` (e.g. `nested-table`).

## Relationship to markitdown

markitdown converts `.docx` to markdown well for simple documents. This skill
adds what it flattens: correct **body order**, **merged-cell fidelity** (HTML),
**nested-table** detection, **text-box** recovery, and **confidence flags**. Use
`--crosscheck` to get both and diff them.

## Tips and failure modes

- **A nested table is kept as structured `nested` data on the outer table** (its
  rows preserved, keyed by parent-cell position) and rendered as HTML inside that
  cell — not collapsed to a placeholder. All cell text is escaped, so the nesting
  is faithful and safe; deeply nested tables stay correct but get dense.
- **Tracked changes**: text is the current markup; accept/reject in Word first if
  you need a specific revision state.
- **Complex text boxes / SmartArt** in DrawingML may not fully surface — the flag
  warns you to check.

## Reference

`references/docx_internals.md` documents body-order iteration, merge handling,
the confidence model, and the JSON schema. `scripts/docx_lib.py` holds the logic.
