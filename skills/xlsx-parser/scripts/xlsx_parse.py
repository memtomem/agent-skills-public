#!/usr/bin/env python3
"""Parse a messy spreadsheet into Markdown + structured JSON.

Detects multiple table regions per sheet, finds the real header row, preserves
merged cells as HTML, shows cached formula values, lists charts, and flags
low-confidence sheets for review.

Usage:
    python xlsx_parse.py INPUT.xlsx -o OUTDIR
    python xlsx_parse.py INPUT.xlsx -o OUTDIR --crosscheck   # also dump markitdown's view
"""
import argparse
import os
import sys

from xlsx_lib import build_document, save_outputs, markitdown_crosscheck, XlsxError


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsx")
    ap.add_argument("-o", "--outdir", default="parsed", help="output directory")
    ap.add_argument("--name", help="basename for outputs (default: file stem)")
    ap.add_argument("--crosscheck", action="store_true",
                    help="also write markitdown's markdown as a second opinion")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    stem = args.name or os.path.splitext(os.path.basename(args.xlsx))[0]
    try:
        doc = build_document(args.xlsx)
    except XlsxError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    md_path = os.path.join(args.outdir, f"{stem}.md")
    json_path = os.path.join(args.outdir, f"{stem}.json")
    save_outputs(doc, md_path, json_path)

    print(f"Parsed {doc['sheet_count']} sheet(s).")
    print(f"  Markdown: {md_path}")
    print(f"  JSON:     {json_path}")
    for s in doc["sheets"]:
        print(f"   - {s['name']}: {s['table_count']} table(s), "
              f"confidence {s['confidence']} {s['flags'] or ''}")
    if doc["verify_sheets"]:
        print(f"\n🔎 verify these sheets: {doc['verify_sheets']}")

    if args.crosscheck:
        md = markitdown_crosscheck(args.xlsx)
        if md is None:
            print("markitdown not available — skipped cross-check")
        else:
            cc = os.path.join(args.outdir, f"{stem}.markitdown.md")
            with open(cc, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"  Cross-check (markitdown): {cc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
