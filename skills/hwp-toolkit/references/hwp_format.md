# HWP 5.x format notes (for debugging the toolkit)

Read this when extraction looks garbled, an edit corrupts a file, or you meet
an unusual variant. Source: Hancom's published "한글문서파일형식 5.0" spec.

## Table of contents
1. Container: OLE2 / CFBF
2. FileHeader flags (compression, encryption, version)
3. Streams you will see
4. The record stream
5. Compression
6. Paragraph text and inline control characters  ← most common gotcha
7. What the editor changes (and why it's safe)
8. Variants: uncompressed, multi-section, .hwpx
9. Quick troubleshooting

## 1. Container: OLE2 / CFBF
A `.hwp` is a Microsoft Compound File (the same container as old `.doc`/`.xls`).
Magic bytes `D0 CF 11 E0 A1 B1 1A E1`. It holds named *streams* inside
*storages* (folders), with a 512-byte sector FAT, a 64-byte mini-sector
MiniFAT for streams under 4096 bytes, and a directory of 128-byte entries
arranged as a (red-black) binary tree ordered by `(name length, uppercased
name)`. `olefile` reads it; the toolkit's `build_ole()` rebuilds it from a
`{name: bytes}` dict so a changed stream of any new size is written correctly
(you cannot just overwrite a stream in place unless its size is unchanged).

## 2. FileHeader flags
Stream `FileHeader`, 256 bytes. Signature `"HWP Document File"` then version,
then a uint32 of flags at offset 36:
- bit 0 = **compressed** (body/doc streams are raw-deflate). Almost always 1.
- bit 1 = **password/encrypted**. If set, body text is unreadable without the
  password — the toolkit detects this and refuses rather than emit garbage.
- bit 2 = distribution document, etc.

## 3. Streams you will see
- `FileHeader` — flags/version.
- `DocInfo` — fonts, char shapes, para shapes, styles, border fills (referenced
  by ID from the body). Compressed. The editor never changes it, so reused IDs
  stay valid.
- `BodyText/Section0`, `Section1`, … — the actual content, one stream per
  section. Compressed. This is what extraction/editing parses.
- `\x05HwpSummaryInformation` — OLE property set: title/author/dates. Note the
  leading `\x05` byte in the name; preserve it exactly when rebuilding.
- `PrvText` (UTF-16 preview text) and `PrvImage` (preview thumbnail) — cosmetic;
  may go stale after an edit, which is harmless.
- `DocOptions/_LinkDoc`, `Scripts/*`, `BinData/*` (embedded images) — passed
  through untouched.

## 4. The record stream
After decompression, a section/DocInfo stream is a flat list of records:

```
record = header(4 bytes) + payload
header (uint32, little-endian):
    bits  0..9   tag id        (e.g. 66 PARA_HEADER, 67 PARA_TEXT)
    bits 10..19  level         (tree depth: para vs list vs cell)
    bits 20..31  size          (payload length)
if size == 0xFFF: the real size is the next uint32, and header is 8 bytes.
```

A normal paragraph appears as the run: `PARA_HEADER(66)`, `PARA_TEXT(67)`,
`PARA_CHAR_SHAPE(68)`, `PARA_LINE_SEG(69)`. Tables are a `CTRL_HEADER(71)` with
a `tbl ` control, then `LIST_HEADER(72)` per cell wrapping the cell's
paragraphs. `clean_text`/`extract_text` walk these and emit one line per
`PARA_TEXT`.

## 5. Compression
Streams are **raw DEFLATE** (no zlib header): `zlib.decompress(data, -15)` and
`zlib.compressobj(9, DEFLATED, -15)`. If bit 0 of FileHeader flags is 0, the
streams are stored uncompressed — `hwp_lib` handles both via `is_compressed()`.

## 6. Paragraph text and inline control characters  ← the classic bug
`PARA_TEXT` payload is **UTF-16-LE**. Besides normal characters it embeds
*control characters* (code < 0x20) that come in three widths:
- **char controls** (codes 0,10,13,24–31): **1** UTF-16 unit. 10/13 are line
  breaks; others mark fields, etc.
- **inline controls** (4,5,6,7,8,9,19,20) and **extended controls**
  (1,2,3,11,12,14–18,21,22,23): **8** UTF-16 units each — the control code
  plus a 7-unit payload (often ASCII tags like `secd`, `tbl `, `gso `).

Naively dropping only chars `< 0x20` leaves the 7-unit ASCII payload behind as
garbage (you'll see text like `dse lco tbl` at the top of a section). Always
**skip the whole 8-unit control**. `hwp_lib.walk_text()` does this; reuse it.

When editing, the toolkit keeps every control character in place and only
substitutes visible text, so widths and downstream controls are preserved.

## 7. What the editor changes (and why it's safe)
For each edited paragraph the toolkit changes exactly two things:
1. the `PARA_TEXT` payload (new UTF-16-LE bytes), and
2. the first uint32 of the owning `PARA_HEADER` = the paragraph's **character
   count** (`nChars`), keeping the high bit. Hangul recomputes line layout
   (`PARA_LINE_SEG`) from this on open, so stale line segments self-heal.

Character shapes (`PARA_CHAR_SHAPE`) map *position → shape id*; appending text
extends the region governed by the last shape, so no change is needed as long
as you don't reorder text before an existing shape boundary. Everything else —
all other records, all other streams — is byte-for-byte identical. That is why
fonts, tables, and images survive.

Limits: this is text substitution, not document surgery. Inserting new
paragraphs/rows/images means adding records *and* fixing the parent
`LIST_HEADER`/cell counts and `DocInfo` references — out of scope. Fill
existing slots, or have the user add empty rows in Hangul first.

## 8. Variants
- **Uncompressed**: handled automatically.
- **Multi-section**: `extract_text`/`replace_text` iterate every
  `BodyText/SectionN`; `set_paragraph_text` takes the section name as a key.
- **.hwpx** (different format!): a ZIP of XML (OWPML, KS X 6101). `hwp_lib`
  auto-detects it (`is_hwpx`) and handles it natively — no manual `unzip` needed:
  - **Read** (`extract_text` → `extract_text_hwpx`): concatenates `<hp:t>` runs
    per `<hp:p>` across `Contents/section*.xml`. Inside a run, `<hp:lineBreak/>`
    becomes `\n` and `<hp:tab/>` becomes `\t` (`_hwpx_run_to_text`); other inline
    elements are dropped, so OWPML markup never leaks into the text.
  - **Find/replace** (`replace_text` → `replace_text_hwpx`): rewrites only the
    matched text inside each `<hp:t>` run and copies every other zip member
    through verbatim (the `mimetype` member stays first and *stored*, not
    deflated). Matching is **per run**: a placeholder split across runs by a
    `<hp:lineBreak/>`, a `<hp:tab/>`, or a formatting change spans two `<hp:t>`
    segments and won't match — keep it contiguous, or edit in Hangul first.
  - **Set-by-index does not apply** — `.hwpx` has no record indices; use
    find/replace. `hwp_inspect.py` lists the zip members.

  Recent Hangul opens both formats interchangeably; if a user only needs *a*
  working Hangul file, editing `.hwpx` is often easier than binary `.hwp`.

## 9. Quick troubleshooting
- *Garbled ASCII in extracted text* → inline-control skipping; use `walk_text`.
- *`replace` reports 0 hits* → the `old` string's spacing/bullets don't match;
  copy it verbatim from `hwp_inspect.py --paragraphs`.
- *Hangul says the file is broken* → a stream size/FAT mismatch; rebuild via
  `build_ole` (never edit stream bytes in place at a different length), and
  confirm with `olefile.isOleFile`.
- *Text shows but layout is cramped on open* → stale `PrvImage`/line segments;
  opening and re-saving in Hangul refreshes them. Harmless.
- *Encrypted* → nothing to do without the password.
