#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the hwp-toolkit skill. Fixtures are generated from scratch
(no third-party documents) by fixtures/make_fixtures.py."""
import csv
import io
import os
import sys
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "skills", "hwp-toolkit", "scripts"))
sys.path.insert(0, os.path.join(HERE, "fixtures"))

import hwp_lib            # noqa: E402
import make_fixtures      # noqa: E402
import olefile            # noqa: E402

FX = os.path.join(HERE, "fixtures")


@pytest.fixture(scope="session", autouse=True)
def _build_fixtures():
    make_fixtures.build_all()


def p(name):
    return os.path.join(FX, name)


def test_extract_basic():
    txt = hwp_lib.extract_text(p("sample_basic.hwp"))
    assert "샘플 강의계획서" in txt and "강의장소" in txt


def test_extract_multisection_labels_both():
    txt = hwp_lib.extract_text(p("sample_multisection.hwp"))
    assert "=== BodyText/Section0 ===" in txt
    assert "=== BodyText/Section1 ===" in txt
    assert "SECTION1_ONLY" in txt


def test_inline_controls_not_leaked():
    txt = hwp_lib.extract_text(p("sample_inline_controls.hwp"))
    assert "앞부분" in txt and "뒷부분" in txt
    assert "SECRET" not in txt


def test_extract_hwpx():
    txt = hwp_lib.extract_text(p("sample.hwpx"))
    assert "HWPX_TEST_콘텐츠" in txt and "두 번째 문단" in txt


def test_inspect_hwp():
    info = hwp_lib.inspect(p("sample_basic.hwp"))
    assert info["compressed"] is True and info["encrypted"] is False
    assert "BodyText/Section0" in info["streams"]
    assert any("강좌명" in x["text"] for x in info["sections"][0]["paragraphs"])


def test_inspect_hwpx():
    info = hwp_lib.inspect(p("sample.hwpx"))
    assert info.get("format") == "hwpx"
    assert any(n.startswith("Contents/section") for n in info["streams"])


def test_replace_preserves_untouched_streams(tmp_path):
    out = str(tmp_path / "out.hwp")
    n = hwp_lib.replace_text(p("sample_basic.hwp"), out,
                             [(" ㅇ 강좌명 : ", " ㅇ 강좌명 : 새 강좌")])
    assert n == 1 and olefile.isOleFile(out)
    src = hwp_lib.read_streams(p("sample_basic.hwp"))
    dst = hwp_lib.read_streams(out)
    for k in src:
        if not k.startswith("BodyText/Section"):
            assert src[k] == dst[k], k
    assert "새 강좌" in hwp_lib.extract_text(out)


def test_replace_zero_when_no_match(tmp_path):
    out = str(tmp_path / "out.hwp")
    assert hwp_lib.replace_text(p("sample_basic.hwp"), out, [("없는문구", "X")]) == 0


def test_set_only_target_paragraph(tmp_path):
    out = str(tmp_path / "out.hwp")
    info = hwp_lib.inspect(p("sample_form.hwp"))
    idxs = [x["rec_index"] for x in info["sections"][0]["paragraphs"]
            if x["text"].startswith("담당자")]
    assert len(idxs) == 3
    hwp_lib.set_paragraph_text(p("sample_form.hwp"), out,
                               {"BodyText/Section0": {idxs[1]: "담당자: 홍길동"}})
    txt = hwp_lib.extract_text(out)
    assert txt.count("홍길동") == 1 and txt.count("[[NAME]]") == 2


def test_inspect_reports_blank_paragraph_candidates():
    info = hwp_lib.inspect(p("sample_blank_cell_form.hwp"))
    section = info["sections"][0]
    assert [x["text"] for x in section["paragraphs"]] == ["성    명¶", "생년월일¶"]
    blanks = section["blank_paragraphs"]
    assert len(blanks) == 2
    assert all(x["suggested_text_level"] == 1 for x in blanks)


def test_fill_blank_paragraph_inserts_text_without_overwriting_label(tmp_path):
    out = str(tmp_path / "out.hwp")
    info = hwp_lib.inspect(p("sample_blank_cell_form.hwp"))
    blanks = info["sections"][0]["blank_paragraphs"]
    hwp_lib.fill_blank_paragraph_text(
        p("sample_blank_cell_form.hwp"), out,
        {"BodyText/Section0": {
            blanks[0]["header_index"]: "김민수",
            blanks[1]["header_index"]: "1990년 1월 1일",
        }},
    )
    txt = hwp_lib.extract_text(out)
    assert "성    명\n김민수\n생년월일\n1990년 1월 1일" in txt
    assert "성    명 김민수" not in txt
    assert olefile.isOleFile(out)


def test_fill_blank_paragraph_rejects_existing_text(tmp_path):
    out = str(tmp_path / "out.hwp")
    info = hwp_lib.inspect(p("sample_blank_cell_form.hwp"))
    label_header = info["sections"][0]["paragraphs"][0]["header_index"]
    with pytest.raises(ValueError, match="already has PARA_TEXT"):
        hwp_lib.fill_blank_paragraph_text(
            p("sample_blank_cell_form.hwp"), out,
            {"BodyText/Section0": {label_header: "김민수"}},
        )


def test_build_ole_roundtrip(tmp_path):
    out = str(tmp_path / "rebuilt.hwp")
    streams = hwp_lib.read_streams(p("sample_multisection.hwp"))
    hwp_lib.build_ole(streams, out)
    assert olefile.isOleFile(out) and hwp_lib.read_streams(out) == streams


def _zip_members(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_replace_hwpx_changes_text_and_count(tmp_path):
    out = str(tmp_path / "out.hwpx")
    n = hwp_lib.replace_text(p("sample.hwpx"), out,
                             [("두 번째 문단", "수정된 둘째 문단")])
    assert n == 1 and zipfile.is_zipfile(out)
    txt = hwp_lib.extract_text(out)
    assert "수정된 둘째 문단" in txt and "두 번째 문단" not in txt


def test_replace_hwpx_preserves_other_members(tmp_path):
    out = str(tmp_path / "out.hwpx")
    hwp_lib.replace_text(p("sample.hwpx"), out, [("첫 문단", "첫째 문단")])
    src, dst = _zip_members(p("sample.hwpx")), _zip_members(out)
    assert set(src) == set(dst)
    for name in src:
        if not name.startswith("Contents/section"):
            assert src[name] == dst[name], name
    # mimetype must stay first and STORED so the container is still valid
    with zipfile.ZipFile(out) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED


def test_replace_hwpx_zero_when_no_match(tmp_path):
    out = str(tmp_path / "out.hwpx")
    assert hwp_lib.replace_text(p("sample.hwpx"), out, [("없는문구", "X")]) == 0


def test_set_on_hwpx_raises(tmp_path):
    out = str(tmp_path / "out.hwpx")
    with pytest.raises(NotImplementedError):
        hwp_lib.set_paragraph_text(p("sample.hwpx"), out,
                                   {"BodyText/Section0": {1: "x"}})


def test_hwpx_linebreak_and_tab_become_whitespace():
    txt = hwp_lib.extract_text(p("sample.hwpx"))
    assert "<hp:lineBreak/>" not in txt and "<hp:tab" not in txt
    assert "기부식품제공업,\n건강기능식품판매업" in txt   # lineBreak -> newline
    assert "처리기관\t(관할 시군구)" in txt              # tab -> \t


def test_hwpx_strips_other_inline_markup():
    txt = hwp_lib.extract_text(p("sample.hwpx"))
    assert "markpen" not in txt and "강조구간끝" in txt


def test_replace_hwpx_preserves_inline_tags(tmp_path):
    out = str(tmp_path / "out.hwpx")
    # edit a run that contains an inline <hp:lineBreak/>; the tag must survive
    n = hwp_lib.replace_text(p("sample.hwpx"), out,
                             [("기부식품제공업", "기부식품업")])
    assert n == 1
    with zipfile.ZipFile(out) as z:
        sec = z.read("Contents/section0.xml").decode("utf-8")
    assert "<hp:lineBreak/>" in sec               # inline element intact
    assert "&lt;hp:lineBreak/&gt;" not in sec     # not double-escaped/corrupted
    assert "기부식품업,\n건강기능식품판매업" in hwp_lib.extract_text(out)


# ---- table extraction -----------------------------------------------------
def test_extract_table_hwp_grid():
    tables = hwp_lib.extract_tables(p("sample_table.hwp"))
    assert len(tables) == 1
    t = tables[0]
    assert (t["nrows"], t["ncols"]) == (2, 3)
    grid = hwp_lib.table_grid(t)                       # default expand="blank"
    assert grid[0] == ["항목", "예산", "비고\n(원)"]    # multi-paragraph cell joins
    assert grid[1][0] == "합계"
    assert grid[1][1] == "1,000"
    assert grid[1][2] == ""                            # merged-over cell stays blank


def test_extract_table_span_metadata():
    t = hwp_lib.extract_tables(p("sample_table.hwp"))[0]
    assert t["spans"] == [{"row": 1, "col": 1, "rowspan": 1, "colspan": 2}]


def test_extract_table_expand_duplicate():
    t = hwp_lib.extract_tables(p("sample_table.hwp"))[0]
    grid = hwp_lib.table_grid(t, expand="duplicate")
    assert grid[1][2] == "1,000"                       # covered cell repeats value


def test_table_renders_gfm_with_span_note():
    t = hwp_lib.extract_tables(p("sample_table.hwp"))[0]
    md = hwp_lib.table_to_markdown(t)
    assert "| 항목 | 예산 | 비고<br>(원) |" in md       # newline -> <br>, header row
    assert "| --- | --- | --- |" in md
    assert "병합 셀" in md and "(r1,c1)→1×2" in md


def test_table_csv_duplicates_merged_cell():
    t = hwp_lib.extract_tables(p("sample_table.hwp"))[0]
    # parse back with csv so the multi-line cell's embedded newline is handled
    rows = list(csv.reader(io.StringIO(hwp_lib.table_to_csv(t))))
    assert rows[0] == ["항목", "예산", "비고\n(원)"]
    assert rows[1] == ["합계", "1,000", "1,000"]        # csv default duplicates merge


def test_extract_table_hwpx_grid_matches_binary():
    t = hwp_lib.extract_tables(p("sample_table.hwpx"))[0]
    assert (t["nrows"], t["ncols"]) == (2, 3)
    grid = hwp_lib.table_grid(t)
    assert grid[0] == ["항목", "예산", "비고\n(원)"]
    assert grid[1][:2] == ["합계", "1,000"] and grid[1][2] == ""
    assert t["spans"] == [{"row": 1, "col": 1, "rowspan": 1, "colspan": 2}]


def test_hwpx_table_cell_preserves_inline_linebreak_and_tab():
    # the fixture's 2nd table is one cell whose text has an inline line break
    # and tab; they must map to \n / \t, not be swallowed (matches non-table runs)
    tables = hwp_lib.extract_tables(p("sample_table.hwpx"))
    assert len(tables) == 2
    assert hwp_lib.table_grid(tables[1])[0][0] == "윗줄\n아랫줄\t탭뒤"


def test_extract_tables_json_shape():
    tables = hwp_lib.extract_tables(p("sample_table.hwp"))
    doc = hwp_lib.tables_to_json(tables)
    assert list(doc) == ["tables"] and len(doc["tables"]) == 1
    one = doc["tables"][0]
    assert one["section"] == "BodyText/Section0" and one["index"] == 0
    assert one["nrows"] == 2 and one["ncols"] == 3
    assert one["grid"][0][0] == "항목"


def test_extract_text_still_marks_table():
    txt = hwp_lib.extract_text(p("sample_table.hwp"))
    assert "[표]" in txt and "표 제목" in txt and "표 끝" in txt
