#!/usr/bin/env python3
"""Parse a PowerPoint deck into Markdown + structured JSON.

Per slide, orders shapes by geometry (reading order), extracts tables (merged
cells included), charts (categories + series values, exact from the XML),
pictures, and speaker notes, and flags ambiguous/image-only slides.

Usage:
    python pptx_parse.py INPUT.pptx -o OUTDIR
    python pptx_parse.py INPUT.pptx -o OUTDIR --crosscheck   # markitdown second opinion
"""
import argparse
import os
import sys

from pptx_lib import build_document, save_outputs, markitdown_crosscheck, PptxError


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pptx")
    ap.add_argument("-o", "--outdir", default="parsed", help="output directory")
    ap.add_argument("--name", help="basename for outputs (default: file stem)")
    ap.add_argument("--crosscheck", action="store_true",
                    help="also write markitdown's markdown as a second opinion")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    stem = args.name or os.path.splitext(os.path.basename(args.pptx))[0]
    try:
        doc = build_document(args.pptx)
    except PptxError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    md_path = os.path.join(args.outdir, f"{stem}.md")
    json_path = os.path.join(args.outdir, f"{stem}.json")
    save_outputs(doc, md_path, json_path)

    print(f"Parsed {doc['slide_count']} slide(s).")
    print(f"  Markdown: {md_path}")
    print(f"  JSON:     {json_path}")
    for s in doc["slides"]:
        print(f"   - slide {s['index']} '{s['title'][:30]}': "
              f"confidence {s['confidence']} {s['flags'] or ''}")
    if doc["verify_slides"]:
        print(f"\n🔎 verify these slides: {doc['verify_slides']}")

    if args.crosscheck:
        md = markitdown_crosscheck(args.pptx)
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
