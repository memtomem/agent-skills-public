"""Tests for the xlsx-parser skill. Fixtures are generated, never committed."""
import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
SKILL_SCRIPTS = os.path.abspath(os.path.join(HERE, "..", "..", "skills", "xlsx-parser", "scripts"))
FIXTURES = os.path.join(HERE, "fixtures")
XLSX = os.path.join(FIXTURES, "messy.xlsx")

sys.path.insert(0, SKILL_SCRIPTS)
import xlsx_lib  # noqa: E402


def _load_make_fixtures():
    path = os.path.join(FIXTURES, "make_fixtures.py")
    spec = importlib.util.spec_from_file_location("xlsx_make_fixtures", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session", autouse=True)
def _build_fixtures():
    _load_make_fixtures().make_all(FIXTURES)
    assert os.path.exists(XLSX)
    yield


def _doc():
    return xlsx_lib.build_document(XLSX)


# --- region detection -------------------------------------------------------

def test_sheets_enumerated():
    doc = _doc()
    names = [s["name"] for s in doc["sheets"]]
    assert names == ["Finance", "Merged", "Formulas", "NoGutter", "Chart",
                     "AllFormula", "Empty"]


def test_finance_two_stacked_tables_detected():
    doc = _doc()
    fin = next(s for s in doc["sheets"] if s["name"] == "Finance")
    tables = [e for e in fin["elements"] if e["type"] == "table"]
    assert len(tables) == 2, "stacked tables separated by a blank-row gutter"
    assert "multiple-table-regions" in fin["flags"]


def test_finance_header_not_row_one():
    # The real header ('항목 Item') is row 4, under a title + a note strip.
    doc = _doc()
    fin = next(s for s in doc["sheets"] if s["name"] == "Finance")
    first_table = next(e for e in fin["elements"] if e["type"] == "table")
    assert first_table["rows"][0][0].startswith("항목")
    # The title/note strips become note elements, not table rows.
    notes = [e for e in fin["elements"] if e["type"] == "note"]
    assert any("Financial Summary" in n.get("text", "") for n in notes)


def test_finance_values_intact():
    doc = _doc()
    fin = next(s for s in doc["sheets"] if s["name"] == "Finance")
    table = next(e for e in fin["elements"] if e["type"] == "table")
    flat = [c for r in table["rows"] for c in r]
    assert "1239" in flat and "매출 Revenue" in flat


# --- merged cells -----------------------------------------------------------

def test_merged_cells_flagged_and_spanned():
    doc = _doc()
    mg = next(s for s in doc["sheets"] if s["name"] == "Merged")
    assert "merged-cells" in mg["flags"]
    table = next(e for e in mg["elements"] if e["type"] == "table")
    assert table.get("spans"), "merged anchor should produce a span entry"
    assert any(s.get("colspan", 1) >= 2 for s in table["spans"])


def test_merged_renders_html_with_colspan():
    doc = _doc()
    md = xlsx_lib.to_markdown(doc)
    assert "<table>" in md and "colspan=" in md


# --- header split with no blank gutter (finding #1) -------------------------

def test_nogutter_preamble_split_to_note():
    doc = _doc()
    sh = next(s for s in doc["sheets"] if s["name"] == "NoGutter")
    table = next(e for e in sh["elements"] if e["type"] == "table")
    # The detected header (row 2) becomes the first table row, not the title.
    assert table["rows"][0] == ["Region", "Units", "Revenue"]
    # The title directly above the header (no blank gutter) is split off as a note
    notes = [e for e in sh["elements"] if e["type"] == "note"]
    assert any("Q3 Sales by Region" in n.get("text", "") for n in notes)
    # ...and it is NOT smuggled into the table body.
    flat = [c for r in table["rows"] for c in r]
    assert not any("Q3 Sales by Region" in c for c in flat)


# --- formulas ---------------------------------------------------------------

def test_formula_cells_flagged():
    doc = _doc()
    fm = next(s for s in doc["sheets"] if s["name"] == "Formulas")
    assert "formula-cells" in fm["flags"]
    table = next(e for e in fm["elements"] if e["type"] == "table")
    assert "contains-formula" in (table.get("note") or "")


def test_formula_missing_cache_is_honest_not_blank():
    # openpyxl writes no formula cache, so the note must NOT claim "cached values
    # shown"; instead it flags the gap and the cell surfaces the formula itself.
    doc = _doc()
    fm = next(s for s in doc["sheets"] if s["name"] == "Formulas")
    assert "formula-no-cache" in fm["flags"]
    table = next(e for e in fm["elements"] if e["type"] == "table")
    note = table.get("note") or ""
    assert "no cached values" in note
    assert "cached values shown" not in note
    # The Total column carries the formula string as provenance, not a blank.
    flat = [c for r in table["rows"] for c in r]
    assert any(c.startswith("=") and "*" in c for c in flat)


def test_all_formula_region_not_dropped():
    # A region that is ENTIRELY uncached formulas must not be silently dropped as
    # empty — detection runs on the formula workbook (re-review #A).
    doc = _doc()
    sh = next(s for s in doc["sheets"] if s["name"] == "AllFormula")
    assert "empty-sheet" not in sh["flags"]
    table = next(e for e in sh["elements"] if e["type"] == "table")
    flat = [c for r in table["rows"] for c in r if c]
    assert flat and all(c.startswith("=") for c in flat)
    assert any("1+2" in c for c in flat)


# --- confidence + schema ----------------------------------------------------

def test_empty_sheet_low_confidence():
    doc = _doc()
    em = next(s for s in doc["sheets"] if s["name"] == "Empty")
    assert "empty-sheet" in em["flags"]
    assert em["confidence"] <= 0.5


# --- charts (finding #3) ----------------------------------------------------

def test_chart_values_resolved():
    doc = _doc()
    sh = next(s for s in doc["sheets"] if s["name"] == "Chart")
    chart = next(e for e in sh["elements"] if e["type"] == "chart")
    ch = chart["chart"]
    # Categories and series values are resolved exactly from the XML/cells —
    # not left as bare A1 references.
    assert ch.get("categories") == ["Q1", "Q2", "Q3", "Q4"]
    series = ch.get("series") or []
    assert series, "series should be resolved, not just refs"
    assert series[0]["values"] == ["260", "295", "330", "354"]


def test_chart_renders_resolved_data_in_markdown():
    doc = _doc()
    md = xlsx_lib.to_markdown(doc)
    assert "[chart]" in md and "260" in md and "Q1" in md


def test_chart_table_cell_pipe_escaped():
    # A chart label containing '|' must not break the pipe-table layout.
    el = {"type": "chart", "sheet": "S", "text": "c",
          "chart": {"kind": "Bar", "categories": ["a|b"],
                    "series": [{"name": "s|1", "values": ["1|2"]}]}}
    md = xlsx_lib.element_to_markdown(el)
    assert "a\\|b" in md and "s\\|1" in md and "1\\|2" in md


def test_document_schema():
    doc = _doc()
    assert {"source", "sheet_count", "min_confidence", "verify_sheets", "sheets"} <= set(doc)
    assert doc["sheet_count"] == 7
    for s in doc["sheets"]:
        assert 0.0 <= s["confidence"] <= 1.0
        for e in s["elements"]:
            assert e["type"] in {"heading", "paragraph", "note", "table", "chart"}


def test_markdown_escapes_html_in_text():
    # User content with HTML must be escaped in Markdown (GFM cells + notes), so
    # a source "<script>" can't inject when the Markdown is rendered to HTML.
    table = {"type": "table", "sheet": "S", "rows": [["a", "<script>x</script>"]]}
    md = xlsx_lib.element_to_markdown(table)
    assert "<script>" not in md and "&lt;script&gt;" in md
    note = {"type": "note", "sheet": "S", "text": "<b>hi</b>"}
    assert "<b>" not in xlsx_lib.element_to_markdown(note)


def test_gfm_for_regular_table():
    # The Merged sheet uses HTML; a plain table (Formulas) stays GFM.
    doc = _doc()
    fm = next(s for s in doc["sheets"] if s["name"] == "Formulas")
    table = next(e for e in fm["elements"] if e["type"] == "table")
    md = xlsx_lib.element_to_markdown(table)
    assert "| Item |" in md or "| Item " in md
