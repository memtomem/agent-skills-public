#!/usr/bin/env python3
"""Parse a Word document into Markdown + structured JSON.

Walks the document in body order (text and tables interleaved correctly),
handles nested + merged-cell tables, recovers text boxes, headers/footers, and
flags tracked changes / comments / embedded images for review.

Usage:
    python docx_parse.py INPUT.docx -o OUTDIR
    python docx_parse.py INPUT.docx -o OUTDIR --crosscheck   # markitdown second opinion
"""
import argparse
import os
import sys

from docx_lib import build_document, save_outputs, markitdown_crosscheck, DocxError


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx")
    ap.add_argument("-o", "--outdir", default="parsed", help="output directory")
    ap.add_argument("--name", help="basename for outputs (default: file stem)")
    ap.add_argument("--crosscheck", action="store_true",
                    help="also write markitdown's markdown as a second opinion")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    stem = args.name or os.path.splitext(os.path.basename(args.docx))[0]
    try:
        doc = build_document(args.docx)
    except DocxError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    md_path = os.path.join(args.outdir, f"{stem}.md")
    json_path = os.path.join(args.outdir, f"{stem}.json")
    save_outputs(doc, md_path, json_path)

    print(f"Parsed {doc['element_count']} element(s).")
    print(f"  Markdown: {md_path}")
    print(f"  JSON:     {json_path}")
    print(f"  Confidence: {doc['confidence']} {doc['flags'] or ''}")
    if doc["needs_review"]:
        print("  🔎 needs review — check the flagged items against the source.")

    if args.crosscheck:
        md = markitdown_crosscheck(args.docx)
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
