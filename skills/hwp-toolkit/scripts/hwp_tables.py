#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract tables from a .hwp / .hwpx as Markdown, CSV, or JSON.

Reconstructs the real 2-D grid (resolving rowspan/colspan and multi-paragraph
cells) that extract_text only marks as "[표]". Thin wrapper around hwp_lib —
run it from this scripts/ directory so the import resolves.

Examples:
  python hwp_tables.py report.hwp                 # all tables as Markdown
  python hwp_tables.py report.hwp -f csv -t 2     # 2nd table as CSV
  python hwp_tables.py report.hwpx -f json -o tables.json
"""
import argparse
import json
import sys

import hwp_lib


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract tables from a .hwp/.hwpx file.")
    ap.add_argument("file", help="path to a .hwp or .hwpx file")
    ap.add_argument("-f", "--format", choices=["md", "csv", "json"],
                    default="md", help="output format (default: md)")
    ap.add_argument("--expand", choices=["blank", "duplicate"], default=None,
                    help="how a merged cell fills the positions it covers "
                         "(default: blank for md/json, duplicate for csv)")
    ap.add_argument("-t", "--table", type=int, metavar="N",
                    help="only output the Nth table (1-based)")
    ap.add_argument("-o", "--output", help="write to this file instead of stdout")
    args = ap.parse_args(argv)

    tables = hwp_lib.extract_tables(args.file)
    if not tables:
        print("No tables found.", file=sys.stderr)
        return 1
    if args.table is not None:
        if not 1 <= args.table <= len(tables):
            ap.error(f"--table {args.table} out of range (1..{len(tables)})")
        tables = [tables[args.table - 1]]

    if args.format == "json":
        expand = args.expand or "blank"
        out = json.dumps(hwp_lib.tables_to_json(tables, expand),
                         ensure_ascii=False, indent=2)
    elif args.format == "csv":
        expand = args.expand or "duplicate"
        out = "\n".join(hwp_lib.table_to_csv(t, expand) for t in tables)
    else:
        expand = args.expand or "blank"
        out = hwp_lib.tables_to_markdown(tables, expand)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
        print(f"Wrote {len(tables)} table(s) to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
