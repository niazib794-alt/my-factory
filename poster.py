"""Business Factory 5 - Pinterest poster (version 8).

The poster uses REAL pieces only:
- the screens are rendered from the actual workbook (laptop layout and phone layout), with clearly
  labelled sample rows, and the sheet itself is never drawn by hand;
- the headline comes from the approved list below for each trade;
- all text is drawn by code, so spelling is never left to an image model.
If LibreOffice or poppler is missing on the server, the screen shows a plain panel that says the
preview is not available. It never shows a fake spreadsheet.
"""
import datetime
import io
import os
import re
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

W, H = 1000, 1500
HEADLINES = {
    "plumb_elec": "Track every plumbing and electrical job in one workbook",
    "hvac": "Track every AC service call and extra part in one workbook",
    "general": "Track every build phase and change order in one workbook",
    "roofing": "Track every roof job, repair and extra material in one workbook",
    "landscape": "Track every lawn visit, add-on and crew hour in one workbook",
    "painters": "Track every room, extra patch and labor hour in one workbook",
    "handyman": "Track every repair, extra task and parts cost in one workbook",
    "other": "Track every job, extra task and cost in one workbook",
}
TAGLINE = {
    "job_costing": "Job costing and profit",
    "change_orders": "Extra work and client approvals",
    "receivables": "Invoices and payments",
    "bundle": "Job costing, approvals and payments in one file",
}
BADGES = {
    "job_costing": ["Labor, materials and subcontractors", "Overhead and profit margin per job", "Dashboard with loss warnings"],
    "change_orders": ["Client approval status for each request", "Proposed charge with your markup", "Dashboard: approved work not billed yet"],
    "receivables": ["Invoice balance and payment status", "Aging from 1-30 to 90+ days", "Follow-ups due now or late"],
    "bundle": ["Job costing and profit per job", "Extra work approvals with proposed charges", "Invoices, payments and aging"],
}
SAMPLE_NOTE = "Screens: the real workbook, with sample rows marked SAMPLE."
CTA = "Get the Workbook"
FONT_CANDIDATES = {
    "bold": ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Arial-Bold.ttf", "LiberationSans-Bold.ttf"],
    "reg": ["DejaVuSans.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"],
}
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation",
             "/usr/share/fonts", "/Library/Fonts", "C:\\Windows\\Fonts"]


def font(size, weight="reg"):
    for d in FONT_DIRS:
        for name in FONT_CANDIDATES[weight]:
            for root, _dirs, files in os.walk(d) if os.path.isdir(d) else []:
                if name in files:
                    try:
                        return ImageFont.truetype(os.path.join(root, name), size)
                    except Exception:
                        pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def wrap(draw, text, fnt, max_w):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def add_sample_rows(xlsx_bytes, module, sheets, rows=4):
    """Write four rows marked SAMPLE into the input cells of the first data tab (formulas untouched)."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    first = sheets.PRODUCT_SHEETS[module][0]
    ws = wb[first]
    specs = sheets.COLUMNS[first]
    for r in range(4, 4 + rows):
        n = r - 3
        for ci, spec in enumerate(specs, 1):
            if spec[3] is not None:
                continue
            kind = spec[1]
            if spec[4]:
                val = spec[4][0]
            elif kind == "text":
                val = f"SAMPLE {n}" if ci == 1 else "SAMPLE"
            elif kind == "date":
                val = datetime.date(2026, 11, min(n + 5, 28))
            elif kind == "money":
                val = 120.0 * n
            elif kind == "num":
                val = float(n)
            elif kind == "pct":
                val = 0.12
            else:
                val = None
            ws.cell(row=r, column=ci, value=val)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def render_workbook_screen(xlsx_bytes, marker="ENTER DATA", dpi=120):
    """PNG of the first data page of a workbook, cropped to its content. None if the tools are missing."""
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe or not shutil.which("pdftoppm") or not shutil.which("pdftotext") or not shutil.which("pdfinfo"):
        return None
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "book.xlsx")
        with open(src, "wb") as f:
            f.write(xlsx_bytes)
        subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", tmp, src],
                       timeout=180, capture_output=True)
        pdf = os.path.join(tmp, "book.pdf")
        if not os.path.exists(pdf):
            return None
        info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
        pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
        page = None
        for p in range(1, pages + 1):
            txt = subprocess.run(["pdftotext", "-f", str(p), "-l", str(p), pdf, "-"],
                                 capture_output=True, text=True).stdout
            if marker in txt:
                page = p
                break
        if page is None:
            return None
        prefix = os.path.join(tmp, "page")
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page), pdf, prefix],
                       timeout=120, capture_output=True)
        pngs = sorted(f for f in os.listdir(tmp) if f.startswith("page") and f.endswith(".png"))
        if not pngs:
            return None
        im = Image.open(os.path.join(tmp, pngs[0])).convert("RGB")
        mask = Image.eval(im.convert("L"), lambda v: 255 if v < 245 else 0)
        box = mask.getbbox()
        if box:
            im = im.crop(box)
        # start at the first row that has real content (the dark title bar), so no blank band is kept
        top = 0
        for y in range(im.height):
            if im.crop((0, y, im.width, y + 1)).convert("L").getextrema()[0] < 120:
                top = max(0, y - 4)
                break
        im = im.crop((0, top, im.width, im.height))
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _contain(im, w, h, bg=(255, 255, 255)):
    canvas = Image.new("RGB", (w, h), bg)
    if im is None:
        return canvas
    im = im.copy()
    im.thumbnail((w, h))
    canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return canvas


def _panel(w, h, text, fnt):
    canvas = Image.new("RGB", (w, h), (241, 245, 249))
    d = ImageDraw.Draw(canvas)
    for i, line in enumerate(wrap(d, text, fnt, w - 40)):
        tw = d.textlength(line, font=fnt)
        d.text(((w - tw) / 2, h / 2 - 40 + i * 34), line, font=fnt, fill=(71, 85, 105))
    return canvas


def _hex(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb):
    def f(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _text_on(rgb):
    return (255, 255, 255) if _luminance(rgb) < 0.45 else (15, 23, 42)


def make_poster(trade_key, module, trade_label, brand, primary, accent, laptop_png, phone_png):
    """Compose the 1000 x 1500 poster. Returns (PNG bytes, status text)."""
    im = Image.new("RGB", (W, H), (248, 250, 252))
    d = ImageDraw.Draw(im)
    prim, acc = _hex(primary), _hex(accent)
    # top band with a curved accent edge (drawn, not an image)
    d.rectangle([0, 0, W, 560], fill=prim)
    d.polygon([(0, 560), (W, 500), (W, 540), (0, 600)], fill=acc)
    head_fnt = font(54, "bold")
    tag_fnt = font(34, "reg")
    y = 70
    for line in wrap(d, HEADLINES.get(trade_key, HEADLINES["other"]), head_fnt, W - 120):
        d.text((60, y), line, font=head_fnt, fill=(255, 255, 255))
        y += 66
    d.text((60, max(y + 14, 440)), TAGLINE.get(module, ""), font=tag_fnt, fill=_text_on(prim) if False else acc)
    # laptop frame and screen
    d.rounded_rectangle([60, 640, 620, 1040], radius=24, fill=(31, 41, 55))
    lap_fnt = font(26, "reg")
    if laptop_png:
        scr = Image.open(io.BytesIO(laptop_png))
        im.paste(_contain(scr, 520, 350), (80, 660))
        status = "laptop: real workbook"
    else:
        im.paste(_panel(520, 350, "Preview not available on this server", lap_fnt), (80, 660))
        status = "laptop: preview not available"
    d.rounded_rectangle([60, 1040, 620, 1060], radius=8, fill=(55, 65, 81))
    # phone frame and screen
    d.rounded_rectangle([650, 760, 900, 1280], radius=34, fill=(31, 41, 55))
    if phone_png:
        scr = Image.open(io.BytesIO(phone_png))
        im.paste(_contain(scr, 224, 470), (663, 785))
        status += "; phone: real workbook"
    else:
        im.paste(_panel(224, 470, "Preview not available on this server", font(22, "reg")), (663, 785))
        status += "; phone: preview not available"
    # three badges
    by = 1100
    for text in BADGES.get(module, BADGES["bundle"]):
        d.rounded_rectangle([60, by, 940, by + 62], radius=16, fill=(255, 255, 255), outline=acc, width=3)
        d.text((90, by + 14), text, font=font(30, "reg"), fill=(15, 23, 42))
        by += 78
    # call to action button
    d.rounded_rectangle([230, 1346, 770, 1420], radius=24, fill=acc)
    btn_fnt = font(40, "bold")
    tw = d.textlength(CTA, font=btn_fnt)
    d.text(((W - tw) / 2, 1360), CTA, font=btn_fnt, fill=_text_on(acc))
    # footer: trade and brand
    foot = font(26, "reg")
    d.text((60, 1450), f"For {trade_label}", font=foot, fill=(71, 85, 105))
    bw = d.textlength(brand, font=font(28, "bold"))
    d.text((W - 60 - bw, 1448), brand, font=font(28, "bold"), fill=prim)
    d.text((60, 1482), SAMPLE_NOTE, font=font(20, "reg"), fill=(100, 116, 139))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue(), status
          
