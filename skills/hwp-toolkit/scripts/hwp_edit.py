#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Edit text inside a .hwp (or .hwpx) file while preserving formatting/tables.

Two modes:

1) find/replace (easiest — good for filling form templates):
     python hwp_edit.py replace IN.hwp OUT.hwp \
        --pair "OOO 기초>" "온디바이스 LLM 기초>" \
        --pair " ㅇ 강좌명 : " " ㅇ 강좌명 : 온디바이스 LLM 실습"
   Or load many rules from JSON:  [{"old":"...","new":"...","max":1}]
     python hwp_edit.py replace IN.hwp OUT.hwp --rules rules.json
   Works on .hwpx too (IN.hwpx OUT.hwpx) — auto-detected; only the edited
   Contents/section*.xml changes, every other zip member is copied verbatim.

2) set paragraph by record index (precise — get indices from hwp_inspect):
     python hwp_edit.py set IN.hwp OUT.hwp --edits edits.json
   edits.json: {"BodyText/Section0": {"136": "1. 제목",
                                        "180": [" - 첫째 줄", " - 둘째 줄"]}}
   .hwp only — .hwpx has no record indices; use `replace` for .hwpx.

3) fill a record-level blank paragraph by header index:
     python hwp_edit.py fill-blank IN.hwp OUT.hwp --edits blank.json
   blank.json: {"BodyText/Section0": {"36": "홍길동"}}
   Use this when `hwp_inspect.py --json` lists a target under
   `blank_paragraphs`; do not overwrite an adjacent label paragraph.

Notes
- Replacement operates on each paragraph's visible text (for .hwpx, each
  <hp:t> run). A substring that spans two paragraphs/runs won't match (edit
  the pieces separately, or use `set` on .hwp).
- The character count stored in each paragraph header is updated automatically
  so Hangul re-lays out the text on open. Inserting whole new paragraphs,
  images, or controls is NOT supported — fill existing cells/lines instead.
"""
import argparse
import json
import sys
import hwp_lib


def cmd_replace(args):
    rules = []
    if args.rules:
        rules = json.load(open(args.rules, encoding="utf-8"))
    for pair in (args.pair or []):
        rules.append({"old": pair[0], "new": pair[1]})
    if not rules:
        sys.exit("No replacement rules given (use --pair or --rules).")
    n = hwp_lib.replace_text(args.input, args.output, rules)
    print(f"Replaced {n} occurrence(s) -> {args.output}")
    if n == 0:
        print("[!] 0 replacements — check the 'old' strings with hwp_inspect "
              "--paragraphs (spacing/control chars matter).", file=sys.stderr)


def cmd_set(args):
    raw = json.load(open(args.edits, encoding="utf-8"))
    edits = {sec: {int(k): v for k, v in by.items()} for sec, by in raw.items()}
    try:
        hwp_lib.set_paragraph_text(args.input, args.output, edits)
    except NotImplementedError as e:
        sys.exit(f"[!] {e}")
    print(f"Applied paragraph edits -> {args.output}")


def cmd_fill_blank(args):
    raw = json.load(open(args.edits, encoding="utf-8"))
    edits = {sec: {int(k): v for k, v in by.items()} for sec, by in raw.items()}
    try:
        hwp_lib.fill_blank_paragraph_text(args.input, args.output, edits)
    except (NotImplementedError, ValueError) as e:
        sys.exit(f"[!] {e}")
    print(f"Filled blank paragraph(s) -> {args.output}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("replace", help="find/replace inside paragraph text")
    r.add_argument("input")
    r.add_argument("output")
    r.add_argument("--pair", nargs=2, action="append", metavar=("OLD", "NEW"))
    r.add_argument("--rules", help="JSON file: [{old,new,max?,regex?}]")
    r.set_defaults(func=cmd_replace)

    s = sub.add_parser("set", help="set paragraph text by record index")
    s.add_argument("input")
    s.add_argument("output")
    s.add_argument("--edits", required=True, help="JSON: {section:{index:text}}")
    s.set_defaults(func=cmd_set)

    b = sub.add_parser("fill-blank",
                       help="insert text into a PARA_HEADER with no PARA_TEXT")
    b.add_argument("input")
    b.add_argument("output")
    b.add_argument("--edits", required=True,
                   help="JSON: {section:{header_index:text}}")
    b.set_defaults(func=cmd_fill_blank)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
