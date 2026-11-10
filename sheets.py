"""Business Factory 3 - workbook builder (.xlsx for Google Sheets and Excel).

One file per product. Real formulas, no hard-coded results.
Yellow cells: the buyer types. Blue cells: automatic formulas, locked.
Each table holds 300 rows. Dashboards read the same rows.
No Streamlit code here, so this file can be tested on its own.
"""
import io

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

N_ROWS = 300
FIRST = 4                      # first data row (Excel numbering)
LAST = FIRST + N_ROWS - 1      # last data row (303)
FONT = "Arial"
YELLOW, BLUE, GREY = "FFF2CC", "DBEAFE", "F1F5F9"
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
    "text": (YELLOW, "General", True),
    "date": (YELLOW, "yyyy-mm-dd", True),
    "money": (YELLOW, "MONEY", True),
    "num": (YELLOW, "0.00", True),
    "pct": (YELLOW, "0.0%", True),
    "c_money": (BLUE, "MONEY", False),
    "c_pct": (BLUE, "0.0%", False),
    "c_int": (BLUE, "0", False),
    "c_text": (BLUE, "General", False),
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
        ("Balance due", "c_money", 14, '=IF(B{r}="","",E{r}-F{r})', None),
        ("Days past due", "c_int", 11, '=IF(OR(B{r}="",D{r}=""),"",IF(G{r}<=0,0,MAX(0,TODAY()-D{r})))', None),
        ("Aging", "c_text", 14,
         '=IF(B{r}="","",IF(G{r}<=0,"Paid",IF(H{r}="","No due date",IF(H{r}=0,"Not yet due",'
         'IF(H{r}<=30,"1-30 days",IF(H{r}<=60,"31-60 days",IF(H{r}<=90,"61-90 days","90+ days")))))))', None),
        ("Status", "c_text", 13,
         '=IF(B{r}="","",IF(G{r}<=0,"Paid",IF(AND(ISNUMBER(H{r}),H{r}>0),"Overdue",'
         'IF(F{r}>0,"Partly paid","Open"))))', None),
        ("Last follow-up", "date", 14, None, None),
        ("Next follow-up", "date", 14, None, None),
        ("Contact method", "text", 14, None, ["Phone", "WhatsApp", "Email", "Visit", "Other"]),
        ("Reference / link", "text", 22, None, None),
        ("Notes", "text", 30, None, None),
    ],
}

HINTS = {
    JOB: "Yellow = type here. Blue = automatic. One row per job. Client / Job is required. "
         "Leave Overhead % blank to use the default in Settings.",
    EXTRA: "Yellow = type here. Blue = automatic. One row per extra-work request. Choose Approved only "
           "after the client agrees, then type the approved amount.",
    INV: "Yellow = type here. Blue = automatic. One row per invoice. Invoice amount is required. "
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
PROTECT_ON = True
VALIDATIONS_ON = True
CONDITIONAL_ON = True
OVERRIDE_TEXT = {}  # brain text: start lines and tab hints
THEMES = {  # (title colour, header colour). Only titles and headers change; the legend colours stay fixed.
    "blue": ("173B75", "1E3A8A"),
    "green": ("14532D", "166534"),
    "purple": ("4C1D95", "5B21B6"),
    "teal": ("134E4A", "0F766E"),
    "amber": ("78350F", "92400E"),
    "rose": ("881337", "9F1239"),
}
LAYOUTS = ("laptop", "phone")
LAYOUT_NOTE = {
    "laptop": "Laptop file: wider columns, more of the table on screen at once.",
    "phone": "Phone file: narrower columns and taller rows, easier to tap and scroll on a phone.",
}


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
    cell.fill = _fill(fill)
    cell.font = _font()
    cell.number_format = _money(cur) if nf == "MONEY" else nf
    cell.border = BOX
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
                 FormulaRule(formula=[f'AND($M{FIRST}="Approved",$N{FIRST}="")'], fill=AMBER_FILL, font=AMBER_FONT))]
    return []


def _data_sheet(wb, name, cur, layout="laptop"):
    cols = COLUMNS[name]
    ws = wb.create_sheet(name)
    last = get_column_letter(len(cols))
    ws.merge_cells(f"A1:{last}1")
    ws["A1"] = f"{name.upper()} • ENTER DATA IN YELLOW CELLS"
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
        h.border = BOX
        h.protection = Protection(locked=True)
        ws.column_dimensions[get_column_letter(ci)].width = _width(spec[2], layout)
    ws.row_dimensions[3].height = 44
    if layout == "phone":
        for r in range(FIRST, LAST + 1):
            ws.row_dimensions[r].height = 24
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
        elif spec[1] == "pct":
            dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
            dv.error = "Type a percent, for example 12%."
            ws.add_data_validation(dv)
            dv.add(f"{col}{FIRST}:{col}{LAST}")
    for rng, rule in (_rules(name) if CONDITIONAL_ON else []):
        ws.conditional_formatting.add(rng, rule)
    ws.freeze_panes = f"{'B' if layout == 'phone' else 'C'}{FIRST}"
    ws.auto_filter.ref = f"A3:{last}{LAST}"
    ws.protection.sheet = PROTECT_ON
    ws.protection.autoFilter = False
    ws.protection.formatColumns = False
    ws.protection.formatRows = False
    return ws


def _settings_sheet(wb, cur, business):
    ws = wb.create_sheet(SET)
    ws.merge_cells("A1:C1")
    ws["A1"] = "SETTINGS • change the yellow cells only"
    ws["A1"].font = _font(True, 14, "FFFFFF")
    ws["A1"].fill = _fill(NAVY)
    ws.row_dimensions[1].height = 30
    for ci, h in enumerate(["Setting", "Value", "What it does"], 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font = _font(True, 10, "FFFFFF")
        c.fill = _fill(HEAD)
        c.border = BOX
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
    ]
    for i, (label, value, kind, note) in enumerate(rows, 4):
        a = ws.cell(row=i, column=1, value=label)
        a.font = _font(True)
        a.border = BOX
        a.alignment = Alignment(vertical="center")
        b = ws.cell(row=i, column=2, value=value)
        _style(b, kind, cur)
        c = ws.cell(row=i, column=3, value=note)
        c.font = _font(False, 9, "475569", True)
        c.border = BOX
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[i].height = 30
    if VALIDATIONS_ON:
        dv = DataValidation(type="list", formula1='"Direct cost,Quote"', allow_blank=False)
        ws.add_data_validation(dv)
        dv.add("B4")
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
        blocks.append(("EXTRA WORK", [
            ("Requests logged", f"=COUNTA({_rng(EXTRA, 'B')})", "c_int", ""),
            ("Waiting for client", f'=COUNTIFS({m},"Waiting for client")', "c_int", "Follow up on these"),
            ("Total proposed charges", f"=SUM({l})", "c_money", ""),
            ("Approved amount", f'=SUMIFS({n},{m},"Approved")', "c_money", ""),
            ("Approved, not billed yet", f'=SUMIFS({n},{m},"Approved",{bl},"Not billed")', "c_money",
             "Invoice these now"),
            ("Approved but no amount typed", f'=COUNTIFS({m},"Approved",{n},"")', "c_int", "Should be 0"),
        ]))
    if module in ("receivables", "bundle"):
        g, e, f_, j = _rng(INV, "G"), _rng(INV, "E"), _rng(INV, "F"), _rng(INV, "J")
        i_, ll = _rng(INV, "I"), _rng(INV, "L")
        blocks.append(("INVOICES", [
            ("Invoices logged", f"=COUNTA({_rng(INV, 'B')})", "c_int", ""),
            ("Total invoiced", f"=SUM({e})", "c_money", ""),
            ("Total paid", f"=SUM({f_})", "c_money", ""),
            ("Outstanding balance", f"=SUM({g})", "c_money", ""),
            ("Overdue balance", f'=SUMIFS({g},{j},"Overdue")', "c_money", ""),
            ("Overdue invoices", f'=COUNTIFS({j},"Overdue")', "c_int", ""),
            ("Aging: 1-30 days", f'=SUMIFS({g},{i_},"1-30 days")', "c_money", ""),
            ("Aging: 31-60 days", f'=SUMIFS({g},{i_},"31-60 days")', "c_money", ""),
            ("Aging: 61-90 days", f'=SUMIFS({g},{i_},"61-90 days")', "c_money", ""),
            ("Aging: 90+ days", f'=SUMIFS({g},{i_},"90+ days")', "c_money", ""),
            ("Follow-ups due now or late", f'=COUNTIFS({ll},"<="&TODAY(),{g},">0")', "c_int",
             "Contact these clients today"),
        ]))
    return blocks


def _dashboard_sheet(wb, module, cur, business, layout="laptop"):
    ws = wb.create_sheet(DASH)
    ws.merge_cells("A1:C1")
    ws["A1"] = "DASHBOARD • automatic, do not type here"
    ws["A1"].font = _font(True, 13, "FFFFFF")
    ws["A1"].fill = _fill(NAVY)
    ws.row_dimensions[1].height = 30
    ws.column_dimensions["A"].width = _width(40, layout)
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 44
    row = 3
    for title, items in dashboard_blocks(module):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
        c = ws.cell(row=row, column=1, value=title)
        c.font = _font(True, 11, "FFFFFF")
        c.fill = _fill(HEAD)
        row += 1
        for label, formula, kind, note in items:
            a = ws.cell(row=row, column=1, value=label)
            a.font = _font()
            a.border = BOX
            b = ws.cell(row=row, column=2, value=formula)
            _style(b, kind, cur)
            n = ws.cell(row=row, column=3, value=note)
            n.font = _font(False, 9, "475569", True)
            n.border = BOX
            row += 1
        row += 1
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
        ("title", "START HERE"),
        ("head", PRODUCT_NAMES[module]),
        ("text", "Download this file, upload it to Google Drive, open it in Google Sheets (or Excel), "
                 "then make your own copy before you type."),
        ("head", "Colour guide"),
        ("in", "Yellow cell = type here."),
        ("calc", "Blue cell = automatic. Do not type in blue cells."),
        ("text", LAYOUT_NOTE[layout]),
        ("head", "Steps"),
        ("text", "1. Open Settings. Check the yellow values: business name, overhead method, default "
                 "overhead % and target margin."),
        ("text", "2. Type one row per item in the yellow cells. Client / Job is required on every row."),
        ("text", "3. Open Dashboard for totals and warnings (losses, overdue invoices, approved work "
                 "with no amount)."),
        ("head", "Limits and protection"),
        ("text", f"Each table holds {N_ROWS} rows. Formula cells are locked without a password, so they "
                 "are hard to change by mistake. Google Sheets shows protection settings under the Data menu."),
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


def build_workbook(module, currency="USD", business="My Business", layout="laptop",
                   theme="blue", protect=True, validations=True, conditional=True, text=None):
    """Return the .xlsx file as bytes.

    layout: "laptop" or "phone". theme: a key of THEMES (titles and headers only).
    protect, validations, conditional: switch off for the plain test variants.
    """
    global PROTECT_ON, VALIDATIONS_ON, CONDITIONAL_ON, NAVY, HEAD
    PROTECT_ON, VALIDATIONS_ON, CONDITIONAL_ON = bool(protect), bool(validations), bool(conditional)
    NAVY, HEAD = THEMES.get(theme, THEMES["blue"])
    global OVERRIDE_TEXT
    OVERRIDE_TEXT = dict(text or {})
    if module not in PRODUCT_SHEETS:
        raise ValueError(f"unknown product: {module}")
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    wb = Workbook()
    wb.properties.creator = business
    wb.properties.title = PRODUCT_NAMES[module]
    start = wb.active
    start.title = START
    _start_sheet(start, module, currency, business, layout)
    _settings_sheet(wb, currency, business)
    for name in PRODUCT_SHEETS[module]:
        _data_sheet(wb, name, currency, layout)
    _dashboard_sheet(wb, module, currency, business, layout)
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
           f"Business: {business} | Currency: {currency} ({sym})", "",
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
    out += ["", "PROTECTION: formula cells are locked without a password. Yellow cells stay editable.",
            "WARNINGS BUILT IN: loss jobs, jobs below target margin, overdue invoices, "
            "approved extra work with no amount."]
    return "\n".join(out)
