"""Core library for parsing unstructured PDF documents.

A single PDF page can mix body text, multi-column layout, ruled tables,
charts, scanned images, and figures. No single extractor handles all of
these well, so this library follows a *triage-then-route* strategy:

1. Look at each page and decide what it mostly is (``classify_pages``).
2. Pull out what local libraries can read reliably — the text layer
   (PyMuPDF, with reading-order and heading heuristics), ruled tables
   (pdfplumber / camelot), and embedded raster images.
3. Flag the pages that local tools *cannot* read on their own (scanned /
   image-only / low-text pages). The caller renders those to PNG and lets
   a vision model transcribe them — that is the "vision fallback" half of
   the hybrid, and it is also the path that handles Korean OCR without any
   tesseract language packs installed.
4. Assemble everything, in reading order, into Markdown + a structured
   JSON element tree (``to_markdown`` / ``build_document``).

The CLI wrappers (``pdf_triage.py``, ``pdf_parse.py``) are thin and just
call into here. Put real logic in this file.

Only the standard scientific-PDF stack is required: PyMuPDF (``fitz``) and
pdfplumber. camelot and tesseract are used opportunistically if importable.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import statistics
import warnings
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import fitz  # PyMuPDF

try:
    import pdfplumber
    _HAVE_PDFPLUMBER = True
except Exception:  # pragma: no cover
    _HAVE_PDFPLUMBER = False

try:
    import camelot  # noqa: F401
    _HAVE_CAMELOT = True
except Exception:  # pragma: no cover
    _HAVE_CAMELOT = False


class PdfError(Exception):
    """User-facing error for an unreadable, missing, or encrypted PDF.

    Raised instead of letting a raw PyMuPDF traceback escape so the CLIs can
    print a clean one-line message.
    """


def _open_pdf(pdf_path: str, password: Optional[str] = None) -> "fitz.Document":
    """Open a PDF with friendly errors. The caller must close the document.

    Raises PdfError for a missing file, a corrupt/non-PDF file, or an
    encrypted PDF when no (or the wrong) password is supplied.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:  # FileNotFoundError, FileDataError, ...
        raise PdfError(f"cannot open {pdf_path!r}: {e}") from e
    if doc.needs_pass:
        if not doc.authenticate(password or ""):
            doc.close()
            raise PdfError(
                f"{pdf_path!r} is password-protected — rerun with --password PASSWORD"
            )
    return doc


# --------------------------------------------------------------------------
# Page triage
# --------------------------------------------------------------------------

# Route names returned by classify_pages. They describe how the page should
# be processed, not a rigid taxonomy — a page can be reasonably handled by
# more than one route, and the thresholds below are deliberately gentle.
ROUTE_TEXT = "text"        # clean text layer, simple single flow
ROUTE_MIXED = "mixed"      # text plus figures/images or multiple columns
ROUTE_TABLE = "table"      # ruled tables dominate the page
ROUTE_SCANNED = "scanned"  # little/no text layer; needs OCR / vision


@dataclass
class PageInfo:
    page: int                 # 1-based page number
    route: str
    width: float
    height: float
    char_count: int
    block_count: int
    image_count: int
    image_area_ratio: float   # fraction of page area covered by raster images
    table_line_score: int     # crude count of long horizontal/vertical rules
    columns: int              # estimated text columns
    needs_vision: bool        # True => render page and hand to a vision model
    reason: str               # human-readable explanation of the routing


def _image_area_ratio(page: "fitz.Page") -> tuple[int, float]:
    """Return (image_count, fraction of page area covered by images)."""
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    covered = 0.0
    count = 0
    seen = set()
    for img in page.get_images(full=True):
        xref = img[0]
        for r in page.get_image_rects(xref):
            key = (round(r.x0), round(r.y0), round(r.x1), round(r.y1))
            if key in seen:
                continue
            seen.add(key)
            covered += abs(r.width * r.height)
            count += 1
    return count, min(covered / page_area, 1.0)


def _table_line_score(page: "fitz.Page") -> int:
    """Count long straight strokes — a cheap proxy for ruled tables.

    We look at vector drawings rather than running a full table detector,
    because this runs on every page and only needs to be good enough to
    route the page to the table extractor for a closer look.
    """
    w, h = page.rect.width, page.rect.height
    h_thresh = w * 0.20          # a "long" horizontal rule
    v_thresh = h * 0.10          # a "long" vertical rule
    cell_min_w = w * 0.06        # a table cell is at least this wide
    cell_max_h = h * 0.25        # ...and not as tall as a figure block
    score = 0
    try:
        drawings = page.get_drawings()
    except Exception as e:
        warnings.warn(f"get_drawings() failed on page {page.number + 1}: {e}")
        return 0
    for d in drawings:
        for item in d.get("items", []):
            if item[0] == "l":  # line segment: ("l", p1, p2)
                p1, p2 = item[1], item[2]
                dx, dy = abs(p1.x - p2.x), abs(p1.y - p2.y)
                if dy < 2 and dx >= h_thresh:
                    score += 1
                elif dx < 2 and dy >= v_thresh:
                    score += 1
            elif item[0] == "re":  # rectangle — full-grid line OR table cell
                rect = item[1]
                rw, rh = abs(rect.width), abs(rect.height)
                # A full-width/height border behaves like a long rule.
                if rw >= h_thresh and rh < 2:
                    score += 1
                elif rh >= v_thresh and rw < 2:
                    score += 1
                # A cell-shaped box: wider than a cell, shorter than a figure.
                # Many of these stacked == a ruled table grid (common in Word/
                # reportlab exports that draw per-cell boxes rather than lines).
                elif rw >= cell_min_w and 4 <= rh <= cell_max_h:
                    score += 1
    return score


def _estimate_columns(blocks: list[dict]) -> int:
    """Estimate column count from the x-positions of text blocks.

    Two clusters of left edges that don't overlap vertically suggest two
    columns. This is intentionally conservative: most documents are one
    column and we don't want false positives scrambling reading order.
    """
    text_blocks = [b for b in blocks if b.get("type") == 0 and b.get("lines")]
    if len(text_blocks) < 6:
        return 1
    page_left = min(b["bbox"][0] for b in text_blocks)
    page_right = max(b["bbox"][2] for b in text_blocks)
    mid = (page_left + page_right) / 2
    gap = (page_right - page_left) * 0.02  # small dead-zone straddling the midline
    # Classify each block by its CENTER into mutually-exclusive sides, so a
    # full-width block (title, centered caption) lands in neither half instead
    # of being double-counted as both left and right.
    left = right = straddle = 0
    for b in text_blocks:
        cx = (b["bbox"][0] + b["bbox"][2]) / 2
        if cx < mid - gap:
            left += 1
        elif cx > mid + gap:
            right += 1
        else:
            straddle += 1
    n = len(text_blocks)
    # Both halves must hold a real share of blocks, and few may straddle.
    if left >= 3 and right >= 3 and (left + right) >= 0.7 * n and straddle <= 0.3 * n:
        return 2
    return 1


def classify_page(page: "fitz.Page") -> PageInfo:
    raw = page.get_text("dict")
    blocks = raw.get("blocks", [])
    text = page.get_text("text") or ""
    char_count = len(text.strip())
    block_count = sum(1 for b in blocks if b.get("type") == 0)
    img_count, img_ratio = _image_area_ratio(page)
    line_score = _table_line_score(page)
    columns = _estimate_columns(blocks)

    # Routing. Order matters: scanned check first (a page that is one big
    # image with no text can't be read locally no matter what else is true).
    needs_vision = False
    if char_count < 30 and img_ratio > 0.55:
        route = ROUTE_SCANNED
        needs_vision = True
        reason = "almost no text layer but page is mostly a raster image — likely scanned/figure page"
    elif char_count < 15 and block_count == 0:
        route = ROUTE_SCANNED
        needs_vision = True
        reason = "empty text layer — needs OCR/vision"
    elif line_score >= 8 and char_count < 4000:
        route = ROUTE_TABLE
        reason = f"{line_score} ruled strokes detected — table-dominant page"
    elif img_ratio > 0.18 or columns > 1 or (img_count > 0 and block_count > 0):
        route = ROUTE_MIXED
        reason = (
            f"text + {img_count} image(s) ({img_ratio:.0%} area)"
            + (", multi-column" if columns > 1 else "")
        )
        # A mixed page with a big image AND thin text may still hide content
        # inside the image (a chart with embedded labels, an infographic).
        if img_ratio > 0.45 and char_count < 400:
            needs_vision = True
            reason += " — sparse text over large figure, vision recommended"
    else:
        route = ROUTE_TEXT
        reason = "clean text layer, simple layout"

    return PageInfo(
        page=page.number + 1,
        route=route,
        width=round(page.rect.width, 1),
        height=round(page.rect.height, 1),
        char_count=char_count,
        block_count=block_count,
        image_count=img_count,
        image_area_ratio=round(img_ratio, 3),
        table_line_score=line_score,
        columns=columns,
        needs_vision=needs_vision,
        reason=reason,
    )


def classify_pages(pdf_path: str, password: Optional[str] = None) -> list[PageInfo]:
    out = []
    doc = _open_pdf(pdf_path, password)
    try:
        for page in doc:
            out.append(classify_page(page))
    finally:
        doc.close()
    return out


# --------------------------------------------------------------------------
# Text extraction with reading order + heading detection
# --------------------------------------------------------------------------

@dataclass
class Element:
    type: str                       # heading | paragraph | table | image
    page: int
    bbox: list[float] = field(default_factory=list)
    text: str = ""
    level: Optional[int] = None     # for headings
    rows: Optional[list[list[str]]] = None  # for tables
    path: Optional[str] = None      # for images
    note: Optional[str] = None      # provenance: "auto-detected" (tables);
    #                                 "vision" is set by the agent during merge

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, [], "")}


def _body_font_size(page: "fitz.Page") -> float:
    """Most common rounded span size — treated as the body text size."""
    sizes: list[float] = []
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                if span.get("text", "").strip():
                    sizes.append(round(span["size"], 1))
    if not sizes:
        return 0.0
    try:
        return statistics.mode(sizes)
    except statistics.StatisticsError:
        return statistics.median(sizes)


def _sort_blocks_reading_order(blocks: list[dict], columns: int, page_width: float) -> list[dict]:
    """Order blocks top-to-bottom, but column-by-column when 2 columns."""
    text_blocks = [b for b in blocks if b.get("type") == 0 and b.get("lines")]
    if columns <= 1:
        return sorted(text_blocks, key=lambda b: (round(b["bbox"][1] / 3), b["bbox"][0]))
    # Split on the content midline using each block's CENTER (matching
    # _estimate_columns), then read the left column fully before the right.
    page_left = min(b["bbox"][0] for b in text_blocks)
    page_right = max(b["bbox"][2] for b in text_blocks)
    mid = (page_left + page_right) / 2
    def center(b: dict) -> float:
        return (b["bbox"][0] + b["bbox"][2]) / 2
    left = sorted([b for b in text_blocks if center(b) < mid], key=lambda b: b["bbox"][1])
    right = sorted([b for b in text_blocks if center(b) >= mid], key=lambda b: b["bbox"][1])
    return left + right


def _block_text_and_size(block: dict) -> tuple[str, float, bool]:
    """Collapse a block into (text, max_span_size, mostly_bold)."""
    parts: list[str] = []
    max_size = 0.0
    bold_chars = 0
    total_chars = 0
    for line in block.get("lines", []):
        line_parts = []
        for span in line.get("spans", []):
            t = span.get("text", "")
            if not t:
                continue
            line_parts.append(t)
            max_size = max(max_size, span.get("size", 0))
            n = len(t.strip())
            total_chars += n
            flags = span.get("flags", 0)
            font = span.get("font", "")
            if flags & 16 or "Bold" in font or "bold" in font:
                bold_chars += n
        if line_parts:
            parts.append("".join(line_parts))
    text = "\n".join(parts).strip()
    mostly_bold = total_chars > 0 and bold_chars / total_chars > 0.6
    return text, max_size, mostly_bold


def extract_text_elements(page: "fitz.Page", columns: int) -> list[Element]:
    body = _body_font_size(page)
    blocks = page.get_text("dict").get("blocks", [])
    ordered = _sort_blocks_reading_order(blocks, columns, page.rect.width)
    elements: list[Element] = []
    for b in ordered:
        text, size, bold = _block_text_and_size(b)
        if not text:
            continue
        bbox = [round(x, 1) for x in b["bbox"]]
        # Heading heuristic: noticeably larger than body, or bold + short.
        is_heading = False
        level = None
        if body and size >= body * 1.35:
            is_heading = True
            ratio = size / body
            level = 1 if ratio >= 1.8 else 2 if ratio >= 1.45 else 3
        elif body and bold and size >= body * 1.1 and len(text) < 80 and "\n" not in text:
            is_heading = True
            level = 3
        if is_heading:
            elements.append(Element(type="heading", page=page.number + 1, bbox=bbox,
                                     text=re.sub(r"\s+", " ", text), level=level))
        else:
            elements.append(Element(type="paragraph", page=page.number + 1, bbox=bbox, text=text))
    return elements


# --------------------------------------------------------------------------
# Table extraction
# --------------------------------------------------------------------------

def _clean_cell(v: Any) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _is_real_table(rows: list[list[str]]) -> bool:
    """Reject degenerate "tables" — a single column or single row is almost
    always a misfire (a list, or the tick labels of a chart axis picked up by
    alignment). A real table needs at least 2 columns and 2 rows."""
    if len(rows) < 2:
        return False
    if max(len(r) for r in rows) < 2:
        return False
    cols_with_data = max(sum(1 for c in r if c) for r in rows)
    return cols_with_data >= 2


def _table_cell_count(rows: list[list[str]]) -> int:
    """Number of non-empty cells — the score used to pick the best candidate."""
    return sum(1 for r in rows for c in r if c)


def _pick_best_table(candidates: list[tuple]) -> Optional[tuple]:
    """Of several (rows, bbox) candidates from different engines, keep the one
    with the most non-empty cells (avoids emitting an empty husk). Returns None
    if no candidate is a real table."""
    real = [c for c in candidates if _is_real_table(c[0])]
    if not real:
        return None
    return max(real, key=lambda item: _table_cell_count(item[0]))


def _camelot_table_bbox(table: Any, page_height: Optional[float]) -> Optional[list[float]]:
    """Convert a camelot table's extent to a top-left-origin bbox.

    camelot reports cell coordinates in PDF points with a **bottom-left**
    origin (pdfminer's convention), whereas pdfplumber's ``Table.bbox`` and the
    rest of this module use a **top-left** origin. Without this conversion a
    camelot-sourced table carries no usable bbox, so it (a) can't be slotted
    into reading order and (b) can't suppress the loose text the bare text layer
    emits for the same cells — the numbers then appear twice. We mirror the
    pdfplumber convention here so both engines' tables behave identically.

    ``page_height`` must be the **mediabox** height in points — the reference
    pdfminer (and therefore both camelot AND pdfplumber's top-left ``top``) uses.
    Note this is NOT ``PageInfo.height`` / ``page.rect.height``, which PyMuPDF
    reports as the *cropbox* height; when a page's cropbox is inset from its
    mediabox the two differ, and using the cropbox height would shift every
    camelot bbox relative to pdfplumber's. Without a height the y-flip is
    impossible, so we return None and fall back to the prior (bbox-less)
    behaviour. Any structural surprise in camelot's objects also falls back to
    None rather than emitting a wrong box.
    """
    if not page_height:
        return None
    xs: list[float] = []
    ys: list[float] = []
    try:
        for row in getattr(table, "cells", None) or []:
            for cell in row:
                xs.extend((cell.x1, cell.x2))
                ys.extend((cell.y1, cell.y2))
    except Exception:
        xs, ys = [], []
    if not xs or not ys:
        # Older/edge camelot objects expose the table extent directly instead.
        bb = getattr(table, "_bbox", None)
        try:
            if bb is not None and len(bb) == 4:
                x0, y0, x1, y1 = (float(v) for v in bb)
                return [round(min(x0, x1), 1), round(page_height - max(y0, y1), 1),
                        round(max(x0, x1), 1), round(page_height - min(y0, y1), 1)]
        except Exception:
            pass
        return None
    return [round(min(xs), 1), round(page_height - max(ys), 1),
            round(max(xs), 1), round(page_height - min(ys), 1)]


def extract_tables(pdf_path: str, page_number: int,
                   password: Optional[str] = None,
                   page_height: Optional[float] = None) -> list[Element]:
    """Extract tables on a page (1-based) as Element(type='table').

    Tries pdfplumber first (find_tables, line strategy), then camelot
    (lattice, then stream) as a second opinion if it is importable. Returns
    whichever yields the most non-empty cells.

    ``page_height`` (the **mediabox** height in points) lets camelot's
    bottom-left cell coordinates be converted to the top-left bbox the rest of
    the module uses; pass it whenever it is known (``parse_page`` does).
    pdfplumber already reports top-left coordinates, so it does not need it.
    """
    # Each candidate is (rows, bbox_or_None). bbox lets us (a) place the table
    # in reading order and (b) suppress the loose text the bare text layer also
    # produces for the same cells (otherwise the numbers appear twice).
    candidates: list[tuple[list[list[str]], Optional[list[float]]]] = []
    if _HAVE_PDFPLUMBER:
        try:
            with pdfplumber.open(pdf_path, password=password) as pdf:
                pg = pdf.pages[page_number - 1]
                for tbl in pg.find_tables() or []:
                    rows = [[_clean_cell(c) for c in row] for row in tbl.extract()]
                    rows = [r for r in rows if any(r)]
                    if rows:
                        bb = [round(v, 1) for v in tbl.bbox]  # (x0, top, x1, bottom)
                        candidates.append((rows, bb))
        except Exception as e:
            warnings.warn(f"pdfplumber table extraction failed on page {page_number}: {e}")
    if _HAVE_CAMELOT:
        warnings.filterwarnings("ignore", module="camelot")
        for flavor in ("lattice", "stream"):
            try:
                tables = camelot.read_pdf(pdf_path, pages=str(page_number), flavor=flavor)
                for t in tables:
                    rows = [[_clean_cell(c) for c in row] for row in t.data]
                    rows = [r for r in rows if any(r)]
                    if rows:
                        candidates.append((rows, _camelot_table_bbox(t, page_height)))
                if tables.n:
                    break
            except Exception as e:
                warnings.warn(f"camelot {flavor} failed on page {page_number}: {e}")
                continue

    best = _pick_best_table(candidates)
    if best is None:
        return []
    best_rows, best_bbox = best
    el = Element(type="table", page=page_number, rows=best_rows, note="auto-detected")
    if best_bbox:
        el.bbox = best_bbox
    return [el]


# --------------------------------------------------------------------------
# Image / figure extraction
# --------------------------------------------------------------------------

def extract_images(page: "fitz.Page", doc: "fitz.Document", out_dir: str,
                   min_area_ratio: float = 0.03) -> list[Element]:
    """Save embedded raster images above a size threshold; return Elements.

    Tiny images (bullets, logos, rules) are skipped — they add noise to the
    output. The threshold is on image area relative to the page.
    """
    os.makedirs(out_dir, exist_ok=True)
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    elements: list[Element] = []
    seen_xref = set()
    idx = 0
    for img in page.get_images(full=True):
        xref = img[0]
        if xref in seen_xref:
            continue
        seen_xref.add(xref)
        rects = page.get_image_rects(xref)
        if not rects:
            continue
        area = max(abs(r.width * r.height) for r in rects)
        if area / page_area < min_area_ratio:
            continue
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.n - pix.alpha >= 4:  # CMYK / other -> RGB
                pix = fitz.Pixmap(fitz.csRGB, pix)
            fname = f"p{page.number + 1}_img{idx}.png"
            fpath = os.path.join(out_dir, fname)
            pix.save(fpath)
            r = rects[0]
            elements.append(Element(type="image", page=page.number + 1,
                                    bbox=[round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)],
                                    path=fpath))
            idx += 1
        except Exception:
            continue
    return elements


def _save_page_png(page: "fitz.Page", out_path: str, dpi: int = 200) -> str:
    """Rasterize an already-open page to PNG. Shared by render_page_png (which
    opens/validates the file) and build_document (which already holds the doc)."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    pix = page.get_pixmap(dpi=dpi)
    pix.save(out_path)
    return out_path


def render_page_png(pdf_path: str, page_number: int, out_path: str, dpi: int = 200,
                    password: Optional[str] = None) -> str:
    """Render a full page (1-based) to PNG for the vision-model fallback."""
    doc = _open_pdf(pdf_path, password)
    try:
        if not (1 <= page_number <= doc.page_count):
            raise PdfError(
                f"page {page_number} out of range — document has {doc.page_count} "
                f"page(s); page numbers are 1-based"
            )
        _save_page_png(doc[page_number - 1], out_path, dpi=dpi)
    finally:
        doc.close()
    return out_path


# --------------------------------------------------------------------------
# Document assembly
# --------------------------------------------------------------------------

def _interleave_by_position(text_els: list[Element], other_els: list[Element]) -> list[Element]:
    """Insert tables/images into the already-ordered text flow by vertical
    position, WITHOUT reordering the text elements relative to each other.

    text_els arrives in reading order (column-by-column on 2-column pages). A
    naive global sort by y would interleave the two columns row-by-row and
    destroy that order, so we keep text_els fixed and slot each non-text
    element in just before the first text block that starts at or below it.
    """
    if not other_els:
        return list(text_els)

    def top(e: Element) -> float:
        return e.bbox[1] if e.bbox else 1e9

    result = list(text_els)
    # Insert top-most last so each insertion lands before any lower element
    # already placed; bbox-less elements (top=inf) append at the end.
    for oe in sorted(other_els, key=top, reverse=True):
        y = top(oe)
        idx = next((i for i, te in enumerate(result)
                    if te.type in ("heading", "paragraph", "list_item") and top(te) >= y),
                   len(result))
        result.insert(idx, oe)
    return result


def _drop_text_inside_tables(text_els: list[Element],
                             table_boxes: list[list[float]]) -> list[Element]:
    """Remove paragraph/heading elements whose CENTER falls inside a detected
    table's bbox, so table cell text isn't printed twice (once as the table,
    once as loose paragraphs).

    The check is 2-D on purpose: an earlier version keyed only on the table's
    vertical band (top/bottom y), which also dropped text that merely sat at the
    same height *beside* the table — e.g. a right-column paragraph or side note
    level with a left-column table — silently losing content. Requiring the text
    center to be inside the table's x-range too (with a small tolerance) spares
    that neighbouring text while still catching the real in-cell duplicates.
    """
    if not table_boxes:
        return text_els

    def inside(e: Element) -> bool:
        if e.type not in ("paragraph", "heading") or not e.bbox:
            return False
        cx = (e.bbox[0] + e.bbox[2]) / 2
        cy = (e.bbox[1] + e.bbox[3]) / 2
        return any(x0 - 2 <= cx <= x1 + 2 and y0 - 2 <= cy <= y1 + 2
                   for x0, y0, x1, y1 in table_boxes)

    return [e for e in text_els if not inside(e)]


def parse_page(pdf_path: str, doc: "fitz.Document", info: PageInfo,
               assets_dir: str, password: Optional[str] = None) -> list[Element]:
    """Run the local extractors appropriate to a page's route.

    Pages flagged needs_vision still get whatever text *can* be read locally;
    the caller layers the vision transcription on top. We never throw away
    the text layer just because a page is figure-heavy.
    """
    page = doc[info.page - 1]
    text_els = extract_text_elements(page, info.columns)
    other: list[Element] = []
    # Only attempt table extraction when there's actual ruling-line evidence
    # (or the page was routed as a table). Running it on every mixed/multi-column
    # page turns ordinary two-column prose into a garbage "table", because the
    # aligned columns look table-shaped to the extractor. Genuinely borderless
    # tables have no lines to key on and are better handled via vision.
    if info.route == ROUTE_TABLE or info.table_line_score >= 4:
        # Use the mediabox height (not info.height, which is the cropbox height)
        # so camelot's mediabox-space cell coords flip to the same top-left
        # space pdfplumber reports — see _camelot_table_bbox.
        other.extend(extract_tables(pdf_path, info.page, password,
                                    page_height=page.mediabox.height))
    other.extend(extract_images(page, doc, assets_dir))
    # Drop loose text that lands inside a detected table, to avoid printing the
    # same cells twice (once as a table, once as paragraphs). Header cells can be
    # classified as 'heading', so those are suppressed too — a real section title
    # above the table sits outside the box and is spared.
    table_boxes = [e.bbox for e in other if e.type == "table" and e.bbox]
    text_els = _drop_text_inside_tables(text_els, table_boxes)
    return _interleave_by_position(text_els, other)


def build_document(pdf_path: str, assets_dir: str,
                   password: Optional[str] = None, *,
                   render_vision: bool = False, render_dir: Optional[str] = None,
                   dpi: int = 200) -> dict:
    """Full local parse. Returns the JSON document dict.

    Pages with needs_vision=True are included with their local elements plus
    a placeholder marker so the caller knows to render + transcribe them.

    When ``render_vision`` is true, each needs_vision page is also rasterized to
    ``render_dir`` (default: a ``render/`` folder beside ``assets_dir``) and its
    path recorded as ``page["render"]``, so the placeholder can embed the
    rendered page and a vision model can Read it directly. Library callers leave
    this off (no side effects); the CLI turns it on.
    """
    infos = classify_pages(pdf_path, password)
    if render_vision and render_dir is None:
        render_dir = os.path.join(os.path.dirname(assets_dir) or ".", "render")
    pages_out = []
    doc = _open_pdf(pdf_path, password)
    try:
        for info in infos:
            els = parse_page(pdf_path, doc, info, assets_dir, password)
            page_dict = {
                "page": info.page,
                "route": info.route,
                "width": info.width,
                "height": info.height,
                "needs_vision": info.needs_vision,
                "reason": info.reason,
                "elements": [e.to_dict() for e in els],
            }
            if render_vision and info.needs_vision:
                rpath = os.path.join(render_dir, f"page_{info.page:03d}.png")
                try:
                    _save_page_png(doc[info.page - 1], rpath, dpi=dpi)
                    page_dict["render"] = rpath
                except Exception as e:  # rendering is best-effort, never fatal
                    warnings.warn(f"failed to render page {info.page} for vision: {e}")
            pages_out.append(page_dict)
    finally:
        doc.close()
    return {
        "source": os.path.basename(pdf_path),
        "page_count": len(infos),
        "pages": pages_out,
    }


# --------------------------------------------------------------------------
# Markdown rendering
# --------------------------------------------------------------------------

# Inline characters whose markdown meaning we neutralize in extracted body
# text so literal PDF content renders verbatim. Backslash is first in the class
# so re.sub escapes it before (not after) the others — avoiding double escaping.
# We deliberately keep this minimal: emphasis/code markers, link/image brackets,
# the table pipe, strikethrough tildes, and the autolink/HTML angle bracket.
# Dots, parentheses and braces are NOT escaped — they don't change rendering in
# running prose and escaping them produces noisy, hard-to-read source.
_MD_INLINE = re.compile(r"([\\`*_\[\]<>~|])")


def _escape_md(text: str, block_leading: bool = True) -> str:
    """Escape markdown so extracted text renders as its literal characters.

    Inline emphasis/link/code markers are always neutralized. When
    ``block_leading`` is true (running text), markers that only act at the start
    of a line — ATX headings ``#``, blockquotes ``>``, ``-``/``+`` bullets,
    ``1.``/``1)`` ordered lists, and ``---``/``===`` rules/setext underlines —
    are escaped too. Table cells pass ``block_leading=False``: a cell beginning
    with ``-`` is data, not a bullet, so only inline escaping applies.
    """
    if not text:
        return text
    out: list[str] = []
    for line in text.split("\n"):
        esc = _MD_INLINE.sub(r"\\\1", line)
        if block_leading:
            esc = re.sub(r"^(\s*)([#>])", r"\1\\\2", esc)              # heading / blockquote
            esc = re.sub(r"^(\s*)([-+])(\s)", r"\1\\\2\3", esc)        # - / + bullets (* already inline-escaped)
            esc = re.sub(r"^(\s*)(\d+)([.)])(\s)", r"\1\2\\\3\4", esc)  # 1. / 1) ordered list
            esc = re.sub(r"^(\s*)([-=])(\2{2,}\s*)$", r"\1\\\2\3", esc)  # --- / === rule / setext
        out.append(esc)
    return "\n".join(out)


def _html_comment_safe(s: str) -> str:
    """Make a string safe to embed inside an HTML comment.

    An HTML comment ends at the first ``-->`` (or ``--!>``), so a crafted value
    — e.g. a PDF filename containing ``-->`` — could otherwise close the comment
    early and inject Markdown/HTML into the output. Dropping the angle brackets
    makes the closing sequence impossible to form while keeping the value
    readable. (Element text is escaped via _escape_md; this guards the one
    filename-derived string that lands in a comment instead.)
    """
    return s.replace("<", "").replace(">", "")


def _doc_link(base: Optional[str], real_path: str) -> str:
    """Build a forward-slash relative link for embedding in the .md.

    The .md is a portable artifact, so links must use '/' regardless of host OS.
    ``os.path.join`` would emit backslashes on Windows (which markdown treats as
    escapes, breaking the link), so we join with posixpath. ``real_path`` is the
    on-disk path (built with the OS separator); we keep only its basename.
    """
    name = os.path.basename(real_path)
    return posixpath.join(base, name) if base else real_path


def _covers_most_of_page(el: dict, page_area: float, frac: float = 0.9) -> bool:
    """True if an element's bbox covers ~the whole page — used to drop a
    full-page raster from the .md when the page is already shown via its render."""
    bb = el.get("bbox")
    if not bb or len(bb) != 4 or not page_area:
        return False
    area = abs((bb[2] - bb[0]) * (bb[3] - bb[1]))
    return area >= frac * page_area


def _rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    header = norm[0]
    body = norm[1:] if len(norm) > 1 else []
    def fmt(r: list[str]) -> str:
        # Inline-escape each cell (which turns a literal "|" into "\|") and
        # flatten newlines, so cell content can't break out of the GFM grid.
        return "| " + " | ".join(_escape_md(c, block_leading=False).replace("\n", " ")
                                 for c in r) + " |"
    lines = [fmt(header), "| " + " | ".join(["---"] * width) + " |"]
    lines += [fmt(r) for r in body]
    return "\n".join(lines)


def element_to_markdown(el: dict, rel_assets: Optional[str] = None) -> str:
    t = el.get("type")
    if t == "heading":
        level = el.get("level") or 2
        return f"{'#' * level} {_escape_md(el.get('text', '').strip())}"
    if t == "paragraph":
        return _escape_md(el.get("text", "").strip())
    if t == "table":
        return _rows_to_markdown(el.get("rows") or [])
    if t == "image":
        path = el.get("path", "")
        if rel_assets and path:
            path = _doc_link(rel_assets, path)
        cap = el.get("text") or el.get("note") or "image"
        # The caption sits inside ![...]; escape so a "]" in it can't end it early.
        return f"![{_escape_md(cap, block_leading=False)}]({path})"
    return _escape_md(el.get("text", "").strip())


def to_markdown(document: dict, rel_assets: Optional[str] = None,
                page_separators: bool = True, rel_render: Optional[str] = None) -> str:
    out: list[str] = []
    title = document.get("source", "")
    if title:
        out.append(f"<!-- parsed from {_html_comment_safe(title)} -->\n")
    for page in document.get("pages", []):
        if page_separators:
            out.append(f"<!-- page {page['page']} · route={page['route']} -->")
        render_path = page.get("render")
        if page.get("needs_vision"):
            if render_path:
                img = _doc_link(rel_render, render_path) if rel_render else render_path
                out.append(
                    f"> ⚠️ Page {page['page']} needs vision transcription "
                    f"({page.get('reason', '')}). Read the rendered image below and "
                    f"replace this block with the transcription."
                )
                out.append(f"![page {page['page']} (rendered for vision)]({img})")
            else:
                out.append(
                    f"> ⚠️ Page {page['page']} needs vision transcription "
                    f"({page.get('reason', '')}). Render with pdf_parse.py --render "
                    f"and replace this block with the transcription."
                )
        # When the whole page is already shown via its render image, drop a
        # full-page raster element so the same page isn't pictured twice.
        page_area = (page.get("width") or 0) * (page.get("height") or 0)
        for el in page.get("elements", []):
            if render_path and el.get("type") == "image" and _covers_most_of_page(el, page_area):
                continue
            md = element_to_markdown(el, rel_assets)
            if md:
                out.append(md)
        out.append("")
    return "\n\n".join(out).strip() + "\n"


# --------------------------------------------------------------------------
# Convenience
# --------------------------------------------------------------------------

def save_outputs(document: dict, md_path: str, json_path: str,
                 rel_assets: Optional[str] = None,
                 rel_render: Optional[str] = None) -> None:
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(document, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(to_markdown(document, rel_assets=rel_assets, rel_render=rel_render))


def pages_needing_vision(document: dict) -> list[int]:
    return [p["page"] for p in document.get("pages", []) if p.get("needs_vision")]
