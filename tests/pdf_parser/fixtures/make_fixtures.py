"""Generate pdf-parser test fixtures from scratch (no third-party PDFs committed).

Builds a single multi-page PDF that exercises every route:
  page 1  text + headings (KR/EN)        -> route "text"
  page 2  two-column layout (KR | EN)    -> route "mixed", columns=2
  page 3  ruled financial table          -> route "table"
  page 4  raster bar chart + caption     -> route "mixed", needs_vision
  page 5  full-page raster, no text layer-> route "scanned", needs_vision

Run directly or via the autouse pytest fixture in test_pdf_parser.py.
"""
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
KR = "HYSMyeongJo-Medium"
W, H = A4


def _load_font(size: int):
    """A scalable TTF for raster fixtures, resolved cross-platform.

    The original hard-coded a Linux-only DejaVu path and fell back to PIL's
    fixed-size bitmap font silently, so the rendered raster differed between a
    macOS dev box and Linux CI. Try a list of common paths and warn (don't
    silently degrade) if none is found.
    """
    import warnings
    from PIL import ImageFont
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",            # Debian/Ubuntu
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf",                                   # macOS
        "/System/Library/Fonts/Supplemental/Arial.ttf",              # macOS
        "/System/Library/Fonts/Helvetica.ttc",                       # macOS
        "C:\\Windows\\Fonts\\arial.ttf",                            # Windows
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    warnings.warn("no scalable TTF found for fixtures; using PIL bitmap default")
    return ImageFont.load_default()


def _text(c):
    c.setFont(KR, 22); c.drawString(2 * cm, H - 3 * cm, "2025 연차보고서 (Annual Report)")
    c.setFont(KR, 13); c.drawString(2 * cm, H - 4 * cm, "1. Executive Summary 개요")
    body = ("본 보고서는 2025 회계연도의 경영 실적과 주요 사업 성과를 요약한다. "
            "매출은 전년 대비 18% 증가하였으며 영업이익률은 12.4%를 기록하였다. "
            "The company expanded into three new markets during the period.")
    t = c.beginText(2 * cm, H - 5 * cm); t.setFont(KR, 11)
    for line in [body[i:i + 46] for i in range(0, len(body), 46)]:
        t.textLine(line)
    c.drawText(t)
    c.setFont(KR, 13); c.drawString(2 * cm, H - 9 * cm, "2. Strategy 전략 방향")
    t = c.beginText(2 * cm, H - 10 * cm); t.setFont(KR, 11)
    for line in ["디지털 전환을 가속하고 지속가능 경영을 강화한다.",
                 "We prioritize R&D investment and operational efficiency.",
                 "핵심 지표는 4분기에 걸쳐 꾸준히 개선되었다."]:
        t.textLine(line)
    c.drawText(t)
    c.showPage()


def _two_column(c):
    c.setFont(KR, 16); c.drawString(2 * cm, H - 2.5 * cm, "3. 시장 분석 / Market Analysis")
    colw = (W - 4 * cm - 1 * cm) / 2
    # Multiple short paragraphs per column, each a separate text block — this
    # mirrors a real two-column article and exercises column detection (which
    # needs several blocks to cluster left/right edges).
    left_paras = [
        "국내 시장은 성숙 단계에 진입했으며 경쟁이 심화되고 있다.",
        "주요 사업자는 가격 경쟁보다 서비스 차별화에 집중한다.",
        "수요는 안정적이나 성장률은 둔화되는 추세이다.",
        "규제 환경 변화도 주의 깊게 모니터링해야 한다.",
    ]
    right_paras = [
        "Overseas markets show double-digit growth potential.",
        "Demand is driven by digital adoption and new use cases.",
        "Local partnerships reduce entry risk and speed up scaling.",
        "Currency volatility remains a key external risk factor.",
    ]
    for x, paras in [(2 * cm, left_paras), (2 * cm + colw + 1 * cm, right_paras)]:
        y = H - 3.8 * cm
        for para in paras:
            t = c.beginText(x, y); t.setFont(KR, 10)
            line = ""
            for wd in para.split(" "):
                if c.stringWidth(line + wd + " ", KR, 10) > colw:
                    t.textLine(line); line = ""
                line += wd + " "
            t.textLine(line); c.drawText(t)
            y -= 1.6 * cm
    c.showPage()


def _table(c):
    c.setFont(KR, 16); c.drawString(2 * cm, H - 2.5 * cm, "4. 재무 요약 / Financial Summary")
    data = [["항목 Item", "2023", "2024", "2025"],
            ["매출 Revenue", "980", "1,050", "1,239"],
            ["영업이익 Op.Income", "88", "102", "154"],
            ["순이익 Net Income", "61", "70", "112"],
            ["직원수 Employees", "420", "455", "511"]]
    x0, y0 = 2 * cm, H - 4 * cm
    rh, cw = 1 * cm, [5 * cm, 3 * cm, 3 * cm, 3 * cm]
    for r, row in enumerate(data):
        x = x0
        for ci, cell in enumerate(row):
            c.rect(x, y0 - r * rh, cw[ci], rh)
            c.setFont(KR, 10 if r else 11)
            c.drawString(x + 4, y0 - r * rh + 0.3 * cm, cell)
            x += cw[ci]
    c.setFont(KR, 9)
    c.drawString(2 * cm, y0 - 6 * rh, "단위: 억원 (KRW 100M). 자료: 내부 결산.")
    c.showPage()


def _chart(c):
    from reportlab.lib.utils import ImageReader
    from PIL import Image, ImageDraw
    import tempfile
    c.setFont(KR, 16); c.drawString(2 * cm, H - 2.5 * cm, "5. 분기별 매출 추이 / Quarterly Revenue")
    # Render the chart as a RASTER figure (as a real report would embed one).
    # A large image with only a short caption around it exercises the
    # mixed+vision route: the data lives inside pixels, so local text extraction
    # can't read it and the page is flagged for vision.
    fig = Image.new("RGB", (1000, 800), "white")
    dr = ImageDraw.Draw(fig)
    vals = [260, 295, 330, 354]
    labels = ["Q1", "Q2", "Q3", "Q4"]
    base_y, max_h, bar_w, gap, x = 720, 600, 160, 60, 120
    for v, lab in zip(vals, labels):
        bh = int(max_h * v / 400)
        dr.rectangle([x, base_y - bh, x + bar_w, base_y], fill=(51, 102, 204))
        dr.text((x + bar_w / 2 - 12, base_y + 12), lab, fill="black", font=_load_font(28))
        dr.text((x + bar_w / 2 - 24, base_y - bh - 36), str(v), fill="black", font=_load_font(24))
        x += bar_w + gap
    dr.text((300, 28), "2025 Revenue by Quarter", fill="black", font=_load_font(30))
    fd, tmp = tempfile.mkstemp(suffix=".png"); os.close(fd); fig.save(tmp)
    fig_w, fig_h = W - 3 * cm, H * 0.6
    c.drawImage(ImageReader(tmp), 1.5 * cm, H - 3 * cm - fig_h, width=fig_w, height=fig_h)
    c.setFont(KR, 10)
    c.drawString(2 * cm, 2 * cm, "매출은 매 분기 증가하여 4분기에 354억원을 기록하였다.")
    c.showPage()
    try:
        os.remove(tmp)
    except OSError:
        pass


def _scanned(c):
    from reportlab.lib.utils import ImageReader
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1000, 1400), "white")
    dr = ImageDraw.Draw(img)
    font = _load_font(28)
    lines = ["CONFIDENTIAL - Scanned Memo", "Date: 2025-11-03", "",
             "Subject: Vendor Agreement Renewal",
             "The contract with ACME Corp expires on",
             "Dec 31. Recommend renewal at revised",
             "terms. Signature on file. [STAMP]"]
    y = 80
    for ln in lines:
        dr.text((70, y), ln, fill="black", font=font); y += 70
    dr.rectangle([700, 600, 920, 760], outline="red", width=5)
    dr.text((720, 660), "APPROVED", fill="red", font=font)
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(tmp)
    c.drawImage(ImageReader(tmp), 0, 0, width=W, height=H)
    c.showPage()
    try:
        os.remove(tmp)
    except OSError:
        pass


def build(path: str) -> str:
    c = canvas.Canvas(path, pagesize=A4)
    _text(c); _two_column(c); _table(c); _chart(c); _scanned(c)
    c.save()
    return path


def make_all(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    build(os.path.join(out_dir, "report_mixed.pdf"))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(__file__)
    make_all(out)
    print("fixtures written to", out)
