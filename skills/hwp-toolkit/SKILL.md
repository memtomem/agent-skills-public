---
name: hwp-toolkit
description: >-
  Read, analyze, and edit Hangul Word Processor documents — the Korean office
  format with a .hwp or .hwpx extension (아래아한글 / 한컴오피스 한글 문서). Use
  this whenever a .hwp or .hwpx FILE is involved in ANY way: extracting or
  summarizing its text, inspecting its structure/streams/metadata (압축·암호화
  여부, 표 개수 등), filling in or doing find-and-replace on a Korean
  form/template (강의계획서, 사업계획서, 보고서, 신청서, 공문, 결재 양식 등), or
  converting it to text/Markdown/HTML/CSV. Trigger on a .hwp or .hwpx filename,
  or on mentions of "한글 파일", "한글 문서", "아래아한글", or a "한컴" document,
  even when the user doesn't say "skill" or name the extension. Standard tools
  (python-docx, PDF readers, plain unzip) do NOT work on .hwp because it is an
  OLE2 binary, not a zip — use this skill's bundled scripts instead. Do NOT use
  this skill for non-HWP documents (Word .docx, PDF, Excel .xlsx, PowerPoint
  .pptx, Google Docs, plain .txt), for Korean-language writing or 맞춤법
  (spelling/grammar) tasks that don't involve a .hwp/.hwpx file, or for
  questions about installing the Hancom Office (한컴오피스) application itself.
---

# HWP Toolkit (아래아한글 .hwp)

`.hwp` (version 5.x) is **not** a zip and **not** a Word file — it is an OLE2
compound binary. `python-docx`, `unzip`, and plain text readers all fail on it.
This skill bundles scripts that parse the real format so you can read, analyze,
and safely edit `.hwp` files.

> Scope note: the binary **.hwp** (5.x) and the newer XML-based **.hwpx** (a
> zip of OWPML XML) are different containers. All scripts auto-detect which one
> you passed. `hwp_extract.py` / `hwp_inspect.py` read both. For editing,
> `hwp_edit.py replace` (find/replace) works on **both**: on `.hwpx` it
> rewrites only the edited `Contents/section*.xml` and copies every other zip
> member through verbatim. `hwp_edit.py set` (edit by record index) is **.hwp
> only** — `.hwpx` has no record indices, so use `replace` there. See
> `references/hwp_format.md`.

## Setup

The scripts need `olefile`. Conversion helpers (text/Markdown/HTML) optionally
use `pyhwp`. Install on first use:

```bash
pip install olefile --break-system-packages          # required
pip install pyhwp   --break-system-packages           # optional: conversions
```

Run scripts from the skill's `scripts/` directory (they import `hwp_lib`):

```bash
cd <skill>/scripts
```

## Choosing what to do

| Goal | Do this |
|---|---|
| Read / summarize the text | `hwp_extract.py` (or `pyhwp` for Markdown/HTML) |
| See structure, streams, metadata, paragraph indices | `hwp_inspect.py` |
| Fill a template / find-replace text | `hwp_edit.py replace` |
| Set specific cells precisely | `hwp_edit.py set` (indices from inspect) |
| Fill record-level blank cells | `hwp_edit.py fill-blank` (header indices from inspect) |
| Convert to .txt / .md / .html | `pyhwp` toolchain (below) |

## 1. Extract text

```bash
python hwp_inspect.py FILE.hwp            # quick: is it compressed/encrypted?
python hwp_extract.py FILE.hwp            # text to stdout (tables marked [표])
python hwp_extract.py FILE.hwp -o out.txt
python hwp_extract.py FILE.hwpx           # .hwpx is auto-detected and handled
```

Multi-section documents are extracted with a `=== BodyText/SectionN ===`
header before each section, so nothing is silently concatenated or dropped.

If the file is password-protected, extraction reports it as encrypted and
stops — the toolkit cannot decrypt it. **Protocol:** tell the user the file is
encrypted, then ask them to remove the password in Hangul (보안 ▸ 문서 암호화
해제), save an unprotected copy, and resend that. Do **not** ask for the
password — the scripts have no way to use one.

## 2. Analyze structure

```bash
python hwp_inspect.py FILE.hwp                 # streams + record tag counts
python hwp_inspect.py FILE.hwp --paragraphs    # every paragraph + rec_index
python hwp_inspect.py FILE.hwp --json          # full dump for programmatic use
```

`--paragraphs` is the key to precise editing: it prints each paragraph's
`rec_index` and its current text (control chars shown as `¶`). You feed those
indices to `hwp_edit.py set`.

Some form cells are blank at the record level: they have `PARA_HEADER`,
character-shape, and line-segment records, but no `PARA_TEXT`. Those cells do
not appear in the normal paragraph list. When `--paragraphs` shows
`blank paragraphs (header_index | suggested level)`, use `hwp_edit.py
fill-blank` with that `header_index`. Do **not** append values to the adjacent
label paragraph just because the blank value cell is missing from the paragraph
list.

## 3. Edit / fill a form (the most common request)

Two approaches. **Always inspect first**, then prefer find/replace; fall back to
index-based `set` when a placeholder string is ambiguous (e.g. several cells
literally contain `"-"`).

### 3a. Find / replace — best for templates

```bash
python hwp_edit.py replace IN.hwp OUT.hwp \
  --pair " ㅇ 강좌명 : " " ㅇ 강좌명 : 온디바이스 LLM 실습" \
  --pair "OOOO (2~3줄)" "무료 Colab에서 소형 LLM을 측정하고 배포안을 설계한다."
```

Or many rules from JSON (`max` limits replacements, `regex` enables regex):

```bash
python hwp_edit.py replace IN.hwp OUT.hwp --rules rules.json
# rules.json: [{"old":"OOO 기초>","new":"온디바이스 기초>","max":1}]
```

Matching is **per paragraph on visible text**. Copy the exact placeholder
(including leading spaces and the `ㅇ`/`*` bullets) from `hwp_inspect.py
--paragraphs`. If you get "0 replacements", the spacing is off — re-check.

The same command works on `.hwpx` (`replace IN.hwpx OUT.hwpx`); there matching
is per `<hp:t>` text segment, so keep each placeholder contiguous in one run —
a string split by a `<hp:lineBreak/>` or a font change spans two runs and won't
match. Inline elements (line breaks, tabs, highlight markup) are preserved.

### 3b. Set by record index — precise control

```bash
python hwp_inspect.py IN.hwp --paragraphs        # find the indices you want
echo '{"BodyText/Section0": {"136": "1. 제목", "180": [" - 첫 줄"," - 둘째 줄"]}}' > edits.json
python hwp_edit.py set IN.hwp OUT.hwp --edits edits.json
```

Pass a **list** for a cell that holds several lines in one paragraph (the
original line-break controls are reused). One paragraph = one table cell line.

### 3c. Fill record-level blank cells

Use this when inspect reports a blank paragraph candidate:

```bash
python hwp_inspect.py IN.hwp --paragraphs
echo '{"BodyText/Section0": {"36": "홍길동"}}' > blanks.json
python hwp_edit.py fill-blank IN.hwp OUT.hwp --edits blanks.json
```

`fill-blank` inserts a `PARA_TEXT` record after the target paragraph header and
refuses to edit a header that already has text. If a target cell already has a
visible placeholder, use `set` or `replace` instead.

### What editing preserves and what it can't do

The editor only rewrites the text you change and the character-count field in
each paragraph header; **every other stream stays byte-identical**, so fonts,
tables, page layout, and images are untouched. Hangul re-flows the edited text
on open.

It can fill existing cells/lines and replace text. `fill-blank` can add the
missing text record for an existing blank paragraph slot, but the toolkit still
cannot add new table rows, images, or controls — design templates so every slot
you need already exists, or ask the user to add rows in Hangul first.

After editing, **always verify**: re-run `hwp_extract.py OUT.hwp` (or `pyhwp`)
and confirm the text is right and `olefile.isOleFile(OUT)` is true. A quick
sanity check that untouched content survived:

```bash
python - <<'PY'
import hwp_lib
a=hwp_lib.read_streams("IN.hwp"); b=hwp_lib.read_streams("OUT.hwp")
print("untouched identical:",
      all(a[k]==b[k] for k in a if not k.startswith("BodyText/Section")))
PY
```

For table forms, `hwp_extract.py` confirms text order but not cell placement,
and `hwp5txt` can omit table cell text entirely. If `hwp5html` is available,
convert the result and verify that values are in the expected table cells. Also
remember that low-level BodyText edits may leave `PrvText` and `PrvImage`
preview streams stale; do not use file-manager previews as the only check.

## 4. Convert to text / Markdown / HTML

`pyhwp` ships CLI converters (after `pip install pyhwp`):

```bash
hwp5txt  FILE.hwp                 # plain text
hwp5html --output DIR FILE.hwp    # XHTML + CSS (tables preserved)
hwp5odt  FILE.hwp                 # OpenDocument (open/convert in LibreOffice)
```

`hwp5txt` shows tables only as a `<표>` marker; for table content use
`hwp5html` and parse the XHTML, or use this skill's `hwp_extract.py`.

## Library use (Python)

For custom work, import the bundled library:

```python
import hwp_lib
hwp_lib.extract_text("f.hwp")                      # -> str
hwp_lib.inspect("f.hwp")                           # -> dict
hwp_lib.replace_text("in.hwp","out.hwp",[("OLD","NEW")])
hwp_lib.set_paragraph_text("in.hwp","out.hwp",{"BodyText/Section0":{136:"..."}})
hwp_lib.build_ole(streams_dict, "out.hwp")         # rebuild from raw streams
```

## How the format works (read when debugging)

If extraction looks garbled, an edit corrupts the file, or you hit an unusual
variant (uncompressed, multi-section, .hwpx), read `references/hwp_format.md`.
It explains the OLE container, the record stream, compression, the inline
control-character encoding (why naive text stripping leaks garbage), and the
exact bytes the editor touches.
