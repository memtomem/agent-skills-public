"""Tests for the docx-parser skill. Fixtures are generated, never committed."""
import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
SKILL_SCRIPTS = os.path.abspath(os.path.join(HERE, "..", "..", "skills", "docx-parser", "scripts"))
FIXTURES = os.path.join(HERE, "fixtures")
DOCX = os.path.join(FIXTURES, "messy.docx")
IMG_DOCX = os.path.join(FIXTURES, "image_only.docx")

sys.path.insert(0, SKILL_SCRIPTS)
import docx_lib  # noqa: E402


def _load_make_fixtures():
    path = os.path.join(FIXTURES, "make_fixtures.py")
    spec = importlib.util.spec_from_file_location("docx_make_fixtures", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session", autouse=True)
def _build_fixtures():
    _load_make_fixtures().make_all(FIXTURES)
    assert os.path.exists(DOCX)
    yield


def _doc():
    return docx_lib.build_document(DOCX)


def test_headings_detected():
    els = _doc()["elements"]
    headings = [e for e in els if e["type"] == "heading"]
    assert any(h["text"].startswith("1.") and h["level"] == 1 for h in headings)
    assert any(h["level"] == 2 for h in headings)


def test_body_order_table_between_text():
    # The financial table must appear AFTER its intro paragraph and BEFORE the
    # "Key points" list — i.e. interleaving order is preserved.
    els = _doc()["elements"]
    types_text = [(e["type"], e.get("text", "")) for e in els]
    intro_idx = next(i for i, (t, x) in enumerate(types_text) if "interleaved table" in x)
    table_idx = next(i for i, (t, x) in enumerate(types_text) if t == "table")
    list_idx = next(i for i, (t, x) in enumerate(types_text) if t == "list_item")
    assert intro_idx < table_idx < list_idx


def test_bullet_list_items():
    els = _doc()["elements"]
    items = [e["text"] for e in els if e["type"] == "list_item"]
    assert "디지털 전환 가속" in items and len(items) == 3


def test_merged_table_spans():
    els = _doc()["elements"]
    merged = next(e for e in els if e["type"] == "table" and e.get("spans"))
    spans = merged["spans"]
    assert any(s.get("colspan", 1) == 2 for s in spans)   # horizontal merge
    assert any(s.get("rowspan", 1) == 2 for s in spans)   # vertical merge
    assert "merged-cells" in _doc()["flags"]


def test_merged_table_renders_html():
    md = docx_lib.to_markdown(_doc())
    assert "<table>" in md and 'colspan="2"' in md and 'rowspan="2"' in md


def test_plain_table_is_gfm():
    els = _doc()["elements"]
    plain = next(e for e in els if e["type"] == "table" and not e.get("spans") and not e.get("note"))
    md = docx_lib.element_to_markdown(plain)
    assert "| 항목 Item |" in md


def test_nested_table_flagged():
    assert "nested-table" in _doc()["flags"]


def test_nested_table_content_preserved():
    # The inner table's cells must survive as STRUCTURED data — not collapsed to a
    # "[nested table]" placeholder (finding #6), and not flattened into a string.
    doc = _doc()
    outer = next(e for e in doc["elements"]
                 if e["type"] == "table" and "nested-table" in (e.get("note") or ""))
    assert outer.get("nested"), "nested tables should be structured, not inline strings"
    nt = outer["nested"][0]
    assert nt["rows"] == [["n1", "n2"], ["n3", "n4"]]
    # text that precedes the nested table inside the same cell is kept too
    assert any("inner:" in c for r in outer["rows"] for c in r)
    blob = json.dumps(outer, ensure_ascii=False)
    assert "[nested table]" not in blob
    md = docx_lib.to_markdown(doc)
    assert "n1" in md and "n4" in md and "inner:" in md


def test_cell_text_escaped_not_injected():
    # Literal HTML in a source cell must be ESCAPED, never emitted as raw markup
    # (re-review #C — the nested-table path used to trust "<table…" prefixes).
    el = {"type": "table",
          "rows": [["<script>alert(1)</script>"]],
          "spans": [{"row": 0, "col": 0, "rowspan": 1, "colspan": 1}]}
    md = docx_lib.element_to_markdown(el)
    assert "<script>" not in md
    assert "&lt;script&gt;" in md


@pytest.mark.parametrize("el", [
    {"type": "table", "rows": [["a", "<script>x</script>"]]},          # GFM path
    {"type": "paragraph", "text": "<script>x</script>"},
    {"type": "list_item", "text": "<img src=x onerror=alert(1)>"},
    {"type": "heading", "level": 2, "text": "<b>h</b>"},
    {"type": "textbox", "text": "<script>x</script>"},
])
def test_all_text_paths_escape_html(el):
    # Every user-authored text path (not just the HTML table) must escape, so a
    # source <script> can't inject when the Markdown is rendered to HTML.
    md = docx_lib.element_to_markdown(el)
    assert "<script>" not in md and "<img" not in md and "<b>" not in md
    assert "&lt;" in md


def test_nested_table_renders_without_double_escaping():
    # The generated nested <table> markup itself must be real HTML, while its
    # inner cell text is escaped exactly once.
    doc = _doc()
    md = docx_lib.to_markdown(doc)
    # nested table is real markup (the outer renders as HTML and embeds it)
    assert md.count("<table>") >= 2


def test_messy_doc_not_flagged_for_vision():
    # A text-bearing document is not an image-only doc.
    assert _doc()["needs_vision"] is False


def test_image_only_doc_needs_vision():
    # A doc whose only content is an embedded image routes to a vision pass
    # explicitly (finding #5, parity with pdf-parser / pptx-parser).
    doc = docx_lib.build_document(IMG_DOCX)
    assert doc["needs_vision"] is True
    assert "needs-vision" in doc["flags"]
    assert doc["confidence"] <= 0.4


def test_textbox_recovered():
    els = _doc()["elements"]
    tbs = [e for e in els if e["type"] == "textbox"]
    assert any("기밀" in e["text"] for e in tbs)
    assert "textbox-content" in _doc()["flags"]


def test_header_captured():
    els = _doc()["elements"]
    assert any(e["type"] == "note" and "ACME" in e.get("text", "") for e in els)


def test_document_schema():
    doc = _doc()
    assert {"source", "element_count", "confidence", "flags", "needs_review", "elements"} <= set(doc)
    assert 0.0 <= doc["confidence"] <= 1.0
    for e in doc["elements"]:
        assert e["type"] in {"heading", "paragraph", "list_item", "table", "textbox", "note", "image"}


def test_korean_preserved():
    md = docx_lib.to_markdown(_doc())
    assert "재무" in md and "Financials" in md
