#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate ORIGINAL .hwp / .hwpx test fixtures from scratch (no third-party
documents). Minimal but structurally faithful: an OLE2 container with a
FileHeader, a tiny DocInfo, and BodyText/SectionN streams built from real HWP
paragraph records — enough to exercise every tool in hwp-toolkit.

Run:  python tests/hwp_toolkit/fixtures/make_fixtures.py
"""
import os
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_SCRIPTS = os.path.normpath(
    os.path.join(HERE, "..", "..", "..", "skills", "hwp-toolkit", "scripts"))
sys.path.insert(0, SKILL_SCRIPTS)
import hwp_lib  # noqa: E402

OUT = HERE


def para_records(text, with_break=True):
    if with_break:
        text = text + "\r"
    nchars = len(text)
    header = struct.pack("<I I H B B H H H I H",
                         nchars, 0, 0, 0, 0, 1, 0, 1, 0, 0)
    charshape = struct.pack("<II", 0, 0)
    lineseg = b"\x00" * 36
    return [
        hwp_lib.Record(66, 0, len(header), 4, 0, header),
        hwp_lib.Record(67, 1, len(text) * 2, 4, 0, text.encode("utf-16-le")),
        hwp_lib.Record(68, 1, len(charshape), 4, 0, charshape),
        hwp_lib.Record(69, 1, len(lineseg), 4, 0, lineseg),
    ]


def blank_para_records():
    header = struct.pack("<I I H B B H H H I H",
                         1, 0, 0, 0, 0, 1, 0, 1, 0, 0)
    charshape = struct.pack("<II", 0, 0)
    lineseg = b"\x00" * 36
    return [
        hwp_lib.Record(66, 0, len(header), 4, 0, header),
        hwp_lib.Record(68, 1, len(charshape), 4, 0, charshape),
        hwp_lib.Record(69, 1, len(lineseg), 4, 0, lineseg),
    ]


def section_blob(paragraphs):
    recs = []
    for p in paragraphs:
        recs += p if isinstance(p, list) else para_records(p)
    return hwp_lib.serialize_records(recs)


def file_header(compressed=True):
    fh = bytearray(256)
    fh[0:17] = b"HWP Document File"
    struct.pack_into("<I", fh, 32, 0x05000000)
    struct.pack_into("<I", fh, 36, 1 if compressed else 0)
    return bytes(fh)


def write_hwp(path, sections):
    streams = {"FileHeader": file_header(True), "DocInfo": hwp_lib.compress(b"")}
    for i, paras in enumerate(sections):
        streams[f"BodyText/Section{i}"] = hwp_lib.compress(section_blob(paras))
    hwp_lib.build_ole(streams, path)
    return path


def basic():
    return write_hwp(os.path.join(OUT, "sample_basic.hwp"), [[
        "샘플 강의계획서", " ㅇ 강좌명 : ",
        " ㅇ 강의목표 : OOOO (2~3줄)", " ㅇ 강의장소 : 서울 어딘가"]])


def multisection():
    return write_hwp(os.path.join(OUT, "sample_multisection.hwp"),
                     [["첫째 절 문구", " ㅇ 공통 : 본문"],
                      ["둘째 절 SECTION1_ONLY 고유문구", " ㅇ 공통 : 본문"]])


def inline_controls():
    leak = "\x04" + "SECRET!"   # inline control (8 units) carrying ASCII
    return write_hwp(os.path.join(OUT, "sample_inline_controls.hwp"),
                     [["앞부분" + leak + "뒷부분", " ㅇ 정상 : 라인"]])


def form():
    return write_hwp(os.path.join(OUT, "sample_form.hwp"),
                     [["담당자: [[NAME]]", "담당자: [[NAME]]",
                       "담당자: [[NAME]]", " ㅇ 비고 : "]])


def blank_cell_form():
    return write_hwp(os.path.join(OUT, "sample_blank_cell_form.hwp"),
                     [["성    명", blank_para_records(),
                       "생년월일", blank_para_records()]])


def _cell_para_records(text, base_level):
    """Paragraph records for one cell line, nested at base_level (PARA_HEADER)
    / base_level+1 (PARA_TEXT) so they sit one level below the cell header."""
    text = text + "\r"
    header = struct.pack("<I I H B B H H H I H",
                         len(text), 0, 0, 0, 0, 1, 0, 1, 0, 0)
    return [
        hwp_lib.Record(66, base_level, len(header), 4, 0, header),
        hwp_lib.Record(67, base_level + 1, len(text) * 2, 4, 0,
                       text.encode("utf-16-le")),
        hwp_lib.Record(68, base_level + 1, 8, 4, 0, struct.pack("<II", 0, 0)),
        hwp_lib.Record(69, base_level + 1, 36, 4, 0, b"\x00" * 36),
    ]


def _cell_records(col, row, colspan, rowspan, lines, level=2):
    """A table cell: LIST_HEADER (col/row/span) + its paragraph records.
    Layout matches hwp_lib._parse_cell_addr: npara u16 | flags u32 | col u16 |
    row u16 | colSpan u16 | rowSpan u16 | width u32 | height u32 | margins | bf."""
    lh = (struct.pack("<H", len(lines)) + struct.pack("<I", 0)
          + struct.pack("<HHHH", col, row, colspan, rowspan)
          + struct.pack("<II", 0, 0) + b"\x00" * 8 + struct.pack("<H", 0))
    recs = [hwp_lib.Record(72, level, len(lh), 4, 0, lh)]
    for line in lines:
        recs += _cell_para_records(line, level + 1)
    return recs


def _table_block():
    """A 2x3 table control built from real records: a host paragraph carrying
    the inline object control char, a CTRL_HEADER, the TABLE record, then one
    LIST_HEADER per cell. Row 1 merges two columns and one cell spans two
    paragraphs, so the parser must resolve spans and multi-line cells."""
    obj = "\x0b" + "\x00" * 7   # inline object control: 1 + 7 padding units
    host_hdr = struct.pack("<I I H B B H H H I H",
                           len(obj), 0, 0, 0, 0, 1, 0, 1, 0, 0)
    block = [
        hwp_lib.Record(66, 0, len(host_hdr), 4, 0, host_hdr),
        hwp_lib.Record(67, 1, len(obj) * 2, 4, 0, obj.encode("utf-16-le")),
        hwp_lib.Record(68, 1, 8, 4, 0, struct.pack("<II", 0, 0)),
        hwp_lib.Record(69, 1, 36, 4, 0, b"\x00" * 36),
        hwp_lib.Record(71, 1, 8, 4, 0, b" lbt" + b"\x00" * 4),   # CTRL_HEADER 'tbl '
    ]
    # TABLE: flags u32 | nRows u16 | nCols u16 | cellSpacing u16 | margins(8) |
    #        rowSizes(nRows u16) | borderFill u16
    tbl = (struct.pack("<I", 0) + struct.pack("<HH", 2, 3) + struct.pack("<H", 0)
           + b"\x00" * 8 + struct.pack("<HH", 3, 2) + struct.pack("<H", 0))
    block.append(hwp_lib.Record(77, 2, len(tbl), 4, 0, tbl))
    block += _cell_records(0, 0, 1, 1, ["항목"])
    block += _cell_records(1, 0, 1, 1, ["예산"])
    block += _cell_records(2, 0, 1, 1, ["비고", "(원)"])     # multi-paragraph cell
    block += _cell_records(0, 1, 1, 1, ["합계"])
    block += _cell_records(1, 1, 2, 1, ["1,000"])             # colSpan = 2
    return block


def table():
    return write_hwp(os.path.join(OUT, "sample_table.hwp"),
                     [["표 제목", _table_block(), "표 끝"]])


def table_hwpx():
    out = os.path.join(OUT, "sample_table.hwpx")
    NS = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'

    def tc(col, row, cspan, rspan, *lines):
        paras = "".join(
            f"<hp:p><hp:run><hp:t>{ln}</hp:t></hp:run></hp:p>" for ln in lines)
        return (f'<hp:tc><hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
                f'<hp:cellSpan colSpan="{cspan}" rowSpan="{rspan}"/>'
                f'<hp:subList>{paras}</hp:subList></hp:tc>')

    table_xml = (
        '<hp:tbl rowCnt="2" colCnt="3">'
        '<hp:tr>' + tc(0, 0, 1, 1, "항목") + tc(1, 0, 1, 1, "예산")
        + tc(2, 0, 1, 1, "비고", "(원)") + '</hp:tr>'
        '<hp:tr>' + tc(0, 1, 1, 1, "합계") + tc(1, 1, 2, 1, "1,000")
        + '</hp:tr></hp:tbl>')
    # second table: one cell whose text carries an inline line break + tab, which
    # must map to '\n'/'\t' (not be swallowed) just like non-table run text.
    inline_xml = (
        '<hp:tbl rowCnt="1" colCnt="1"><hp:tr>'
        '<hp:tc><hp:cellAddr colAddr="0" rowAddr="0"/>'
        '<hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run>'
        '<hp:t>윗줄<hp:lineBreak/>아랫줄<hp:tab/>탭뒤</hp:t>'
        '</hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl>')
    section = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               f'<hp:sec {NS}>'
               '<hp:p><hp:run><hp:t>표 앞 문단</hp:t></hp:run>'
               f'<hp:run>{table_xml}</hp:run></hp:p>'
               f'<hp:p><hp:run>{inline_xml}</hp:run></hp:p></hp:sec>')
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo("mimetype"); zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, "application/hwp+zip")
        z.writestr("Contents/section0.xml", section)
    return out


def hwpx():
    out = os.path.join(OUT, "sample.hwpx")
    NS = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
    section = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               f'<hp:sec {NS}>'
               '<hp:p><hp:run><hp:t>HWPX_TEST_콘텐츠 첫 문단입니다.</hp:t></hp:run></hp:p>'
               '<hp:p><hp:run><hp:t>두 번째 문단.</hp:t></hp:run></hp:p>'
               # run with an inline line break + tab + highlight markup
               '<hp:p><hp:run><hp:t>기부식품제공업,<hp:lineBreak/>건강기능식품판매업'
               '</hp:t></hp:run></hp:p>'
               '<hp:p><hp:run><hp:t>처리기관<hp:tab/>(관할 시군구)</hp:t></hp:run></hp:p>'
               '<hp:p><hp:run><hp:t>강조<hp:markpenBegin/>구간<hp:markpenEnd/>끝'
               '</hp:t></hp:run></hp:p></hp:sec>')
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo("mimetype"); zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, "application/hwp+zip")
        z.writestr("Contents/section0.xml", section)
        z.writestr("Contents/header.xml",
                   '<?xml version="1.0" encoding="UTF-8"?><hh:head '
                   'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"/>')
        z.writestr("META-INF/manifest.xml",
                   '<?xml version="1.0" encoding="UTF-8"?><odf:manifest '
                   'xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>')
    return out


def build_all():
    return [basic(), multisection(), inline_controls(), form(),
            blank_cell_form(), table(), table_hwpx(), hwpx()]


if __name__ == "__main__":
    for f in build_all():
        print("built", os.path.relpath(f, os.path.join(HERE, "..", "..", "..")),
              os.path.getsize(f), "bytes")
