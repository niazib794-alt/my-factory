"""Business Factory 5 - Pinterest poster (version 9).

Layout, top to bottom (1000 x 1500):
- the headline, a tagline bar and the brand logo box (brand name comes from config.py)
- a laptop with the Excel workbook and a phone with the Google Sheet
- three features that the workbook really has, and the call to action
Every screen is labelled SAMPLE unless the owner uploads a real phone screenshot.
A screen comes from the workbook itself: LibreOffice when the server has it, otherwise a table drawn from
the workbook's real column names and sample rows. Nothing here is a fake app.
"""
import datetime
import io
import os
import re
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

import config
import sheets

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
    "job_costing": "Job Costing & Profit Tracker",
    "change_orders": "Extra Work & Client Approvals",
    "receivables": "Invoices & Payment Tracker",
    "bundle": "All-in-One Contractor Bundle",
}
BADGES = {
    "job_costing": ["Labor, materials and subcontractors", "Overhead and profit margin for each job",
                    "Dashboard with loss warnings"],
    "change_orders": ["Client approval status for each request", "Proposed charge with your markup",
                      "Dashboard: approved work not billed yet"],
    "receivables": ["Invoice balance and payment status", "Aging from 1-30 to 90+ days",
                    "Follow-ups due now or late"],
    "bundle": ["Job costing and profit for each job", "Extra work approvals with proposed charges",
               "Invoices, payments and aging"],
}
CTA = "Get It Now"
PLATFORM_LINE = "Works in Google Sheets & Excel"
SAMPLE_TAG = "SAMPLE"
FOOT_NOTE = "SAMPLE = sample rows, not real figures"
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_FILES = [
    os.path.join(FONT_DIR, "Inter-ExtraBold.otf"),
    os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_FONTS = {}


def font(size):
    """The first heavy font that loads: the bundled Inter (OFL), then system fallbacks."""
    if size not in _FONTS:
        chosen = None
        for path in FONT_FILES:
            if os.path.exists(path):
                try:
                    chosen = ImageFont.truetype(path, size)
                    break
                except Exception:
                    continue
        if chosen is None:
            try:
                chosen = ImageFont.load_default(size=size)
            except TypeError:
                chosen = ImageFont.load_default()
        _FONTS[size] = chosen
    return _FONTS[size]


def fit_font(draw, text, max_w, start, minimum=24):
    size = start
    while size > minimum and draw.textlength(text, font=font(size)) > max_w:
        size -= 2
    return font(size)


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


def _hex(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb):
    def f(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _text_on(rgb):
    """Dark or white text, whichever reads better on this colour."""
    return (255, 255, 255) if _luminance(rgb) < 0.4 else (15, 23, 42)


def _shade(rgb, k):
    return tuple(int(c * k) for c in rgb)


def add_sample_rows(xlsx_bytes, module, sheets_mod, rows=4, layout="laptop"):
    """Write four rows marked SAMPLE into the input cells of the first data tab (formulas untouched).
    For the picture only, the print area is set to the top of the tab, so the screen shows the header
    and the sample rows and no page margins. The owner's workbook is not changed."""
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    first = sheets_mod.PRODUCT_SHEETS[module][0]
    ws = wb[first]
    specs = sheets_mod.COLUMNS[first]
    # proportions that suit the frames: a wide laptop view, and a tall phone view of the first columns
    shown_cols = min(len(specs), 8 if layout == "laptop" else 3)
    shown_rows = 3 + rows + 10 if layout == "laptop" else 3 + rows + 14
    ws.print_area = f"A1:{get_column_letter(shown_cols)}{shown_rows}"
    ws.page_margins.left = ws.page_margins.right = ws.page_margins.top = ws.page_margins.bottom = 0.2
    ws.page_margins.header = ws.page_margins.footer = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
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


def table_preview(module, layout):
    """A picture of the workbook's first tab, drawn from its real column names and four sample rows.
    Used only when LibreOffice is missing on the server."""
    tab = sheets.PRODUCT_SHEETS[module][0]
    headers = [s[0] for s in sheets.COLUMNS[tab]]
    laptop = layout == "laptop"
    cols = headers[:9] if laptop else headers[:4]
    w, h = (1200, 640) if laptop else (600, 1100)
    head_h, row_h = (130, 60) if laptop else (150, 84)
    im = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, 52], fill=(30, 58, 138))
    d.text((16, 12), f"{tab.upper()} - ENTER DATA IN THE YELLOW CELLS", font=font(24 if laptop else 26),
           fill=(255, 255, 255))
    step = (w - 2) / len(cols)
    hf = font(22 if laptop else 26)
    for i, text in enumerate(cols):
        x0 = 1 + i * step
        d.rectangle([x0, 60, x0 + step, 60 + head_h], fill=(51, 65, 85), outline=(203, 213, 225))
        for j, line in enumerate(wrap(d, text, hf, step - 12)[:3]):
            d.text((x0 + 6, 66 + j * (hf.size + 4)), line, font=hf, fill=(255, 255, 255))
    for r in range(4):
        y0 = 60 + head_h + r * row_h
        for i in range(len(cols)):
            x0 = 1 + i * step
            d.rectangle([x0, y0, x0 + step, y0 + row_h], fill=(255, 242, 204), outline=(203, 213, 225))
            label = f"SAMPLE {r + 1}" if i == 0 else "SAMPLE"
            d.text((x0 + 6, y0 + row_h // 2 - 12), label, font=font(20 if laptop else 24), fill=(71, 85, 105))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def screen_or_table(xlsx_bytes, module, layout):
    """The workbook screen from LibreOffice when the server has it, otherwise the table picture. Always a PNG."""
    return render_workbook_screen(xlsx_bytes) or table_preview(module, layout)


def _screen(png_bytes, w, h, sample, tag_font):
    canvas = Image.new("RGB", (w, h), (255, 255, 255))
    if png_bytes:
        try:
            src = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            src.thumbnail((w, h))
            canvas.paste(src, ((w - src.width) // 2, (h - src.height) // 2))
        except Exception:
            pass
    if sample:
        d = ImageDraw.Draw(canvas)
        tw = d.textlength(SAMPLE_TAG, font=tag_font)
        box = [w - tw - 34, 10, w - 10, 10 + tag_font.size + 16]
        d.rounded_rectangle(box, radius=10, fill=(251, 191, 36))
        d.text((box[0] + 12, box[1] + 6), SAMPLE_TAG, font=tag_font, fill=(15, 23, 42))
    return canvas


def make_poster(trade_key, module, trade_label, brand, primary, accent, laptop_png, phone_png,
                laptop_sample=True, phone_sample=True, headline=None, tagline=None, badges=None, cta=None):
    """Compose the 1000 x 1500 poster. Returns (PNG bytes, status text)."""
    prim, acc = _hex(primary), _hex(accent)
    im = Image.new("RGB", (W, H), prim)
    d = ImageDraw.Draw(im)
    bottom = _shade(prim, 0.55)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(prim[i] * (1 - t) + bottom[i] * t) for i in range(3)))

    # headline: the largest size (80 down to 52) that fits in about 300 pixels of height
    head_text = headline or HEADLINES.get(trade_key, HEADLINES["other"])
    size = 80
    while True:
        hf = font(size)
        lines = wrap(d, head_text, hf, 880)
        if len(lines) * (size + 8) <= 300 or size <= 52:
            break
        size -= 4
    y = 56
    for line in lines:
        d.text((60, y), line, font=hf, fill=(255, 255, 255))
        y += size + 8

    # tagline bar
    tag_text = tagline or TAGLINE.get(module, "")
    tf = fit_font(d, tag_text, 820, 38, 24)
    pill_y = y + 12
    pill_w = d.textlength(tag_text, font=tf) + 48
    d.rounded_rectangle([60, pill_y, 60 + pill_w, pill_y + 66], radius=33, fill=acc)
    d.text((84, pill_y + 12), tag_text, font=tf, fill=_text_on(acc))

    # brand logo box, name from the brand setting (config.py by default)
    logo = f"{(brand or config.BRAND_NAME).rstrip('.')}."
    logo_y = pill_y + 66 + 22
    lf = font(60)
    logo_w = d.textlength(logo, font=lf) + 60
    d.rounded_rectangle([60, logo_y, 60 + logo_w, logo_y + 104], radius=22, outline=(255, 255, 255), width=4)
    d.text((90, logo_y + 14), logo, font=lf, fill=(255, 255, 255))

    # laptop with the Excel workbook
    d.rounded_rectangle([40, 580, 700, 960], radius=22, fill=(17, 24, 39))
    im.paste(_screen(laptop_png, 628, 336, laptop_sample, font(22)), (56, 596))
    d.rounded_rectangle([20, 962, 720, 986], radius=10, fill=(55, 65, 81))

    # phone with the Google Sheet
    d.rounded_rectangle([735, 600, 950, 1110], radius=34, fill=(17, 24, 39))
    im.paste(_screen(phone_png, 191, 484, phone_sample, font(20)), (747, 614))

    # three features that the workbook really has
    fy = 1130
    for text in (badges or BADGES.get(module, BADGES["bundle"]))[:3]:
        d.ellipse([70, fy, 140, fy + 70], outline=acc, width=5)
        d.line([(88, fy + 36), (100, fy + 49), (124, fy + 22)], fill=acc, width=6)
        bf = fit_font(d, text, 770, 38, 26)
        d.text((166, fy + 14), text, font=bf, fill=(255, 255, 255))
        fy += 80

    # call to action
    cta_text = f"{cta or CTA}  |  {PLATFORM_LINE}"
    cf = fit_font(d, cta_text, 840, 44, 26)
    cy0, cy1 = 1390, 1458
    d.rounded_rectangle([60, cy0, 940, cy1], radius=34, fill=acc)
    cw = d.textlength(cta_text, font=cf)
    d.text(((W - cw) / 2, cy0 + (cy1 - cy0 - cf.size) / 2 - 4), cta_text, font=cf, fill=_text_on(acc))

    # footer
    text_on_prim = _text_on(prim)
    d.text((60, 1474), f"For {trade_label}", font=font(22), fill=text_on_prim)
    if laptop_sample or phone_sample:
        note = FOOT_NOTE
        nf = font(20)
        d.text((W - 60 - d.textlength(note, font=nf), 1478), note, font=nf, fill=text_on_prim)

    out = io.BytesIO()
    im.save(out, "PNG")
    status = ("laptop: SAMPLE preview" if laptop_sample else "laptop: uploaded") + "; " + \
             ("phone: SAMPLE preview" if phone_sample else "phone: uploaded screenshot")
    return out.getvalue(), status
