"""Tests for the pptx-parser skill. Fixtures are generated, never committed."""
import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
SKILL_SCRIPTS = os.path.abspath(os.path.join(HERE, "..", "..", "skills", "pptx-parser", "scripts"))
FIXTURES = os.path.join(HERE, "fixtures")
PPTX = os.path.join(FIXTURES, "deck.pptx")

sys.path.insert(0, SKILL_SCRIPTS)
import pptx_lib  # noqa: E402


def _load_make_fixtures():
    path = os.path.join(FIXTURES, "make_fixtures.py")
    spec = importlib.util.spec_from_file_location("pptx_make_fixtures", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session", autouse=True)
def _build_fixtures():
    _load_make_fixtures().make_all(FIXTURES)
    assert os.path.exists(PPTX)
    yield


def _doc():
    return pptx_lib.build_document(PPTX)


def test_slide_count_and_titles():
    doc = _doc()
    assert doc["slide_count"] == 3
    assert doc["slides"][0]["title"].startswith("1.")
    assert "Financials" in doc["slides"][1]["title"]


def test_bullets_captured():
    doc = _doc()
    s1 = doc["slides"][0]
    for bullet in ["디지털 전환 가속", "해외 시장 확대", "R&D 투자 증대"]:
        match = next((e for e in s1["elements"] if bullet in e.get("text", "")), None)
        assert match is not None
        assert match["type"] == "list_item", f"{bullet!r} should be a list item, not prose"


def test_level0_bullet_is_list_not_paragraph():
    # The FIRST bullet in a body placeholder is level 0, but it's still a list
    # item — PowerPoint just leaves its bullet implicit (finding #4).
    doc = _doc()
    s1 = doc["slides"][0]
    first = next(e for e in s1["elements"] if "디지털 전환 가속" in e.get("text", ""))
    assert first["type"] == "list_item"
    # level is present even at depth 0 — it's a real indent depth, not "absent"
    assert "level" in first and first["level"] == 0
    # nested bullets keep their indent depth
    nested = next(e for e in s1["elements"] if "해외 시장 확대" in e.get("text", ""))
    assert nested.get("level", 0) >= 1
    md = pptx_lib.to_markdown(doc)
    assert "- 디지털 전환 가속" in md


def test_speaker_notes_captured():
    doc = _doc()
    s1 = doc["slides"][0]
    notes = [e for e in s1["elements"] if e["type"] == "note"]
    assert any("발표자 노트" in e.get("text", "") for e in notes)


def test_merged_table_html_with_colspan():
    doc = _doc()
    s2 = doc["slides"][1]
    table = next(e for e in s2["elements"] if e["type"] == "table")
    assert table.get("spans"), "merged header cell should produce a span"
    assert any(s.get("colspan", 1) == 2 for s in table["spans"])
    assert "table-merged-cells" in s2["flags"]
    md = pptx_lib.to_markdown(doc)
    assert "<table>" in md and 'colspan="2"' in md


def test_chart_data_extracted_exactly():
    doc = _doc()
    s2 = doc["slides"][1]
    chart = next(e for e in s2["elements"] if e["type"] == "chart")
    assert "has-chart" in s2["flags"]
    cats = chart["chart"]["categories"]
    series = chart["chart"]["series"][0]
    assert cats == ["Q1", "Q2", "Q3", "Q4"]
    assert series["values"] == [260.0, 295.0, 330.0, 354.0]


def test_image_only_slide_flagged():
    doc = _doc()
    s3 = doc["slides"][2]
    assert "image-only-slide" in s3["flags"]
    assert s3["confidence"] <= 0.4
    assert 3 in doc["verify_slides"]


def test_image_only_slide_needs_vision():
    # Explicit needs_vision routing (parity with pdf-parser), not just low score.
    doc = _doc()
    s3 = doc["slides"][2]
    assert s3["needs_vision"] is True
    assert "needs-vision" in s3["flags"]
    assert 3 in doc["vision_slides"]
    # a normal text slide must NOT be flagged for vision
    assert doc["slides"][0]["needs_vision"] is False


def test_title_not_duplicated_in_elements():
    doc = _doc()
    s2 = doc["slides"][1]
    # Title is at slide level; it should not also appear as a heading element.
    headings = [e for e in s2["elements"] if e["type"] == "heading"]
    assert headings == []


def test_markdown_escapes_html_in_text():
    # User content with HTML must be escaped in Markdown (text + GFM cells).
    para = {"type": "paragraph", "slide": 1, "text": "<script>x</script>"}
    assert "<script>" not in pptx_lib.element_to_markdown(para)
    table = {"type": "table", "slide": 1, "rows": [["<img onerror=1>", "b"]]}
    md = pptx_lib.element_to_markdown(table)
    assert "<img" not in md and "&lt;" in md


def test_document_schema():
    doc = _doc()
    assert {"source", "slide_count", "min_confidence", "verify_slides", "slides"} <= set(doc)
    for s in doc["slides"]:
        assert 0.0 <= s["confidence"] <= 1.0
        for e in s["elements"]:
            assert e["type"] in {"heading", "paragraph", "list_item", "table", "chart", "image", "note"}


def test_shapes_geometry_order():
    # Slide 2: the title sits above the table/chart, which sit above nothing —
    # the table (left) should be emitted before the chart (right) at the same row.
    doc = _doc()
    s2 = doc["slides"][1]
    types = [e["type"] for e in s2["elements"]]
    assert types.index("table") < types.index("chart")
