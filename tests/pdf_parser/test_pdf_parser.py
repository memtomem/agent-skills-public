"""Tests for the pdf-parser skill.

Fixtures are generated (never committed) by fixtures/make_fixtures.py, via the
session-scoped autouse fixture below — matching the repo convention used by
hwp-toolkit.
"""
import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
SKILL_SCRIPTS = os.path.abspath(os.path.join(HERE, "..", "..", "skills", "pdf-parser", "scripts"))
FIXTURES = os.path.join(HERE, "fixtures")
PDF = os.path.join(FIXTURES, "report_mixed.pdf")

sys.path.insert(0, SKILL_SCRIPTS)

import pdf_lib  # noqa: E402


def _load_make_fixtures():
    """Load this skill's make_fixtures by path under a unique module name.

    Each skill ships its own fixtures/make_fixtures.py; a plain
    ``import make_fixtures`` would collide across skills when the whole repo
    suite runs (sys.modules caches the first one). Loading by path avoids that.
    """
    path = os.path.join(FIXTURES, "make_fixtures.py")
    spec = importlib.util.spec_from_file_location("pdf_parser_make_fixtures", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session", autouse=True)
def _build_fixtures():
    _load_make_fixtures().make_all(FIXTURES)
    assert os.path.exists(PDF)
    yield


# --- triage -----------------------------------------------------------------

def test_page_count():
    infos = pdf_lib.classify_pages(PDF)
    assert len(infos) == 5


def test_scanned_page_flagged_for_vision():
    infos = pdf_lib.classify_pages(PDF)
    scanned = [i for i in infos if i.route == pdf_lib.ROUTE_SCANNED]
    assert len(scanned) == 1
    assert scanned[0].page == 5
    assert scanned[0].needs_vision is True


def test_table_page_detected():
    infos = pdf_lib.classify_pages(PDF)
    assert infos[2].route == pdf_lib.ROUTE_TABLE
    assert infos[2].table_line_score >= 8


def test_two_column_detected():
    infos = pdf_lib.classify_pages(PDF)
    assert infos[1].columns == 2


def test_figure_page_routed_mixed_vision():
    # Page 4 is a large raster chart with only a short caption — the figure-vision
    # branch (img-heavy page whose data lives in pixels) must fire.
    infos = pdf_lib.classify_pages(PDF)
    fig = infos[3]
    assert fig.route == pdf_lib.ROUTE_MIXED
    assert fig.needs_vision is True
    assert fig.image_area_ratio > 0.45


def test_vision_pages_are_figure_and_scan():
    infos = pdf_lib.classify_pages(PDF)
    # Text/table pages (1-3) read locally; only the raster figure (4) and the
    # scanned page (5) need vision.
    assert {i.page for i in infos if i.needs_vision} == {4, 5}
    assert all(not infos[p - 1].needs_vision for p in (1, 2, 3))


# --- extraction -------------------------------------------------------------

def test_korean_text_preserved():
    doc = pdf_lib.build_document(PDF, os.path.join(FIXTURES, "_assets"))
    md = pdf_lib.to_markdown(doc)
    assert "연차보고서" in md
    assert "Market Analysis" in md


def test_headings_detected():
    doc = pdf_lib.build_document(PDF, os.path.join(FIXTURES, "_assets"))
    headings = [e for p in doc["pages"] for e in p["elements"] if e["type"] == "heading"]
    assert any("연차보고서" in h.get("text", "") for h in headings)


def test_financial_table_extracted():
    doc = pdf_lib.build_document(PDF, os.path.join(FIXTURES, "_assets"))
    tables = [e for p in doc["pages"] for e in p["elements"] if e["type"] == "table"]
    assert len(tables) == 1, "expected exactly one real table (no chart false-positive)"
    rows = tables[0]["rows"]
    header = rows[0]
    assert "2025" in header
    # Spot-check a value survives intact.
    flat = [c for r in rows for c in r]
    assert "1,239" in flat


def test_table_renders_as_gfm_once():
    doc = pdf_lib.build_document(PDF, os.path.join(FIXTURES, "_assets"))
    md = pdf_lib.to_markdown(doc)
    # The financial numbers must appear once (as a table), not duplicated as
    # loose text — the suppression logic depends on table bbox.
    assert md.count("| 매출 Revenue |") == 1
    assert "매출 Revenue\n980" not in md  # not the loose-text form


def test_two_column_reading_order():
    doc = pdf_lib.build_document(PDF, os.path.join(FIXTURES, "_assets"))
    md = pdf_lib.to_markdown(doc)
    # ALL four left-column (Korean) paragraphs must precede ALL four
    # right-column (English) ones — not interleaved row-by-row.
    left = ["국내 시장은", "주요 사업자", "수요는 안정", "규제 환경"]
    right = ["Overseas markets", "Demand is driven", "Local partnerships", "Currency volatility"]
    assert max(md.index(s) for s in left) < min(md.index(s) for s in right)


def test_vision_placeholder_in_markdown():
    doc = pdf_lib.build_document(PDF, os.path.join(FIXTURES, "_assets"))
    md = pdf_lib.to_markdown(doc)
    assert "needs vision transcription" in md


def test_json_schema_shape():
    doc = pdf_lib.build_document(PDF, os.path.join(FIXTURES, "_assets"))
    assert doc["page_count"] == 5
    for p in doc["pages"]:
        assert {"page", "route", "needs_vision", "elements"} <= set(p)
        for e in p["elements"]:
            assert e["type"] in {"heading", "paragraph", "table", "image"}
            assert e["page"] == p["page"]


def test_render_page_png(tmp_path):
    out = str(tmp_path / "p5.png")
    pdf_lib.render_page_png(PDF, 5, out, dpi=120)
    assert os.path.exists(out) and os.path.getsize(out) > 1000


def test_render_page_out_of_range_raises():
    # page 0 / negatives must NOT silently render the wrong page (neg indexing).
    for bad in (0, -1, 99):
        with pytest.raises(pdf_lib.PdfError):
            pdf_lib.render_page_png(PDF, bad, os.path.join(FIXTURES, "_bad.png"))


def test_open_pdf_clean_errors(tmp_path):
    with pytest.raises(pdf_lib.PdfError):
        pdf_lib.classify_pages(str(tmp_path / "does_not_exist.pdf"))
    notpdf = tmp_path / "x.pdf"
    notpdf.write_bytes(b"this is not a pdf")
    with pytest.raises(pdf_lib.PdfError):
        pdf_lib.classify_pages(str(notpdf))


def test_image_elements_extracted():
    doc = pdf_lib.build_document(PDF, os.path.join(FIXTURES, "_assets"))
    images = [e for p in doc["pages"] for e in p["elements"] if e["type"] == "image"]
    assert images, "expected at least one extracted image element (raster figure / scan)"
    for img in images:
        assert os.path.exists(img["path"]) and os.path.getsize(img["path"]) > 0
    md = pdf_lib.to_markdown(doc, rel_assets="assets")
    assert "![" in md and "assets/" in md


def test_to_dict_omits_empty_fields():
    para = pdf_lib.Element(type="paragraph", page=1, bbox=[1.0, 2.0, 3.0, 4.0], text="hi")
    assert para.to_dict() == {"type": "paragraph", "page": 1,
                              "bbox": [1.0, 2.0, 3.0, 4.0], "text": "hi"}
    tbl = pdf_lib.Element(type="table", page=2, rows=[["a", "b"], ["c", "d"]],
                          note="auto-detected")
    # empty text / bbox / level / path are dropped
    assert set(tbl.to_dict()) == {"type", "page", "rows", "note"}


def test_pick_best_table_selection():
    assert isinstance(pdf_lib._HAVE_CAMELOT, bool)
    sparse = ([["a", "b"], ["c", ""]], [0.0, 0.0, 10.0, 10.0])
    rich = ([["a", "b", "c"], ["1", "2", "3"]], None)
    best = pdf_lib._pick_best_table([sparse, rich])
    assert best is not None and best[0] == rich[0]      # richer candidate wins
    assert pdf_lib._pick_best_table([([["x"], ["y"]], None)]) is None  # 1-col rejected
    assert pdf_lib._pick_best_table([([["only one row"]], None)]) is None  # 1-row rejected
    assert pdf_lib._pick_best_table([]) is None


# --- camelot bbox derivation ------------------------------------------------

class _FakeCell:
    """Duck-types camelot's Cell: PDF points, bottom-left origin, x1<x2, y1<y2."""
    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2


class _FakeCamelotTable:
    def __init__(self, cells=None, _bbox=None):
        if cells is not None:
            self.cells = cells
        if _bbox is not None:
            self._bbox = _bbox


def test_camelot_bbox_converts_bottom_left_to_top_left():
    # Cells span x in [50, 300], y (bottom-left origin) in [400, 700] on an
    # 800pt-tall page. Top-left bbox: top = 800-700 = 100, bottom = 800-400 = 400.
    cells = [
        [_FakeCell(50, 600, 175, 700), _FakeCell(175, 600, 300, 700)],
        [_FakeCell(50, 400, 175, 600), _FakeCell(175, 400, 300, 600)],
    ]
    bbox = pdf_lib._camelot_table_bbox(_FakeCamelotTable(cells=cells), page_height=800)
    assert bbox == [50.0, 100.0, 300.0, 400.0]


def test_camelot_bbox_falls_back_to_table_bbox_attr():
    # No cells, but the table exposes its extent directly (older camelot path).
    t = _FakeCamelotTable(cells=[], _bbox=(50, 400, 300, 700))
    assert pdf_lib._camelot_table_bbox(t, page_height=800) == [50.0, 100.0, 300.0, 400.0]


def test_camelot_bbox_none_without_page_height():
    cells = [[_FakeCell(50, 400, 300, 700)]]
    assert pdf_lib._camelot_table_bbox(_FakeCamelotTable(cells=cells), page_height=None) is None
    # Garbage object never raises — falls back to None.
    assert pdf_lib._camelot_table_bbox(object(), page_height=800) is None


# --- markdown escaping ------------------------------------------------------

def test_markdown_escapes_inline_specials():
    para = {"type": "paragraph", "text": "use snake_case, *stars*, a|b, and [1]"}
    md = pdf_lib.element_to_markdown(para)
    assert md == r"use snake\_case, \*stars\*, a\|b, and \[1\]"


def test_markdown_escapes_line_leading_block_markers():
    f = lambda s: pdf_lib.element_to_markdown({"type": "paragraph", "text": s})
    assert f("# not a heading") == r"\# not a heading"
    assert f("> not a quote") == r"\> not a quote"
    assert f("- not a bullet") == r"\- not a bullet"
    assert f("1. not a list") == r"1\. not a list"
    assert f("---") == r"\---"        # thematic break / setext: escape first char only
    assert f("=====") == r"\====="    # longer rule preserved, not truncated


def test_markdown_plain_korean_text_unchanged():
    # No markdown specials in ordinary Korean prose -> escaping is a no-op.
    txt = "본 보고서는 2025 회계연도의 경영 실적을 요약한다."
    assert pdf_lib.element_to_markdown({"type": "paragraph", "text": txt}) == txt


def test_table_cells_inline_escaped_not_block():
    rows = [["항목", "비고"], ["-3", "a_b|c"]]
    md = pdf_lib._rows_to_markdown(rows)
    # A cell starting with "-" is data, not a bullet (no block escaping); inline
    # specials (_ and |) are still neutralized so they can't break the GFM grid.
    assert "| -3 | a\\_b\\|c |" in md


# --- scanned/vision page rendering ------------------------------------------

def test_build_document_renders_vision_pages(tmp_path):
    rdir = str(tmp_path / "render")
    doc = pdf_lib.build_document(PDF, str(tmp_path / "_assets"),
                                 render_vision=True, render_dir=rdir, dpi=100)
    vis = [p for p in doc["pages"] if p["needs_vision"]]
    assert {p["page"] for p in vis} == {4, 5}
    for p in vis:
        assert p.get("render") and os.path.exists(p["render"]) and os.path.getsize(p["render"]) > 1000
    # Non-vision pages are not rendered.
    assert all("render" not in p for p in doc["pages"] if not p["needs_vision"])
    md = pdf_lib.to_markdown(doc, rel_assets="assets", rel_render="render")
    assert "render/page_004.png" in md and "render/page_005.png" in md
    assert "(rendered for vision)" in md
    assert "needs vision transcription" in md
    # The scanned page's full-page raster is dropped from the .md (the render
    # already pictures the whole page); page 4's chart is a partial figure, kept.
    assert "assets/p5_img0.png" not in md
    assert "assets/p4_img0.png" in md


def test_parse_page_threads_mediabox_height_to_table_extractor(tmp_path, monkeypatch):
    # Regression: camelot's cell coords are in mediabox space, so the table
    # extractor must receive the MEDIABOX height (842), not the cropbox-based
    # PageInfo.height (742). A page whose cropbox is inset would otherwise shift
    # every camelot bbox and reintroduce the duplicate-numbers bug.
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)          # mediabox height 842
    page.insert_text((100, 100), "hi")
    page.set_cropbox(fitz.Rect(0, 50, 595, 792))        # cropbox height 742
    pdf_path = str(tmp_path / "crop.pdf")
    doc.save(pdf_path)
    doc.close()

    captured = {}
    monkeypatch.setattr(
        pdf_lib, "extract_tables",
        lambda p, n, password=None, page_height=None: captured.update(page_height=page_height) or [])
    d = fitz.open(pdf_path)
    info = pdf_lib.PageInfo(page=1, route=pdf_lib.ROUTE_TABLE, width=595.0, height=742.0,
                            char_count=2, block_count=1, image_count=0, image_area_ratio=0.0,
                            table_line_score=0, columns=1, needs_vision=False, reason="test")
    pdf_lib.parse_page(pdf_path, d, info, str(tmp_path / "_a"))
    d.close()
    assert captured["page_height"] == 842.0   # mediabox, not the cropbox 742.0


def test_table_dedup_spares_text_beside_table():
    # A left-column table must not suppress a right-column paragraph that merely
    # sits at the same height (the old y-band-only check dropped it -> lost text).
    table_box = [100.0, 200.0, 300.0, 400.0]   # left column
    E = pdf_lib.Element
    in_cell = E(type="paragraph", page=1, bbox=[110.0, 210.0, 290.0, 230.0], text="cell value")
    beside = E(type="paragraph", page=1, bbox=[360.0, 205.0, 540.0, 235.0], text="right column")  # same y, x outside
    above = E(type="heading", page=1, bbox=[110.0, 150.0, 300.0, 180.0], text="section title")     # y above
    kept = pdf_lib._drop_text_inside_tables([in_cell, beside, above], [table_box])
    texts = [e.text for e in kept]
    assert "cell value" not in texts      # in-cell duplicate suppressed
    assert "right column" in texts        # neighbouring text spared (the fix)
    assert "section title" in texts       # title above the table spared
    assert pdf_lib._drop_text_inside_tables([in_cell], []) == [in_cell]  # no tables -> no-op


def test_source_filename_cannot_break_html_comment():
    # A crafted PDF filename must not be able to close the provenance comment
    # early and inject markup into the .md (the source string skips _escape_md).
    doc = {"source": "a--><script>bad</script>.pdf", "page_count": 0, "pages": []}
    first = pdf_lib.to_markdown(doc).splitlines()[0]
    assert first.startswith("<!-- parsed from ") and first.endswith("-->")
    assert "<script>" not in first
    assert "-->" not in first[:-3]   # no early closer before the real one
    assert "bad" in first            # name still recorded (sans angle brackets)


def test_doc_link_uses_forward_slashes():
    # In-document links must be posix (portable .md) regardless of host OS.
    assert pdf_lib._doc_link("assets", os.path.join("x", "y", "p1_img0.png")) == "assets/p1_img0.png"
    assert pdf_lib._doc_link("render", "/abs/path/page_003.png") == "render/page_003.png"
    assert pdf_lib._doc_link(None, "/abs/path/page_003.png") == "/abs/path/page_003.png"


def test_build_document_no_render_by_default(tmp_path):
    doc = pdf_lib.build_document(PDF, str(tmp_path / "_assets"))
    assert all("render" not in p for p in doc["pages"])
    md = pdf_lib.to_markdown(doc)
    assert "Render with pdf_parse.py --render" in md
