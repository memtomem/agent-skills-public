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
            blank_cell_form(), hwpx()]


if __name__ == "__main__":
    for f in build_all():
        print("built", os.path.relpath(f, os.path.join(HERE, "..", "..", "..")),
              os.path.getsize(f), "bytes")
