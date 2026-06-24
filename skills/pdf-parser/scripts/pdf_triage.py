#!/usr/bin/env python3
"""Triage a PDF: classify every page and print a parsing plan.

Run this FIRST. It tells you, per page, what kind of content it holds and
which pages local extraction can read on its own vs. which need a vision
model. Use the plan to decide where to spend effort.

Usage:
    python pdf_triage.py INPUT.pdf [--json PLAN.json]
"""
import argparse
import json
import sys
from dataclasses import asdict

from pdf_lib import classify_pages, PdfError


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf")
    ap.add_argument("--json", help="also write the full plan as JSON here")
    ap.add_argument("--password", help="password for an encrypted PDF")
    args = ap.parse_args()

    try:
        infos = classify_pages(args.pdf, password=args.password)
    except PdfError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    counts: dict[str, int] = {}
    vision = []
    print(f"{'pg':>3}  {'route':<8} {'chars':>6} {'imgs':>4} {'img%':>5} {'tbl':>3} {'col':>3}  reason")
    print("-" * 88)
    for i in infos:
        counts[i.route] = counts.get(i.route, 0) + 1
        if i.needs_vision:
            vision.append(i.page)
        flag = "👁 " if i.needs_vision else "  "
        print(f"{i.page:>3}  {i.route:<8} {i.char_count:>6} {i.image_count:>4} "
              f"{i.image_area_ratio*100:>4.0f}% {i.table_line_score:>3} {i.columns:>3}  {flag}{i.reason}")

    print("-" * 88)
    print("legend: chars=text-layer length, imgs=raster count, img%=image area, "
          "tbl=ruled-line score, col=estimated columns, 👁=needs vision")
    print("Route totals:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if vision:
        print(f"Pages needing vision transcription: {vision}")
        print(f"  -> render them:  python pdf_parse.py {args.pdf} -o OUTDIR --render "
              f"--pages {','.join(map(str, vision))}")
    else:
        print("No pages need vision — local extraction should cover the whole document.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([asdict(i) for i in infos], f, ensure_ascii=False, indent=2)
        print(f"Plan written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
