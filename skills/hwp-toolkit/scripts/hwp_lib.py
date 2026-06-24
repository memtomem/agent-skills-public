#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hwp_lib — read / analyze / edit Hangul Word Processor 5.x (.hwp) files.

An .hwp 5.x file is an OLE2 compound document. Body text lives in
`BodyText/SectionN` streams as a flat sequence of binary "records"; the
streams are usually zlib raw-deflate compressed (FileHeader flag bit 0).
Each record = 32-bit header (tag:10 | level:10 | size:12; size 0xFFF means a
following uint32 holds the real size) + payload. Paragraph text is in
HWPTAG_PARA_TEXT (67) as UTF-16-LE, and the character count is mirrored in
the owning HWPTAG_PARA_HEADER (66, first uint32).

This module provides:
  - read_streams(path)            -> dict[name -> bytes]
  - is_compressed(streams)        -> bool
  - sections(streams)             -> ordered list of BodyText/SectionN names
  - parse_records(blob)           -> list[Record]
  - extract_text(path, ...)       -> str (paragraphs + table cell markers)
  - inspect(path)                 -> dict (streams, metadata, per-paragraph text)
  - build_ole(streams, out_path)  -> rebuilds a valid compound file
  - replace_text(path, out, rules)-> find/replace inside paragraph text & save

Only stdlib + `olefile` are required for everything except convenience
conversion helpers. Editing keeps every untouched stream byte-identical and
only rewrites the section(s) you change, so formatting/tables are preserved.
"""
import html
import math
import re
import struct
import zipfile
import zlib

try:
    import olefile
except ImportError as e:  # pragma: no cover
    raise SystemExit("Install dependency first:  pip install olefile") from e

# ---- record tag ids (HWP 5.0 spec) ----------------------------------------
T_DOC_PARA_HEADER = 66
T_PARA_TEXT = 67
T_PARA_CHAR_SHAPE = 68
T_PARA_LINE_SEG = 69
TAG_NAMES = {
    66: "PARA_HEADER", 67: "PARA_TEXT", 68: "PARA_CHAR_SHAPE",
    69: "PARA_LINE_SEG", 71: "CTRL_HEADER", 72: "LIST_HEADER",
    73: "PAGE_DEF", 74: "FOOTNOTE_SHAPE", 75: "PAGE_BORDER_FILL",
    76: "SHAPE_COMPONENT", 77: "TABLE",
}


# ===========================================================================
# Reading
# ===========================================================================
def read_streams(path):
    """Return {stream_name: bytes} for every stream in the compound file.
    Names use '/' separators and preserve control prefixes (e.g.
    '\\x05HwpSummaryInformation')."""
    ole = olefile.OleFileIO(path)
    out = {}
    for entry in ole.listdir(streams=True, storages=False):
        name = "/".join(entry)
        out[name] = ole.openstream(name).read()
    ole.close()
    return out


def is_compressed(streams):
    fh = streams.get("FileHeader", b"")
    if len(fh) < 40:
        return True
    flags = int.from_bytes(fh[36:40], "little")
    return bool(flags & 0x01)


def is_encrypted(streams):
    fh = streams.get("FileHeader", b"")
    if len(fh) < 40:
        return False
    return bool(int.from_bytes(fh[36:40], "little") & 0x02)


def section_names(streams):
    secs = [n for n in streams if re.fullmatch(r"BodyText/Section\d+", n)]
    return sorted(secs, key=lambda n: int(n.rsplit("Section", 1)[1]))


def decompress(blob, compressed=True):
    return zlib.decompress(blob, -15) if compressed else blob


def compress(blob, compressed=True):
    if not compressed:
        return blob
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return co.compress(blob) + co.flush()


# ===========================================================================
# Record parsing
# ===========================================================================
class Record:
    __slots__ = ("tag", "level", "size", "hlen", "start", "payload")

    def __init__(self, tag, level, size, hlen, start, payload):
        self.tag, self.level, self.size = tag, level, size
        self.hlen, self.start, self.payload = hlen, start, payload

    @property
    def name(self):
        return TAG_NAMES.get(self.tag, str(self.tag))

    def text(self):
        if self.tag == T_PARA_TEXT:
            return self.payload.decode("utf-16-le", "replace")
        return None


def parse_records(blob):
    recs, i = [], 0
    n = len(blob)
    while i + 4 <= n:
        h = int.from_bytes(blob[i:i + 4], "little")
        tag = h & 0x3FF
        level = (h >> 10) & 0x3FF
        size = (h >> 20) & 0xFFF
        hlen = 4
        if size == 0xFFF:
            size = int.from_bytes(blob[i + 4:i + 8], "little")
            hlen = 8
        payload = blob[i + hlen:i + hlen + size]
        recs.append(Record(tag, level, size, hlen, i, payload))
        i += hlen + size
    return recs


def serialize_records(recs):
    out = bytearray()
    for r in recs:
        size = len(r.payload)
        if size < 0xFFF:
            h = (r.tag & 0x3FF) | ((r.level & 0x3FF) << 10) | ((size & 0xFFF) << 20)
            out += struct.pack("<I", h)
        else:
            h = (r.tag & 0x3FF) | ((r.level & 0x3FF) << 10) | (0xFFF << 20)
            out += struct.pack("<II", h, size)
        out += r.payload
    return bytes(out)


# Inline control characters in PARA_TEXT. Per the HWP 5.0 spec a control char
# is one of three kinds determined by its code; inline/extended controls each
# occupy 8 UTF-16 code units (the control + 7 units of payload), while "char"
# controls occupy a single unit. We must skip whole controls when reading text,
# otherwise the 7-unit payload (often ASCII tags like 'secd','tbl') leaks out
# as garbage.
_CHAR_CTRL = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}
_WIDE_CTRL = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20,
              21, 22, 23}  # inline + extended, 8 units each


def walk_text(text):
    """Yield ('text', str) for printable runs and ('ctrl', code) for control
    characters, correctly consuming multi-unit inline/extended controls."""
    buf = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        o = ord(c)
        if o >= 0x20:
            buf.append(c)
            i += 1
            continue
        if buf:
            yield ("text", "".join(buf))
            buf = []
        yield ("ctrl", o)
        i += 8 if o in _WIDE_CTRL else 1
    if buf:
        yield ("text", "".join(buf))


def clean_text(text):
    """Printable text of a paragraph with all inline controls removed."""
    return "".join(s for kind, s in walk_text(text) if kind == "text")


def _visible(text):
    """Readable single-line form for inspection (controls collapsed to ¶)."""
    out = []
    for kind, val in walk_text(text):
        if kind == "text":
            out.append(val)
        elif val in (10, 13):
            out.append("¶")
    return "".join(out)


# ===========================================================================
# Text extraction
# ===========================================================================
def is_hwpx(path):
    """True if `path` is an .hwpx (OWPML zip), not a binary .hwp. The two share
    a brand but are completely different containers, so callers must branch."""
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "mimetype" in names:
                if z.read("mimetype").strip() == b"application/hwp+zip":
                    return True
            # fall back to structural signature
            return any(n.startswith("Contents/section") for n in names)
    except Exception:
        return False


def _hwpx_run_to_text(inner):
    """Readable text of one <hp:t> run's mixed content. A run holds text plus
    inline elements: <hp:lineBreak/> and <hp:tab/> carry whitespace, while
    others (markpen, field markers, …) carry none. Convert the first two, drop
    the rest, then unescape entities — otherwise raw XML tags leak into output."""
    inner = re.sub(r"<hp:lineBreak\s*/?>", "\n", inner)
    inner = re.sub(r"<hp:tab\b[^>]*?>", "\t", inner)
    inner = re.sub(r"<[^>]+>", "", inner)            # strip remaining inline markup
    return html.unescape(inner)


def extract_text_hwpx(path):
    """Extract body text from an .hwpx. Text lives in <hp:t> runs inside <hp:p>
    paragraphs across Contents/section*.xml. One paragraph -> one line (a
    <hp:lineBreak/> inside a run adds a newline within that line)."""
    lines = []
    with zipfile.ZipFile(path) as z:
        secs = sorted(n for n in z.namelist()
                      if re.fullmatch(r"Contents/section\d+\.xml", n))
        multi = len(secs) > 1
        for n in secs:
            if multi:
                lines.append(f"=== {n} ===")
            xml = z.read(n).decode("utf-8", "replace")
            for para in re.findall(r"<hp:p\b.*?</hp:p>", xml, re.S):
                runs = re.findall(r"<hp:t\b[^>]*>(.*?)</hp:t>", para, re.S)
                lines.append("".join(_hwpx_run_to_text(r) for r in runs))
    return "\n".join(lines)


def extract_text(path, table_markers=True):
    """Return readable text of a .hwp or .hwpx file. Inline control characters
    are dropped; each paragraph becomes one line. For binary .hwp, table
    boundaries are marked [표]; when a document has multiple sections, each is
    introduced with a `=== section ===` header so the boundary is legible."""
    if is_hwpx(path):
        return extract_text_hwpx(path)
    streams = read_streams(path)
    if is_encrypted(streams):
        raise ValueError("File is password-protected/encrypted; cannot read.")
    comp = is_compressed(streams)
    secs = section_names(streams)
    multi = len(secs) > 1
    lines = []
    for sec in secs:
        if multi:
            lines.append(f"=== {sec} ===")
        recs = parse_records(decompress(streams[sec], comp))
        for r in recs:
            if table_markers and r.tag == 77:  # TABLE control
                lines.append("[표]")
            if r.tag == T_PARA_TEXT:
                lines.append(clean_text(r.text()))
    return "\n".join(lines)


# ===========================================================================
# Inspection / structure dump
# ===========================================================================
def _summary_info(streams):
    """Best-effort parse of \\x05HwpSummaryInformation (OLE property set)."""
    raw = streams.get("\x05HwpSummaryInformation")
    if not raw:
        return {}
    info = {}
    try:
        import olefile  # property parser
        # Minimal: rely on olefile's getproperties via a temp wrapper is hard
        # here; instead just report presence + size.
        info["present"] = True
        info["bytes"] = len(raw)
    except Exception:
        pass
    return info


def inspect(path, max_paragraphs=10000):
    if is_hwpx(path):
        with zipfile.ZipFile(path) as z:
            members = {n: z.getinfo(n).file_size for n in z.namelist()}
        return {"path": path, "format": "hwpx", "compressed": True,
                "encrypted": False, "streams": members, "sections": [],
                "note": "HWPX (OWPML zip). Text in Contents/section*.xml; "
                        "use extract_text()."}
    streams = read_streams(path)
    comp = is_compressed(streams)
    enc = is_encrypted(streams)
    result = {
        "path": path,
        "compressed": comp,
        "encrypted": enc,
        "streams": {n: len(b) for n, b in sorted(streams.items())},
        "sections": [],
    }
    if enc:
        return result
    for sec in section_names(streams):
        recs = parse_records(decompress(streams[sec], comp))
        tag_counts = {}
        paras = []
        blanks = []
        last_hdr = None
        header_has_text = {}
        for idx, r in enumerate(recs):
            tag_counts[r.name] = tag_counts.get(r.name, 0) + 1
            if r.tag == T_DOC_PARA_HEADER:
                last_hdr = idx
                header_has_text[idx] = False
            if r.tag == T_PARA_TEXT and len(paras) < max_paragraphs:
                if last_hdr is not None:
                    header_has_text[last_hdr] = True
                paras.append({
                    "rec_index": idx,
                    "header_index": last_hdr,
                    "level": r.level,
                    "text": _visible(r.text()),
                })
        for idx, r in enumerate(recs):
            if r.tag == T_DOC_PARA_HEADER and not header_has_text.get(idx, False):
                blanks.append({
                    "header_index": idx,
                    "level": r.level,
                    "suggested_text_level": _paragraph_text_level(recs, idx),
                })
        result["sections"].append({
            "name": sec,
            "record_count": len(recs),
            "tag_counts": tag_counts,
            "paragraphs": paras,
            "blank_paragraphs": blanks,
        })
    return result


def _paragraph_text_level(recs, header_index):
    """Best-effort text level for a paragraph that currently has no text."""
    for r in recs[header_index + 1:]:
        if r.tag == T_DOC_PARA_HEADER:
            break
        if r.tag in (T_PARA_CHAR_SHAPE, T_PARA_LINE_SEG, T_PARA_TEXT):
            return r.level
    return recs[header_index].level + 1


def _set_header_char_count(header_record, char_count):
    pa = bytearray(header_record.payload)
    high = int.from_bytes(pa[0:4], "little") & 0x80000000
    pa[0:4] = struct.pack("<I", (char_count & 0x7FFFFFFF) | high)
    header_record.payload = bytes(pa)


# ===========================================================================
# Editing — find/replace inside paragraph text
# ===========================================================================
def _edit_section_blob(blob, rules, count_holder):
    """Apply (old, new) substring replacements to PARA_TEXT records.
    rules: list of dicts {old, new, max (optional), regex (bool)}.
    Updates the owning PARA_HEADER's char count. Returns new blob."""
    recs = parse_records(blob)
    # map text record -> its header record
    hdr_of = {}
    last = None
    for idx, r in enumerate(recs):
        if r.tag == T_DOC_PARA_HEADER:
            last = idx
        if r.tag == T_PARA_TEXT:
            hdr_of[idx] = last

    for idx, r in enumerate(recs):
        if r.tag != T_PARA_TEXT:
            continue
        text = r.text()
        # separate control chars so replacements only touch visible text per
        # line segment; we operate on the whole string but only replace the
        # given visible substrings (callers pass visible substrings).
        new_text = text
        for rule in rules:
            if rule.get("done_count", 0) >= rule.get("max", 10 ** 9):
                continue
            old, new = rule["old"], rule["new"]
            if rule.get("regex"):
                new_text2, n = re.subn(old, new, new_text)
            else:
                if old not in new_text:
                    continue
                remaining = rule.get("max", 10 ** 9) - rule.get("done_count", 0)
                new_text2 = new_text.replace(old, new, remaining)
                n = new_text.count(old)
                n = min(n, remaining)
            if n:
                rule["done_count"] = rule.get("done_count", 0) + n
                count_holder[0] += n
                new_text = new_text2
        if new_text != text:
            r.payload = new_text.encode("utf-16-le")
            # update char count in header (preserve high bit / control mask)
            h = recs[hdr_of[idx]]
            pa = bytearray(h.payload)
            old_n = int.from_bytes(pa[0:4], "little")
            high = old_n & 0x80000000
            pa[0:4] = struct.pack("<I", (len(new_text) & 0x7FFFFFFF) | high)
            h.payload = bytes(pa)
    return serialize_records(recs)


def set_paragraph_text(path, out_path, edits):
    """Low-level: set whole text of specific paragraphs by record index.
    edits: {section_name: {rec_index: new_full_text_str_or_list_of_lines}}.
    For multi-line cells pass a list; original control chars are reused/padded.
    """
    if is_hwpx(path):
        raise NotImplementedError(
            "set-by-index targets binary .hwp record streams; .hwpx has no "
            "such indices. Use replace_text() (find/replace) on .hwpx instead.")
    streams = read_streams(path)
    comp = is_compressed(streams)
    for sec, by_idx in edits.items():
        recs = parse_records(decompress(streams[sec], comp))
        hdr_of, last = {}, None
        for idx, r in enumerate(recs):
            if r.tag == T_DOC_PARA_HEADER:
                last = idx
            if r.tag == T_PARA_TEXT:
                hdr_of[idx] = last
        for idx, value in by_idx.items():
            r = recs[idx]
            controls = [c for c in r.text() if ord(c) < 0x20] or ["\r"]
            lines = [value] if isinstance(value, str) else list(value)
            while len(controls) < len(lines):
                controls.append(controls[-1])
            pieces = [lines[k] + controls[k] for k in range(len(lines))]
            pieces += [controls[k] for k in range(len(lines), len(controls))]
            new_text = "".join(pieces)
            r.payload = new_text.encode("utf-16-le")
            h = recs[hdr_of[idx]]
            pa = bytearray(h.payload)
            high = int.from_bytes(pa[0:4], "little") & 0x80000000
            pa[0:4] = struct.pack("<I", (len(new_text) & 0x7FFFFFFF) | high)
            h.payload = bytes(pa)
        streams[sec] = compress(serialize_records(recs), comp)
    build_ole(streams, out_path)


def fill_blank_paragraph_text(path, out_path, edits):
    """Insert text into paragraphs that have PARA_HEADER but no PARA_TEXT.
    edits: {section_name: {header_index: new_text_str_or_list_of_lines}}.

    This is for form cells that are blank at the record level, so they do not
    appear in `inspect(...)[section]["paragraphs"]`. It refuses to edit a header
    that already owns a PARA_TEXT record; use set_paragraph_text() for those.
    """
    if is_hwpx(path):
        raise NotImplementedError(
            "fill-blank targets binary .hwp record streams; use replace_text() "
            "for .hwpx.")
    streams = read_streams(path)
    comp = is_compressed(streams)
    for sec, by_idx in edits.items():
        recs = parse_records(decompress(streams[sec], comp))
        header_owns_text = {}
        last = None
        for idx, r in enumerate(recs):
            if r.tag == T_DOC_PARA_HEADER:
                last = idx
                header_owns_text[last] = False
            elif r.tag == T_PARA_TEXT and last is not None:
                header_owns_text[last] = True
        inserts = []
        for raw_idx, value in by_idx.items():
            idx = int(raw_idx)
            if idx < 0 or idx >= len(recs) or recs[idx].tag != T_DOC_PARA_HEADER:
                raise ValueError(f"{sec}:{idx} is not a PARA_HEADER index")
            if header_owns_text.get(idx):
                raise ValueError(
                    f"{sec}:{idx} already has PARA_TEXT; use set_paragraph_text")
            controls = ["\r"]
            lines = [value] if isinstance(value, str) else list(value)
            while len(controls) < len(lines):
                controls.append(controls[-1])
            text = "".join(lines[k] + controls[k] for k in range(len(lines)))
            level = _paragraph_text_level(recs, idx)
            payload = text.encode("utf-16-le")
            inserts.append((idx, Record(T_PARA_TEXT, level, len(payload), 4, 0, payload)))
            _set_header_char_count(recs[idx], len(text))
        for idx, record in sorted(inserts, reverse=True):
            recs.insert(idx + 1, record)
        streams[sec] = compress(serialize_records(recs), comp)
    build_ole(streams, out_path)


def _normalize_rules(rules):
    norm = []
    for ru in rules:
        if isinstance(ru, (tuple, list)):
            norm.append({"old": ru[0], "new": ru[1]})
        else:
            norm.append(dict(ru))
    return norm


def replace_text(path, out_path, rules):
    """High-level find/replace across all sections of a .hwp or .hwpx.
    rules: list of (old, new) tuples, or dicts {old, new, max?, regex?}.
    Returns total number of replacements made. .hwpx is auto-detected and
    routed to replace_text_hwpx()."""
    if is_hwpx(path):
        return replace_text_hwpx(path, out_path, rules)
    norm = _normalize_rules(rules)
    streams = read_streams(path)
    comp = is_compressed(streams)
    counter = [0]
    for sec in section_names(streams):
        blob = decompress(streams[sec], comp)
        new_blob = _edit_section_blob(blob, norm, counter)
        streams[sec] = compress(new_blob, comp)
    build_ole(streams, out_path)
    return counter[0]


# ===========================================================================
# Editing — find/replace inside .hwpx (OWPML zip) text runs
# ===========================================================================
_HP_T_RE = re.compile(r"(<hp:t\b[^>]*>)(.*?)(</hp:t>)", re.S)


def _apply_rules_to_text(text, norm, counter):
    """Apply normalized (old,new,max?,regex?) rules to one visible string.
    Mutates each rule's 'done_count' so per-rule `max` caps span every run,
    and bumps counter[0]. Returns the rewritten string."""
    out = text
    for rule in norm:
        done = rule.get("done_count", 0)
        cap = rule.get("max", 10 ** 9)
        if done >= cap:
            continue
        old, new = rule["old"], rule["new"]
        if rule.get("regex"):
            out2, n = re.subn(old, new, out, count=cap - done)
        else:
            if old not in out:
                continue
            remaining = cap - done
            n = min(out.count(old), remaining)
            out2 = out.replace(old, new, remaining)
        if n:
            rule["done_count"] = done + n
            counter[0] += n
            out = out2
    return out


def _edit_hwpx_run_inner(inner, norm, counter):
    """Rewrite only the text segments of a run's mixed content, leaving inline
    elements (<hp:lineBreak/>, <hp:tab/>, markpen, …) byte-for-byte intact.
    Splitting on tags first is what keeps a later html.escape from mangling an
    inline element into &lt;hp:lineBreak/&gt; when a neighbouring run is edited.
    Entities in text are unescaped before matching and re-escaped after, so
    callers pass plain visible text just like with .hwp."""
    parts = re.split(r"(<[^>]+>)", inner)
    for i, part in enumerate(parts):
        if not part or (part[0] == "<" and part[-1] == ">"):
            continue  # an inline element/tag — never touch it
        text = html.unescape(part)
        new_text = _apply_rules_to_text(text, norm, counter)
        if new_text != text:
            parts[i] = html.escape(new_text, quote=False)
    return "".join(parts)


def _edit_hwpx_xml(xml, norm, counter):
    """Run the rules over every <hp:t> text run in one section XML string."""
    return _HP_T_RE.sub(
        lambda m: m.group(1)
        + _edit_hwpx_run_inner(m.group(2), norm, counter) + m.group(3),
        xml)


def replace_text_hwpx(path, out_path, rules):
    """Find/replace inside an .hwpx. Only Contents/section*.xml is rewritten;
    every other zip member is copied through byte-for-byte, preserving member
    order and per-member compression (so the STORED `mimetype` stays first and
    uncompressed). Matching is per text segment — a placeholder split across a
    run boundary or an inline element (<hp:lineBreak/>, a formatting change)
    won't match; keep each placeholder contiguous in one run.
    Returns the number of replacements made."""
    norm = _normalize_rules(rules)
    counter = [0]
    with zipfile.ZipFile(path) as zin:
        infos = zin.infolist()
        datas = {zi.filename: zin.read(zi.filename) for zi in infos}
    for name in datas:
        if re.fullmatch(r"Contents/section\d+\.xml", name):
            xml = datas[name].decode("utf-8")
            datas[name] = _edit_hwpx_xml(xml, norm, counter).encode("utf-8")
    with zipfile.ZipFile(out_path, "w") as zout:
        for zi in infos:  # original ZipInfo preserves name, order, compress_type
            zout.writestr(zi, datas[zi.filename])
    return counter[0]


# ===========================================================================
# OLE2 / CFBF writer (rebuilds a valid compound file from a stream dict)
# ===========================================================================
_SECTOR, _MINI, _CUTOFF = 512, 64, 4096
_FREE, _ENDCHAIN, _FATSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD


def _cfbf_key(name):
    return (len(name), name.upper())


def build_ole(streams, out_path):
    """Write `streams` (dict name->bytes, '/'-separated) as an OLE2 file.
    Rebuilds directory tree, FAT, MiniFAT and mini stream. Stream byte
    contents are preserved exactly."""
    # ---- build entry list with hierarchy from stream paths
    # entries: dict name(full path or 'Root Entry') -> node
    nodes = {}  # full_path -> {name, type, data, children:[full_paths]}
    nodes["Root Entry"] = {"name": "Root Entry", "type": 5, "data": b"",
                           "children": [], "parent": None}

    def ensure_storage(full):
        if full in nodes:
            return
        parent, _, leaf = full.rpartition("/")
        pkey = "Root Entry" if parent == "" else parent
        ensure_storage(parent) if parent else None
        nodes[full] = {"name": leaf, "type": 1, "data": b"",
                       "children": [], "parent": pkey}
        nodes[pkey]["children"].append(full)

    for path, data in streams.items():
        parent, _, leaf = path.rpartition("/")
        if parent:
            ensure_storage(parent)
            pkey = parent
        else:
            pkey = "Root Entry"
        nodes[path] = {"name": leaf, "type": 2, "data": data,
                       "children": [], "parent": pkey}
        nodes[pkey]["children"].append(path)

    # assign ids: root first
    order = ["Root Entry"] + [k for k in nodes if k != "Root Entry"]
    id_of = {k: i for i, k in enumerate(order)}
    ents = [nodes[k] for k in order]
    for e in ents:
        e["left"] = e["right"] = e["child"] = _FREE
        e["start"], e["size"] = _ENDCHAIN, 0

    # build balanced BST among siblings (CFBF ordering)
    def build_bst(child_paths):
        ids = sorted((id_of[c] for c in child_paths),
                     key=lambda i: _cfbf_key(ents[i]["name"]))
        def rec(lo, hi):
            if lo > hi:
                return _FREE
            mid = (lo + hi) // 2
            ents[ids[mid]]["left"] = rec(lo, mid - 1)
            ents[ids[mid]]["right"] = rec(mid + 1, hi)
            return ids[mid]
        return rec(0, len(ids) - 1)

    for k in order:
        if nodes[k]["children"]:
            ents[id_of[k]]["child"] = build_bst(nodes[k]["children"])

    # ---- small vs big streams
    small = [i for i, e in enumerate(ents) if e["type"] == 2 and 0 < len(e["data"]) < _CUTOFF]
    big = [i for i, e in enumerate(ents) if e["type"] == 2 and len(e["data"]) >= _CUTOFF]

    # mini stream + minifat
    mini = bytearray()
    minifat = []
    for i in small:
        d = ents[i]["data"]
        nsec = math.ceil(len(d) / _MINI)
        start = len(mini) // _MINI
        ents[i]["start"], ents[i]["size"] = start, len(d)
        mini += d + b"\x00" * (nsec * _MINI - len(d))
        for k in range(nsec):
            minifat.append(_ENDCHAIN if k == nsec - 1 else start + k + 1)
    while len(mini) % _SECTOR:
        mini += b"\x00"

    def nsec(nbytes):
        return math.ceil(nbytes / _SECTOR) if nbytes else 0

    n_dir_entries = math.ceil(len(ents) / 4) * 4
    dir_sectors = n_dir_entries * 128 // _SECTOR
    minifat_sectors = nsec(len(minifat) * 4)
    mini_sectors = len(mini) // _SECTOR
    big_sectors = sum(nsec(len(ents[i]["data"])) for i in big)

    base = big_sectors + mini_sectors + dir_sectors + minifat_sectors
    fat_sectors = 1
    while True:
        need = math.ceil((base + fat_sectors) / (_SECTOR // 4))
        if need == fat_sectors:
            break
        fat_sectors = need
    total = base + fat_sectors
    fat = [_FREE] * total

    cur = 0
    def chain(nsec):
        nonlocal cur
        if not nsec:
            return _ENDCHAIN
        start = cur
        for k in range(nsec):
            fat[cur] = _ENDCHAIN if k == nsec - 1 else cur + 1
            cur += 1
        return start

    for i in big:
        ents[i]["start"] = chain(nsec(len(ents[i]["data"])))
        ents[i]["size"] = len(ents[i]["data"])
    root_start = chain(mini_sectors)
    ents[0]["start"] = root_start if mini_sectors else _ENDCHAIN
    ents[0]["size"] = len(mini)
    dir_start = chain(dir_sectors)
    minifat_start = chain(minifat_sectors)
    fat_start = cur
    for _ in range(fat_sectors):
        fat[cur] = _FATSECT
        cur += 1

    # directory bytes
    def dir_entry(e):
        nm = e["name"].encode("utf-16-le") + b"\x00\x00"
        b = bytearray(128)
        b[0:len(nm)] = nm
        struct.pack_into("<H", b, 64, len(nm))
        b[66] = e["type"]
        b[67] = 1  # black
        struct.pack_into("<I", b, 68, e["left"])
        struct.pack_into("<I", b, 72, e["right"])
        struct.pack_into("<I", b, 76, e["child"])
        struct.pack_into("<I", b, 116, e["start"] & 0xFFFFFFFF)
        struct.pack_into("<Q", b, 120, e["size"] & 0xFFFFFFFFFFFFFFFF)
        return bytes(b)

    dbytes = bytearray()
    for e in ents:
        dbytes += dir_entry(e)
    while len(dbytes) < n_dir_entries * 128:
        eb = bytearray(128)
        struct.pack_into("<I", eb, 68, _FREE)
        struct.pack_into("<I", eb, 72, _FREE)
        struct.pack_into("<I", eb, 76, _FREE)
        dbytes += eb
    dbytes += b"\x00" * (dir_sectors * _SECTOR - len(dbytes))

    mf = b"".join(struct.pack("<I", x) for x in minifat)
    mf += b"\xFF" * (minifat_sectors * _SECTOR - len(mf))
    fb = b"".join(struct.pack("<I", x) for x in fat)
    fb += b"\xFF" * (fat_sectors * _SECTOR - len(fb))

    sectors = bytearray(total * _SECTOR)

    def put(s, blob):
        sectors[s * _SECTOR:s * _SECTOR + len(blob)] = blob

    for i in big:
        d = ents[i]["data"]
        d += b"\x00" * (nsec(len(d)) * _SECTOR - len(d))
        put(ents[i]["start"], d)
    if mini_sectors:
        put(root_start, bytes(mini))
    put(dir_start, bytes(dbytes))
    if minifat_sectors:
        put(minifat_start, mf)
    put(fat_start, fb)

    header = bytearray(512)
    header[0:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<H", header, 24, 0x003E)
    struct.pack_into("<H", header, 26, 0x0003)
    struct.pack_into("<H", header, 28, 0xFFFE)
    struct.pack_into("<H", header, 30, 0x0009)
    struct.pack_into("<H", header, 32, 0x0006)
    struct.pack_into("<I", header, 44, fat_sectors)
    struct.pack_into("<I", header, 48, dir_start)
    struct.pack_into("<I", header, 56, _CUTOFF)
    struct.pack_into("<I", header, 60, minifat_start if minifat_sectors else _ENDCHAIN)
    struct.pack_into("<I", header, 64, minifat_sectors)
    struct.pack_into("<I", header, 68, _ENDCHAIN)
    struct.pack_into("<I", header, 72, 0)
    difat = [_FREE] * 109
    for k in range(fat_sectors):
        difat[k] = fat_start + k
    for k, v in enumerate(difat):
        struct.pack_into("<I", header, 76 + k * 4, v)

    with open(out_path, "wb") as fh:
        fh.write(bytes(header) + bytes(sectors))
    return out_path
