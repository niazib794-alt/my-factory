"""Business Factory 5 - workbook builder (.xlsx for Google Sheets and Excel).

One file per product. Real formulas, no hard-coded results.
Coloured cells: the buyer types. Grey cells: automatic formulas, locked.
Each table holds 300 rows. Dashboards read the same rows.
No Streamlit code here, so this file can be tested on its own.
"""
import io
import re

import config

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.properties import PageSetupProperties

N_ROWS = 300
FIRST = 4                      # first data row (Excel numbering)
LAST = FIRST + N_ROWS - 1      # last data row (303)
FONT = "Arial"
YELLOW, BLUE, GREY = "FFF2CC", "E2E8F0", "F1F5F9"
NAVY, HEAD = "173B75", "1E3A8A"
SYMBOL = {"USD": "$", "CAD": "CA$", "GBP": "£", "EUR": "€", "AUD": "A$"}

START, SET = "START HERE", "Settings"
JOB, EXTRA, INV, DASH = "Job Costing", "Extra Work Log", "Invoice Tracker", "Dashboard"

PRODUCT_NAMES = {
    "job_costing": "Service Business Profit & Job Costing",
    "change_orders": "Contractor Extra Work Approval Tracker",
    "receivables": "Contractor Invoice & Payment Collection",
    "bundle": "All-in-One Master Contractor Bundle",
}
PRODUCT_SHEETS = {
    "job_costing": [JOB],
    "change_orders": [EXTRA],
    "receivables": [INV],
    "bundle": [JOB, EXTRA, INV],
}
KIND_NAME = {"text": "text", "date": "date", "money": "money", "num": "number", "pct": "percent",
             "c_money": "money, automatic", "c_pct": "percent, automatic",
             "c_int": "whole number, automatic", "c_text": "text, automatic"}

# kind -> (fill colour, number format, editable by the buyer)
KINDS = {
    "text": ("IN", "General", True),
    "date": ("IN", "yyyy-mm-dd", True),
    "money": ("IN", "MONEY", True),
    "num": ("IN", "0.00", True),
    "pct": ("IN", "0.0%", True),
    "c_money": ("CALC", "MONEY", False),
    "c_pct": ("CALC", "0.0%", False),
    "c_int": ("CALC", "0", False),
    "c_text": ("CALC", "General", False),
}

# Each column: (header, kind, width, formula or None, dropdown list or None). {r} = Excel row number.
COLUMNS = {
    JOB: [
        ("Job ID", "text", 11, None, None),
        ("Client / Job (required)", "text", 24, None, None),
        ("Job date", "date", 13, None, None),
        ("Quote / revenue", "money", 15, None, None),
        ("Labor hours", "num", 11, None, None),
        ("Labor rate per hour", "money", 14, None, None),
        ("Labor cost", "c_money", 14, '=IF(B{r}="","",E{r}*F{r})', None),
        ("Materials", "money", 14, None, None),
        ("Subcontractors", "money", 15, None, None),
        ("Other direct cost", "money", 15, None, None),
        ("Direct cost", "c_money", 14, '=IF(B{r}="","",G{r}+H{r}+I{r}+J{r})', None),
        ("Overhead % (blank = Settings)", "pct", 16, None, None),
        ("Overhead amount", "c_money", 15,
         '=IF(B{r}="","",IF(Settings!$B$4="Quote",D{r},K{r})*IF(L{r}="",Settings!$B$5,L{r}))', None),
        ("Total cost", "c_money", 14, '=IF(B{r}="","",K{r}+M{r})', None),
        ("Profit", "c_money", 14, '=IF(B{r}="","",D{r}-N{r})', None),
        ("Profit margin", "c_pct", 12, '=IF(B{r}="","",IF(D{r}=0,"",O{r}/D{r}))', None),
        ("Job status", "text", 14, None, ["Quoted", "Won", "In progress", "Done", "Paid", "Lost"]),
        ("Notes", "text", 30, None, None),
    ],
    EXTRA: [
        ("Change ID", "text", 11, None, None),
        ("Job / Client (required)", "text", 24, None, None),
        ("Date requested", "date", 13, None, None),
        ("Requested by", "text", 16, None, None),
        ("Extra work description", "text", 34, None, None),
        ("Reason / scope change", "text", 26, None, None),
        ("Labor hours", "num", 11, None, None),
        ("Labor rate per hour", "money", 14, None, None),
        ("Materials", "money", 14, None, None),
        ("Other cost", "money", 13, None, None),
        ("Markup %", "pct", 11, None, None),
        ("Proposed charge", "c_money", 15, '=IF(B{r}="","",(G{r}*H{r}+I{r}+J{r})*(1+K{r}))', None),
        ("Client decision", "text", 18, None, ["Waiting for client", "Approved", "Rejected", "Scope changed"]),
        ("Approved amount", "money", 15, None, None),
        ("Date approved", "date", 13, None, None),
        ("Billing", "text", 14, None, ["Not billed", "Billed"]),
        ("Notes", "text", 30, None, None),
    ],
    INV: [
        ("Invoice #", "text", 11, None, None),
        ("Client / Job (required)", "text", 24, None, None),
        ("Invoice date", "date", 13, None, None),
        ("Due date", "date", 13, None, None),
        ("Invoice amount (required)", "money", 15, None, None),
        ("Amount paid", "money", 14, None, None),
        ("Balance due", "c_money", 14, '=IF(OR(B{r}="",E{r}=""),"",E{r}-F{r})', None),
        ("Days past due", "c_int", 11, '=IF(OR(B{r}="",D{r}=""),"",IF(G{r}<=0,0,MAX(0,TODAY()-D{r})))', None),
        ("Aging", "c_text", 14,
         '=IF(B{r}="","",IF(E{r}="","Check amount",IF(G{r}<=0,"Paid",IF(H{r}="","No due date",IF(H{r}=0,"Not yet due",'
         'IF(H{r}<=30,"1-30 days",IF(H{r}<=60,"31-60 days",IF(H{r}<=90,"61-90 days","90+ days"))))))))', None),
        ("Status", "c_text", 13,
         '=IF(B{r}="","",IF(E{r}="","Check amount",IF(G{r}<=0,"Paid",IF(AND(ISNUMBER(H{r}),H{r}>0),"Overdue",'
         'IF(F{r}>0,"Partly paid","Open")))))', None),
        ("Last follow-up", "date", 14, None, None),
        ("Next follow-up", "date", 14, None, None),
        ("Contact method", "text", 14, None, ["Phone", "WhatsApp", "Email", "Visit", "Other"]),
        ("Reference / link", "text", 22, None, None),
        ("Notes", "text", 30, None, None),
    ],
}

HINTS = {
    JOB: "Yellow cells = type here. Grey cells = automatic. One row per job. Client / Job is required. "
         "Leave Overhead % blank to use the default in Settings.",
    EXTRA: "Yellow cells = type here. Grey cells = automatic. One row per extra-work request. Choose Approved only "
           "after the client agrees, then type the approved amount.",
    INV: "Yellow cells = type here. Grey cells = automatic. One row per invoice. Invoice amount is required. "
         "Status and aging update every day, using today's date.",
}

EXAMPLES = {
    JOB: ["Job ID J-001 | Client / Job: Kitchen sink repair | Quote: 350 | Labor: 3 h x 45 = 135 | "
          "Materials: 40 | Direct cost: 175 | Overhead: 12% of direct cost = 21 | Total cost: 196 | "
          "Profit: 154 | Margin: 44%"],
    EXTRA: ["Change ID C-001 | Job / Client: Kitchen sink repair | Extra work: replace shut-off valve | "
            "Labor: 1 h x 45 = 45 | Materials: 30 | Markup 20% | Proposed charge: (45 + 30) x 1.20 = 90 | "
            "Client decision: Approved | Approved amount: 90 | Billing: Not billed"],
    INV: ["Invoice # 1001 | Client / Job: Smith house | Invoice date: 2026-10-01 | Due date: 2026-10-31 | "
          "Invoice amount: 350 | Amount paid: 200 | Balance due: 150 | After the due date the status "
          "shows Overdue and the balance moves into the aging buckets on the Dashboard"],
}
EXAMPLE_NOTE = "Illustrative numbers only, not market prices. Type your own rows in the tabs, not here."

SIDE = Side(style="thin", color="CBD5E1")
BOX = Border(left=SIDE, right=SIDE, top=SIDE, bottom=SIDE)
RED_FILL = PatternFill(fill_type="solid", start_color="FEE2E2", end_color="FEE2E2")
RED_FONT = Font(name=FONT, color="991B1B", bold=True)
AMBER_FILL = PatternFill(fill_type="solid", start_color="FEF3C7", end_color="FEF3C7")
AMBER_FONT = Font(name=FONT, color="92400E")
MARKUP_FILL = PatternFill(fill_type="solid", start_color="FDBA74", end_color="FDBA74")
PROTECT_ON = True
VALIDATIONS_ON = True
CONDITIONAL_ON = True
OVERRIDE_TEXT = {}  # brain text: start lines and tab hints
BRAND_DEFAULT = config.BRAND_NAME
FORMULA_FILL = "E2E8F0"  # grey: automatic cells in every file
TRADES = {  # header colour (primary), accent, example job, pin palette wording
    "plumb_elec": {"label": "Plumbers & Electricians", "primary": "1E3A8A", "accent": "F59E0B",
                   "example": "Kitchen sink repair", "palette": "navy blue headers with amber gold accents"},
    "hvac": {"label": "HVAC & AC Repair Technicians", "primary": "0F766E", "accent": "475569",
             "example": "AC unit service call", "palette": "teal blue headers with cool grey accents"},
    "general": {"label": "General Contractors & Builders", "primary": "166534", "accent": "334155",
                "example": "Bathroom remodel, phase 1", "palette": "forest green headers with slate charcoal accents"},
    "roofing": {"label": "Roofing & Siding Contractors", "primary": "991B1B", "accent": "FEF3C7",
                "example": "Roof leak repair", "palette": "crimson red headers with warm cream accents"},
    "landscape": {"label": "Landscaping & Lawn Care Services", "primary": "047857", "accent": "4D7C0F",
                  "example": "Monthly lawn mowing add-on", "palette": "emerald green headers with earthy olive accents"},
    "painters": {"label": "Painters & Drywall Contractors", "primary": "3730A3", "accent": "E0F2FE",
                 "example": "Hallway repaint and patch", "palette": "royal indigo headers with soft sky blue accents"},
    "handyman": {"label": "Handyman & Home Repair Services", "primary": "C2410C", "accent": "F3F4F6",
                 "example": "Replace a door lock", "palette": "burnt orange headers with neutral sand accents"},
    "other": {"label": "Other trade (neutral)", "primary": "1F2937", "accent": "E5E7EB",
              "example": "Your own job", "palette": "charcoal headers with light grey accents"},
}
TRADE_LABELS = [v["label"] for v in TRADES.values()]
DEFAULT_STYLE = {"phone_font": 13, "phone_row": 30, "phone_min_width": 12, "phone_border": "D1D5DB"}
BORDER_CYCLE = ["D1D5DB", "CBD5E1", "B8C4D6", "9AA8BC"]
BRAND = BRAND_DEFAULT
TRADE = "plumb_elec"
LAYOUT_NOW = "laptop"
STYLE = dict(DEFAULT_STYLE)
PHONE_BORDER = Border(bottom=Side(style="thin", color=DEFAULT_STYLE["phone_border"]))
ACCENT_FILL, ACCENT_FONT = "F59E0B", "FFFFFF"
DASH_TAB = "F59E0B"
LAYOUTS = ("laptop", "phone")
LAYOUT_NOTE = {
    "laptop": "Laptop file: wider columns, more of the table on screen at once.",
    "phone": "Phone file: narrower columns and taller rows, easier to tap and scroll on a phone.",
}


def _box():
    return PHONE_BORDER if LAYOUT_NOW == "phone" else BOX


def _width(w, layout):
    return max(9, round(w * 0.8)) if layout == "phone" else w


def _font(bold=False, size=10, color="0F172A", italic=False):
    return Font(name=FONT, bold=bold, size=size, color=color, italic=italic)


def _fill(color):
    return PatternFill(fill_type="solid", start_color=color, end_color=color)


def _money(cur):
    return '"' + SYMBOL.get(cur, "$") + '"#,##0.00'


def _style(cell, kind, cur):
    fill, nf, editable = KINDS[kind]
    cell.fill = _fill(YELLOW if fill == "IN" else BLUE)
    cell.font = _font()
    cell.number_format = _money(cur) if nf == "MONEY" else nf
    cell.border = _box()
    cell.alignment = Alignment(vertical="center", wrap_text=(kind == "text"))
    cell.protection = Protection(locked=not editable)


def _rng(sheet, col):
    """Absolute range of one column over the table rows, for dashboard formulas."""
    return f"'{sheet}'!${col}${FIRST}:${col}${LAST}"


def _rules(name):
    if name == JOB:
        return [(f"O{FIRST}:O{LAST}",
                 CellIsRule(operator="lessThan", formula=["0"], fill=RED_FILL, font=RED_FONT))]
    if name == INV:
        return [(f"J{FIRST}:J{LAST}",
                 FormulaRule(formula=[f'$J{FIRST}="Overdue"'], fill=RED_FILL, font=RED_FONT))]
    if name == EXTRA:
        return [(f"N{FIRST}:N{LAST}",
                 FormulaRule(formula=[f'AND($M{FIRST}="Approved",$N{FIRST}="")'], fill=AMBER_FILL, font=AMBER_FONT)),
                (f"K{FIRST}:K{LAST}",
                 FormulaRule(formula=[f'AND($B{FIRST}<>"",$K{FIRST}="")'], fill=MARKUP_FILL))]
    return []


def _data_sheet(wb, name, cur, layout="laptop"):
    cols = COLUMNS[name]
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = LAYOUT_NOW != "phone"
    last = get_column_letter(len(cols))
    ws.merge_cells(f"A1:{last}1")
    ws["A1"] = f"{name.upper()} • ENTER DATA IN THE YELLOW CELLS"
    ws["A1"].font = _font(True, 14, "FFFFFF")
    ws["A1"].fill = _fill(NAVY)
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 30
    ws.merge_cells(f"A2:{last}2")
    ws["A2"] = OVERRIDE_TEXT.get("hints", {}).get(name, HINTS[name])
    ws["A2"].font = _font(False, 10, "334155", True)
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[2].height = 32
    for ci, spec in enumerate(cols, 1):
        h = ws.cell(row=3, column=ci, value=spec[0])
        h.font = _font(True, 10, "FFFFFF")
        h.fill = _fill(HEAD)
        h.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        h.border = _box()
        h.protection = Protection(locked=True)
        ws.column_dimensions[get_column_letter(ci)].width = (
            max(STYLE["phone_min_width"], _width(spec[2], layout), _word_width(spec[0]),
                16 if spec[1] == "date" else 0, 17 if spec[1] in ("money", "c_money") or spec[0] in ("Aging", "Status") else 0)
            if layout == "phone" else _width(spec[2], layout))
    ws.row_dimensions[3].height = 44
    if layout == "phone":
        for r in range(FIRST, LAST + 1):
            ws.row_dimensions[r].height = STYLE["phone_row"]
    for r in range(FIRST, LAST + 1):
        for ci, spec in enumerate(cols, 1):
            cell = ws.cell(row=r, column=ci)
            if spec[3]:
                cell.value = spec[3].format(r=r)
            _style(cell, spec[1], cur)
    for ci, spec in enumerate(cols, 1) if VALIDATIONS_ON else []:
        col = get_column_letter(ci)
        if spec[4]:
            dv = DataValidation(type="list", formula1='"' + ",".join(spec[4]) + '"', allow_blank=True)
            dv.error = "Choose a value from the list."
            dv.errorTitle = "Not in the list"
            ws.add_data_validation(dv)
            dv.add(f"{col}{FIRST}:{col}{LAST}")
        elif spec[1] == "money":
            dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
            dv.error = "Type an amount of 0 or more, for example 350 or 1250.50."
            dv.errorTitle = "Amount"
            dv.showErrorMessage = True
            ws.add_data_validation(dv)
            dv.add(f"{col}{FIRST}:{col}{LAST}")
        elif spec[1] == "date":
            dv = DataValidation(type="date", operator="between", formula1="36526", formula2="73050", allow_blank=True)
            dv.error = "Type a date, for example 2026-11-24."
            dv.errorTitle = "Date"
            dv.showErrorMessage = True
            ws.add_data_validation(dv)
            dv.add(f"{col}{FIRST}:{col}{LAST}")
        elif spec[1] == "pct":
            dv = DataValidation(type="decimal", operator="between", formula1="0", formula2="1", allow_blank=True)
            dv.error = "Type a percent between 0% and 100%, for example 12%."
            dv.errorTitle = "Percent out of range"
            dv.showErrorMessage = True
            ws.add_data_validation(dv)
            dv.add(f"{col}{FIRST}:{col}{LAST}")
    for rng, rule in (_rules(name) if CONDITIONAL_ON else []):
        ws.conditional_formatting.add(rng, rule)
    if layout == "phone":
        for r in range(FIRST, LAST + 1):
            for ci in range(1, len(cols) + 1):
                c = ws.cell(row=r, column=ci)
                c.font = _font(bool(c.font.b), STYLE["phone_font"], "0F172A", bool(c.font.i))
        for ci in range(1, len(cols) + 1):
            ws.cell(row=3, column=ci).font = _font(True, 11, "FFFFFF")
    ws.freeze_panes = f"{'B' if layout == 'phone' else 'C'}{FIRST}"
    ws.auto_filter.ref = f"A3:{last}{LAST}"
    ws.print_title_rows = "3:3"
    ws.page_setup.orientation = "landscape" if layout == "laptop" else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.protection.sheet = PROTECT_ON
    ws.protection.autoFilter = False
    ws.protection.formatColumns = False
    ws.protection.formatRows = False
    return ws


def _settings_sheet(wb, cur, business, module=""):
    ws = wb.create_sheet(SET)
    ws.merge_cells("A1:C1")
    ws["A1"] = f"SETTINGS • {BRAND} • change the yellow cells only"
    ws["A1"].font = _font(True, 14, "FFFFFF")
    ws["A1"].fill = _fill(NAVY)
    ws.row_dimensions[1].height = 30
    for ci, h in enumerate(["Setting", "Value", "What it does"], 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font = _font(True, 10, "FFFFFF")
        c.fill = _fill(HEAD)
        c.border = _box()
        c.alignment = Alignment(vertical="center", horizontal="center")
    rows = [  # row 4..8: the job-costing formulas read B4, B5 and B6
        ("Overhead method", "Direct cost", "text",
         "Direct cost: overhead % x direct cost. Quote: overhead % x quote price. Choose the method you use."),
        ("Default overhead %", 0.12, "pct",
         "Used when a job's overhead % is left blank. 12% is only an example. Set your own number."),
        ("Target profit margin", 0.30, "pct",
         "The Dashboard counts jobs below this margin. 30% is only an example. Set your own target."),
        ("Your business name", business, "text", "Shown on START HERE and in the Dashboard title."),
        ("Currency", cur, "c_text", "Set when this file was built. To change it, build the file again."),
        ("Trade", TRADES[TRADE]["label"], "text", "Your trade. Pick one from the list. It sets the header colours."),
    ]
    if module == "receivables":
        rows = [
            ("Follow-up reminder (days)", 7, "text",
             "Dashboard counts Next follow-up dates within this many days, and any that are already late."),
            ("Your business name", business, "text", "Shown on START HERE and in the Dashboard title."),
            ("Currency", cur, "c_text", "Set when this file was built. To change it, build the file again."),
            ("Trade", TRADES[TRADE]["label"], "text", "Your trade. Pick one from the list. It sets the header colours."),
        ]
    if module == "change_orders":
        rows = [(a, b_, c, "Not used in this workbook. It belongs to the Job Costing product.") if i < 3 else (a, b_, c, d)
                for i, (a, b_, c, d) in enumerate(rows)]
    for i, (label, value, kind, note) in enumerate(rows, 4):
        a = ws.cell(row=i, column=1, value=label)
        a.font = _font(True)
        a.border = _box()
        a.alignment = Alignment(vertical="center")
        b = ws.cell(row=i, column=2, value=value)
        _style(b, kind, cur)
        c = ws.cell(row=i, column=3, value=note)
        c.font = _font(False, 9, "475569", True)
        c.border = _box()
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[i].height = 30
    trade_row = 4 + [r_[0] for r_ in rows].index("Trade")
    if VALIDATIONS_ON:
        if module == "receivables":
            dvr = DataValidation(type="whole", operator="between", formula1="0", formula2="365", allow_blank=False)
            dvr.error = "Type a whole number of days from 0 to 365."
            dvr.errorTitle = "Reminder days"
            dvr.showErrorMessage = True
            ws.add_data_validation(dvr)
            dvr.add("B4")
        else:
            dv = DataValidation(type="list", formula1='"Direct cost,Quote"', allow_blank=False)
            ws.add_data_validation(dv)
            dv.add("B4")
        dvt = DataValidation(type="list", formula1='"' + ",".join(TRADE_LABELS) + '"', allow_blank=False)
        ws.add_data_validation(dvt)
        dvt.add(f"B{trade_row}")
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 72
    ws.protection.sheet = PROTECT_ON
    return ws


def dashboard_blocks(module):
    """List of (section title, [(label, formula, style kind, note), ...]) for the product."""
    blocks = []
    if module in ("job_costing", "bundle"):
        o, d, p = _rng(JOB, "O"), _rng(JOB, "D"), _rng(JOB, "P")
        blocks.append(("JOB COSTING", [
            ("Jobs entered", f"=COUNTA({_rng(JOB, 'B')})", "c_int", "Rows with a client or job name"),
            ("Total quoted revenue", f"=SUM({d})", "c_money", ""),
            ("Total direct cost", f"=SUM({_rng(JOB, 'K')})", "c_money", ""),
            ("Total cost incl. overhead", f"=SUM({_rng(JOB, 'N')})", "c_money", ""),
            ("Total profit", f"=SUM({o})", "c_money", ""),
            ("Overall profit margin", f'=IFERROR(SUM({o})/SUM({d}),"")', "c_pct", ""),
            ("Jobs with a loss", f'=COUNTIFS({o},"<0")', "c_int", "Look at these jobs first"),
            ("Jobs below target margin", f'=COUNTIFS({p},"<"&Settings!$B$6)', "c_int",
             "Target is set in Settings"),
        ]))
    if module in ("change_orders", "bundle"):
        m, n, l, bl = _rng(EXTRA, "M"), _rng(EXTRA, "N"), _rng(EXTRA, "L"), _rng(EXTRA, "P")
        b = _rng(EXTRA, "B")
        blocks.append(("EXTRA WORK", [
            ("Requests logged", f"=COUNTA({_rng(EXTRA, 'B')})", "c_int", ""),
            ("Waiting for client", f'=COUNTIFS({m},"Waiting for client",{b},"<>")', "c_int", "Follow up on these"),
            ("Total proposed charges", f"=SUM({l})", "c_money", ""),
            ("Approved amount", f'=SUMIFS({n},{m},"Approved",{b},"<>")', "c_money", ""),
            ("Approved, not billed yet", f'=SUMIFS({n},{m},"Approved",{bl},"<>Billed",{b},"<>")', "c_money",
             "Invoice these now"),
            ("Approved but no amount typed", f'=COUNTIFS({m},"Approved",{n},"",{b},"<>")', "c_int", "Should be 0"),
        ]))
    if module in ("receivables", "bundle"):
        g, e, f_, j = _rng(INV, "G"), _rng(INV, "E"), _rng(INV, "F"), _rng(INV, "J")
        i_, ll = _rng(INV, "I"), _rng(INV, "L")
        blocks.append(("INVOICES", [
            ("Invoices logged", f"=COUNTA({_rng(INV, 'B')})", "c_int", ""),
            ("Total invoiced", f"=SUM({e})", "c_money", ""),
            ("Total paid", f"=SUM({f_})", "c_money", ""),
            ("Outstanding balance", f'=SUMIF({g},">0")', "c_money", "Owed to you. Overpayments are shown below as credit."),
            ("Overdue balance", f'=SUMIFS({g},{j},"Overdue")', "c_money", ""),
            ("Overdue invoices", f'=COUNTIFS({j},"Overdue")', "c_int", ""),
            ("Aging: 1-30 days", f'=SUMIFS({g},{i_},"1-30 days")', "c_money", ""),
            ("Aging: 31-60 days", f'=SUMIFS({g},{i_},"31-60 days")', "c_money", ""),
            ("Aging: 61-90 days", f'=SUMIFS({g},{i_},"61-90 days")', "c_money", ""),
            ("Aging: 90+ days", f'=SUMIFS({g},{i_},"90+ days")', "c_money", ""),
            ("Aging: not yet due", f'=SUMIFS({g},{i_},"Not yet due")', "c_money", "Due date is today or later."),
            ("Aging: no due date", f'=SUMIFS({g},{i_},"No due date")', "c_money", "Invoices with no Due date typed."),
            ("Credit (paid more than invoiced)", f'=SUMIF({g},"<0")', "c_money", "Shown as a negative number. Not counted as owed."),
            (("Follow-ups due within reminder days or late", f'=COUNTIFS({ll},"<="&(TODAY()+Settings!$B$4),{g},">0")', "c_int",
              "Contact these clients today or this week.") if module == "receivables" else
             ("Follow-ups due now or late", f'=COUNTIFS({ll},"<="&TODAY(),{g},">0")', "c_int",
              "Contact these clients today.")),
        ]))
    return blocks


def _dashboard_sheet(wb, module, cur, business, layout="laptop"):
    ws = wb.create_sheet(DASH)
    ws.merge_cells("A1:C1")
    ws["A1"] = f'={BIZ_REF}&" • DASHBOARD • automatic, do not type here"'
    ws["A1"].font = _font(True, 13, "FFFFFF")
    ws["A1"].fill = _fill(NAVY)
    ws.row_dimensions[1].height = 30
    ws.column_dimensions["A"].width = _width(40, layout)
    ws.column_dimensions["B"].width = 26 if layout == "phone" else 22
    ws.column_dimensions["C"].width = 44
    row = 3
    for title, items in dashboard_blocks(module):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
        c = ws.cell(row=row, column=1, value=title)
        c.font = _font(True, 11, ACCENT_FONT)
        c.fill = _fill(ACCENT_FILL)
        row += 1
        for label, formula, kind, note in items:
            a = ws.cell(row=row, column=1, value=label)
            a.font = _font()
            a.border = _box()
            b = ws.cell(row=row, column=2, value=formula)
            _style(b, kind, cur)
            n = ws.cell(row=row, column=3, value=note)
            n.font = _font(False, 9, "475569", True)
            n.border = _box()
            row += 1
        row += 1
    if layout == "phone":
        for rr in range(3, row):
            for cc in (1, 2):
                cell = ws.cell(row=rr, column=cc)
                if cell.value is not None:
                    f0 = cell.font
                    colour = f0.color.rgb[-6:] if (f0.color is not None and isinstance(f0.color.rgb, str)) else "0F172A"
                    cell.font = _font(bool(f0.b), 14 if cc == 2 else 13, colour, bool(f0.i))
    if module in ("job_costing", "bundle"):
        from openpyxl.chart import BarChart, Reference
        chart = BarChart()
        chart.type = "col"
        chart.title = "Profit by job"
        chart.add_data(Reference(wb[JOB], min_col=15, min_row=3, max_row=LAST), titles_from_data=True)
        chart.set_categories(Reference(wb[JOB], min_col=1, min_row=FIRST, max_row=LAST))
        chart.height, chart.width = 8, 16
        ws.add_chart(chart, "E3")
    ws.protection.sheet = PROTECT_ON
    return ws


def _start_sheet(ws, module, cur, business, layout="laptop"):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 105
    rows = [
        ("title", f'={BIZ_REF}&" • START HERE"'),
        ("head", PRODUCT_NAMES[module]),
        ("text", f"Trade: {TRADES[TRADE]['label']}. Example job: {TRADES[TRADE]['example']}."),
        ("text", "Download this file, upload it to Google Drive, open it in Google Sheets (or Excel), "
                 "then make your own copy before you type."),
        ("head", "Colour guide"),
        ("in", "Yellow cell = type here."),
        ("calc", "Grey cell = automatic. Do not type in grey cells."),
        ("text", LAYOUT_NOTE[layout]),
        ("head", "Steps"),
        ("text", ("1. Open Settings and type your business name. It shows on START HERE and in the Dashboard title."
                  if module == "change_orders" else
                  "1. Open Settings. Check the yellow values: business name and follow-up reminder (days)."
                  if module == "receivables" else
                  "1. Open Settings. Check the yellow values: business name, overhead method, default "
                  "overhead % and target margin.")),
        ("text", "2. Type one row per item in the yellow cells. Client / Job is required on every row."),
        ("text", dash_tip(module)),
        ("head", "Limits and protection"),
        ("text", f"Each table holds {N_ROWS} rows. " + (
            "Formula cells are locked without a password, so they are hard to change by mistake. "
            "Google Sheets shows protection settings under the Data menu."
            if PROTECT_ON else
            "NO PROTECTION version: cells can be changed by mistake and formulas are not locked. "
            "Make your own copy before you type, and keep this copy for testing only.")),

        ("text", "This file organises your records. It is not legal, tax, bookkeeping or accounting advice. "
                 "Check currency and tax rules for your area."),
        ("head", "Example row"),
    ] + [("example", EXAMPLES[s][0]) for s in PRODUCT_SHEETS[module]] + [("example", EXAMPLE_NOTE)]
    rows = rows[:2] + [("text", s) for s in OVERRIDE_TEXT.get("start_lines", [])] + rows[2:]
    r = 1
    for kind, text in rows:
        cell = ws.cell(row=r, column=1, value=text)
        if kind == "title":
            cell.font = _font(True, 14, "FFFFFF")
            cell.fill = _fill(NAVY)
            ws.row_dimensions[r].height = 30
        elif kind == "head":
            cell.font = _font(True, 12, NAVY)
            ws.row_dimensions[r].height = 24
        elif kind == "in":
            cell.fill = _fill(YELLOW)
            cell.font = _font(True)
        elif kind == "calc":
            cell.fill = _fill(BLUE)
            cell.font = _font(True)
        elif kind == "example":
            cell.fill = _fill(GREY)
            cell.font = _font(False, 10, "334155", True)
        else:
            cell.font = _font(False, 10.5)
        if kind in ("text", "example"):
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            ws.row_dimensions[r].height = 16 * (len(text) // 95 + 1) + 6
        r += 1
    ws.protection.sheet = PROTECT_ON


INTERNAL_NOTE = re.compile(r"\d\s*pt\b|\bpt\b|font|row height|column width|refinement|file style|phone view uses", re.I)


BIZ_REF = "Settings!$B$7"


def build_workbook(module, currency="USD", business=None, layout="laptop", theme=None,
                   protect=True, validations=True, conditional=True, text=None,
                   trade="plumb_elec", style=None, brand=None):
    """Return the .xlsx file as bytes.

    layout: "laptop" or "phone". trade: a key of TRADES (header colours). style: from refine_style().
    text: brain text (start_lines, hints). protect / validations / conditional: off for the test variants.
    theme is accepted for old callers and ignored.
    """
    global PROTECT_ON, VALIDATIONS_ON, CONDITIONAL_ON, NAVY, HEAD, BRAND, TRADE, LAYOUT_NOW, STYLE, BIZ_REF
    global PHONE_BORDER, ACCENT_FILL, ACCENT_FONT, DASH_TAB, OVERRIDE_TEXT
    if module not in PRODUCT_SHEETS:
        raise ValueError(f"unknown product: {module}")
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    if trade not in TRADES:
        raise ValueError(f"unknown trade: {trade}")
    BRAND = brand or BRAND_DEFAULT
    BIZ_REF = "Settings!$B$5" if module == "receivables" else "Settings!$B$7"
    business = business or BRAND
    PROTECT_ON, VALIDATIONS_ON, CONDITIONAL_ON = bool(protect), bool(validations), bool(conditional)
    TRADE = trade
    t = TRADES[trade]
    NAVY = HEAD = t["primary"]
    ACCENT_FILL, ACCENT_FONT = accent_pair(trade)
    LAYOUT_NOW = layout
    STYLE = dict(DEFAULT_STYLE, **(style or {}))
    PHONE_BORDER = Border(bottom=Side(style="thin", color=STYLE["phone_border"]))
    DASH_TAB = t["accent"] if contrast(t["accent"], "FFFFFF") >= 3 else t["primary"]
    OVERRIDE_TEXT = dict(text or {})
    if "start_lines" in OVERRIDE_TEXT:
        OVERRIDE_TEXT["start_lines"] = [l for l in OVERRIDE_TEXT["start_lines"] if not INTERNAL_NOTE.search(str(l))]
    wb = Workbook()
    wb.properties.creator = BRAND
    wb.properties.title = PRODUCT_NAMES[module]
    start = wb.active
    start.title = START
    _start_sheet(start, module, currency, business, layout)
    _settings_sheet(wb, currency, business, module)
    for name in PRODUCT_SHEETS[module]:
        _data_sheet(wb, name, currency, layout)
    _dashboard_sheet(wb, module, currency, business, layout)
    wb[START].sheet_properties.tabColor = NAVY
    wb[SET].sheet_properties.tabColor = "64748B"
    for name in PRODUCT_SHEETS[module]:
        wb[name].sheet_properties.tabColor = HEAD
    wb[DASH].sheet_properties.tabColor = DASH_TAB
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def outline(module):
    """Tab name -> column headers, in order (used by the app preview)."""
    return {name: [c[0] for c in COLUMNS[name]] for name in PRODUCT_SHEETS[module]}


def spec_text(module, currency="USD", business="My Business"):
    """Plain-text specification generated from the same code that builds the file."""
    sym = SYMBOL.get(currency, "$")
    out = [f"SHEET SPECIFICATION • {PRODUCT_NAMES[module]}",
           f"Business: {business} | Trade: {TRADES[TRADE]['label']} | Currency: {currency} ({sym})", "",
           "Tabs, in order:",
           f"1. {START}: instructions, colour guide, example row (text only)",
           f"2. {SET}: overhead method (Direct cost or Quote), default overhead %, target profit margin, "
           "business name, currency"]
    n = 3
    for name in PRODUCT_SHEETS[module]:
        out.append(f"{n}. {name}: {N_ROWS} rows (Excel rows {FIRST} to {LAST}), column headers in row 3")
        n += 1
    out.append(f"{n}. {DASH}: automatic totals, locked")
    for name in PRODUCT_SHEETS[module]:
        out += ["", f"TAB {name}: columns"]
        for i, c in enumerate(COLUMNS[name], 1):
            letter = get_column_letter(i)
            if c[3]:
                out.append(f"  {letter}. {c[0]}: automatic ({KIND_NAME[c[1]]}, locked)")
            else:
                extra = f"; choose from: {', '.join(c[4])}" if c[4] else ""
                out.append(f"  {letter}. {c[0]}: type here ({KIND_NAME[c[1]]}){extra}")
    out += ["", f"TAB {DASH}: metrics"]
    for title, items in dashboard_blocks(module):
        out.append(f"  {title}")
        for label, _, _, note in items:
            out.append(f"    - {label}" + (f" ({note})" if note else ""))
    out += ["", "PROTECTION: formula cells are locked without a password. Yellow input cells stay editable.",
            "WARNINGS BUILT IN: loss jobs, jobs below target margin, overdue invoices, "
            "approved extra work with no amount."]
    return "\n".join(out)


# ---------------- checks and helpers (version 6)
def _lum(hex_):
    vals = []
    for i in (0, 2, 4):
        c = int(hex_[i:i + 2], 16) / 255
        vals.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def contrast(a, b):
    """WCAG contrast ratio between two hex colours."""
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return round((hi + 0.05) / (lo + 0.05), 2)


def accent_pair(trade):
    """Accent fill, and the text colour that reads on it (4.5:1 where the palette allows)."""
    t = TRADES[trade]
    acc, pri = t["accent"], t["primary"]
    if contrast(acc, "FFFFFF") >= 4.5:
        return acc, "FFFFFF"
    if contrast(pri, acc) >= 4.5:
        return acc, pri
    return acc, "0F172A"


def palette_problems(trade):
    """Checks on one trade palette. Returns (check, status, detail) rows."""
    t = TRADES[trade]
    out = []
    c = contrast(t["primary"], "FFFFFF")
    out.append(("Header text contrast", "PASS" if c >= 4.5 else "FIX",
                f"white on {t['primary']}: {c}:1 (needs 4.5:1)"))
    for label, other in (("input yellow", YELLOW), ("formula grey", FORMULA_FILL)):
        c = contrast(t["accent"], other)
        out.append((f"Accent vs {label}", "PASS" if c >= 1.15 else "WARNING",
                    f"{t['accent']} vs {other}: {c}:1" + ("" if c >= 1.15 else
                    " (too close: buyers may read the accent as an input cell)")))
    return out


FORBIDDEN_CLAIMS = ["overtime", "benefit", "union", "apprentice", "offline", "prevent", "avoid dispute",
                    "boost", "guarantee"]
REQUIRED_TERMS = {"approv": ["approv"], "invoice": ["invoice"], "aging": ["aging", "ageing"],
                  "margin": ["margin"], "profit": ["profit"], "labor": ["labor", "labour"]}


def start_text_problems(lines, headers, dashboard_labels=()):
    """START HERE must match the workbook: no unsupported claims, and every topic it names must exist."""
    haystack = [h.lower() for h in list(headers) + list(dashboard_labels) if h]
    probs = []
    for line in lines:
        low = str(line).lower()
        if INTERNAL_NOTE.search(str(line)):
            probs.append(f"internal note, not for the buyer: {str(line)[:70]}")
        for word in FORBIDDEN_CLAIMS:
            if word in low:
                probs.append(f"'{word}' is not in the workbook: {str(line)[:70]}")
        for key, terms in REQUIRED_TERMS.items():
            if key in low and not any(term in h for term in terms for h in haystack):
                probs.append(f"'{key}' is named but no column or Dashboard item covers it: {str(line)[:70]}")
    return probs[:12]


def refine_style(prev=None):
    """One small step from the previous file style. Never goes backwards, always changes something."""
    before = dict(DEFAULT_STYLE, **(prev or {}))
    p = dict(before)
    if p["phone_font"] < 14:
        p["phone_font"] += 1
    if p["phone_row"] < 34:
        p["phone_row"] += 2
    if p["phone_min_width"] < 14:
        p["phone_min_width"] += 1
    if p == before:
        i = BORDER_CYCLE.index(p["phone_border"]) if p["phone_border"] in BORDER_CYCLE else 0
        p["phone_border"] = BORDER_CYCLE[(i + 1) % len(BORDER_CYCLE)]
    changes = [f"{label}: {before[k]} -> {p[k]}" for k, label in (
        ("phone_font", "phone text size (pt)"), ("phone_row", "phone row height (pt)"),
        ("phone_min_width", "phone minimum column width"), ("phone_border", "phone separator colour"))
        if p[k] != before[k]]
    return p, changes


def mobile_report(xlsx_bytes):
    """Checks on a built file for phones: text size, row height, boxes, gridlines, protection."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    rows = []
    data_sheets = [n for n in wb.sheetnames if n not in (START, SET, DASH)]
    for name in data_sheets:
        ws = wb[name]
        rows.append((f"{name}: gridlines hidden", "PASS" if ws.sheet_view.showGridLines is False else "FIX",
                     str(ws.sheet_view.showGridLines)))
        rows.append((f"{name}: protected", "PASS" if ws.protection.sheet else "FIX", str(ws.protection.sheet)))
        inp = ws.cell(row=FIRST, column=1)
        rows.append((f"{name}: input text size", "PASS" if (inp.font.sz or 0) >= 13 else "FIX",
                     f"{inp.font.sz} pt"))
        rows.append((f"{name}: row height", "PASS" if (ws.row_dimensions[FIRST].height or 0) >= 28 else "FIX",
                     f"{ws.row_dimensions[FIRST].height} pt"))
        boxed, unlocked = 0, 0
        for r in range(FIRST, LAST + 1):
            for ci in range(1, ws.max_column + 1):
                c = ws.cell(row=r, column=ci)
                b = c.border
                if b and b.left and b.right and b.top and b.bottom and b.left.style and b.right.style:
                    boxed += 1
                if isinstance(c.value, str) and c.value.startswith("=") and c.protection.locked is False:
                    unlocked += 1
        rows.append((f"{name}: boxed cells", "PASS" if boxed == 0 else "WARNING", str(boxed)))
        rows.append((f"{name}: formulas locked", "PASS" if unlocked == 0 else "FIX", f"{unlocked} unlocked"))
    return rows


def _word_width(header):
    """Column width that keeps the longest word of a header on one line (phone, 11 pt bold)."""
    words = [w.strip("()%,./") for w in str(header).replace("/", " ").split()]
    longest = max((len(w) for w in words), default=0)
    return longest * 1.6 + 2


DASH_TIPS = {
    "job_costing": "losses and jobs below target margin",
    "change_orders": "approved work with no amount typed, and approved work not billed yet",
    "receivables": "overdue invoices and follow-ups due within your reminder days or late",
    "bundle": "losses, jobs below target margin, approved work with no amount, overdue invoices and follow-ups",
}


def dash_tip(module):
    """The Dashboard line in START HERE names only the warnings this product really has."""
    return f"3. Open Dashboard for totals and warnings ({DASH_TIPS[module]})."
