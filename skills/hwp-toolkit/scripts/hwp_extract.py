#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract readable text from an .hwp OR .hwpx file.

Usage:
  python hwp_extract.py INPUT.hwp   [-o OUT.txt]
  python hwp_extract.py INPUT.hwpx  [-o OUT.txt]

Auto-detects the format: binary .hwp (OLE2) and .hwpx (OWPML zip) are handled
transparently. Prints the document text (one line per paragraph; binary-.hwp
table boundaries marked [표]; multi-section docs get `=== section ===`
headers) to stdout, or writes it to OUT if -o is given. For richer conversions
(Markdown/HTML) of binary .hwp prefer the `hwp5` toolchain — see SKILL.md.
"""
import argparse
import sys
import hwp_lib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--no-table-markers", action="store_true")
    args = ap.parse_args()
    text = hwp_lib.extract_text(args.input,
                                table_markers=not args.no_table_markers)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {args.output} ({len(text)} chars)", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
