#!/usr/bin/env python3
"""Parse a PDF into Markdown + structured JSON (local extraction).

This does everything local libraries can do reliably: text in reading order
with heading detection, ruled tables (pdfplumber/camelot), and embedded images.
Pages that need a vision model (scanned / image-only / sparse-text-over-figure)
are marked in both outputs and, by default, rendered to PNG and embedded in the
⚠️ placeholder so a vision model can Read them straight away. Borderless tables
have no ruling lines to key on locally and are best recovered via that vision
route.

Typical flow:
    # full local parse -> doc.md, doc.json, assets/, and render/ for vision pages
    python pdf_parse.py INPUT.pdf -o OUTDIR

    # skip auto-rendering the vision pages (text/tables/images only)
    python pdf_parse.py INPUT.pdf -o OUTDIR --no-vision-render

    # re-render specific pages at a different DPI (standalone, no parse)
    python pdf_parse.py INPUT.pdf -o OUTDIR --render --pages 3,7 --dpi 250

After transcribing a rendered page with a vision model, replace that page's
⚠️ placeholder block in doc.md (and the corresponding page.elements in
doc.json) with the real content. See SKILL.md for the merge step.
"""
import argparse
import os
import sys

from pdf_lib import (
    build_document, save_outputs, render_page_png, pages_needing_vision,
    classify_pages, PdfError,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("-o", "--outdir", default="parsed", help="output directory")
    ap.add_argument("--render", action="store_true",
                    help="render pages that need vision (or --pages) to PNG")
    ap.add_argument("--pages", help="comma-separated 1-based pages to render (with --render)")
    ap.add_argument("--dpi", type=int, default=200, help="render DPI (default 200)")
    ap.add_argument("--no-vision-render", action="store_true",
                    help="don't auto-render the vision pages during a normal parse "
                         "(by default they are rendered and embedded in the .md)")
    ap.add_argument("--name", help="basename for outputs (default: PDF stem)")
    ap.add_argument("--password", help="password for an encrypted PDF")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    assets_dir = os.path.join(args.outdir, "assets")
    stem = args.name or os.path.splitext(os.path.basename(args.pdf))[0]

    if args.render:
        if args.pages:
            try:
                pages = [int(x) for x in args.pages.split(",") if x.strip()]
            except ValueError:
                print("error: --pages must be comma-separated integers, e.g. --pages 3,7",
                      file=sys.stderr)
                return 2
            bad = [p for p in pages if p < 1]
            if bad:
                print(f"error: page numbers are 1-based; got {bad}", file=sys.stderr)
                return 2
        else:
            # Re-triage to find vision pages if no explicit list given.
            try:
                pages = [i.page for i in classify_pages(args.pdf, password=args.password)
                         if i.needs_vision]
            except PdfError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
        if not pages:
            print("Nothing to render (no pages flagged for vision). "
                  "Pass --pages to force.")
            return 0
        render_dir = os.path.join(args.outdir, "render")
        out = []
        for p in pages:
            path = os.path.join(render_dir, f"page_{p:03d}.png")
            try:
                render_page_png(args.pdf, p, path, dpi=args.dpi, password=args.password)
            except PdfError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            out.append(path)
        print("Rendered pages for vision transcription:")
        for p in out:
            print("  ", p)
        print("\nNext: Read each PNG with a vision model, transcribe to Markdown,")
        print("then replace the matching ⚠️ block in the .md / page.elements in the .json.")
        return 0

    render_dir = os.path.join(args.outdir, "render")
    try:
        doc = build_document(args.pdf, assets_dir, password=args.password,
                             render_vision=not args.no_vision_render,
                             render_dir=render_dir, dpi=args.dpi)
    except PdfError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    md_path = os.path.join(args.outdir, f"{stem}.md")
    json_path = os.path.join(args.outdir, f"{stem}.json")
    save_outputs(doc, md_path, json_path, rel_assets="assets", rel_render="render")

    print(f"Parsed {doc['page_count']} page(s).")
    print(f"  Markdown: {md_path}")
    print(f"  JSON:     {json_path}")
    if os.path.isdir(assets_dir) and os.listdir(assets_dir):
        print(f"  Assets:   {assets_dir}/ ({len(os.listdir(assets_dir))} file(s))")
    vision = pages_needing_vision(doc)
    if vision:
        rendered = [p["page"] for p in doc["pages"] if p.get("render")]
        print(f"\n⚠️  {len(vision)} page(s) need vision transcription: {vision}")
        if rendered:
            print(f"   Rendered for you: {render_dir}/ (embedded in the .md placeholders)")
            print("   Next: Read each rendered PNG with a vision model, transcribe it,")
            print("   then replace the matching ⚠️ block in the .md / page.elements in the .json.")
        else:
            print(f"   Render them:  python pdf_parse.py {args.pdf} -o {args.outdir} --render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
