"""Business Factory 5 - the brains (version 8).

Twelve brains, one job each. They run in order and pass their output on.
- Brains 1 to 9 use AI. Each reply is checked by code. A rejected reply gets one retry with the reason.
  If it still fails, the brain uses a truthful template for its part and the pipeline keeps going.
  The template is always marked in the run, so the owner can see it.
- Brain 1 runs up to five research passes, one angle each, on different keys, then merges the evidence.
  Evidence labelled SOURCE must have a link; otherwise the label becomes GUESS.
- Brain 7 writes the listing for Payhip. A sanitizer removes any sentence that breaks the rules
  (no offline, no FREE, no internal notes, no unverified numbers, no unsupported features) and fills the
  required parts from the product's own facts. Listing wording never stops the pipeline.
- Brain 10 builds the phone file and checks it (code). Brain 11 is the critic and gate: code checks,
  with an optional AI critic whose notes are advisory. Brain 12 packages the files (code).
Nothing is approved without the owner.
"""
import difflib
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime

import config
import engine
import poster
import sheets

PRODUCT_TITLES = {
    "job_costing": "Service Business Profit & Job Costing",
    "change_orders": "Contractor Extra Work Approval Tracker",
    "receivables": "Contractor Invoice & Payment Collection",
    "bundle": "All-in-One Master Contractor Bundle",
}
PRODUCT_KEYWORD = {"job_costing": "job costing", "change_orders": "extra work", "receivables": "invoice",
                   "bundle": "bundle"}
CHANGE_TYPES = ["colour", "font", "layout", "feature", "ease_of_use", "complaint_fix", "content", "price_guidance"]
EVIDENCE_LABELS = ["SOURCE", "USER_INPUT", "GUESS", "UNKNOWN"]
BRAIN_NAMES = {
    1: "Research (up to 5 passes)", 2: "Gaps and complaints", 3: "Trade profile", 4: "Change plan",
    5: "Sheet text", 6: "Decision and price", 7: "Payhip listing", 8: "Buyer guide",
    9: "Pins and poster", 10: "Mobile and layout reviewer (code)", 11: "Critic and gate (code + AI advisory)",
    12: "Package (code)",
}
AI_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9]
RESEARCH_MIN, RESEARCH_MAX, RESEARCH_DEFAULT = 1, 5, 5
ANGLES = [
    ("buyer searches", "what contractors type when they look for this kind of spreadsheet, and the problems they describe", "searches"),
    ("existing products", "what similar trade spreadsheets offer, their common features and weaknesses (no prices unless a source gives them)", "products"),
    ("complaints and wishes", "complaints and wishes from people who buy or use trade spreadsheets", "complaints"),
    ("price and format evidence", "price ranges and file formats seen in sources, each with a link and a date", "price"),
    ("trend and season", "seasonal demand and recent changes for this trade, only if a source shows them; otherwise GUESS", "trend"),
]
RISKY = re.compile(r"\b(guarantee[sd]?|best[- ]?sellers?|cure[sd]?|diagnos\w*|medical|treat(?:s|ment)?|"
                   r"passive income|get rich|income guarantee)\b", re.I)
FREE_WORD = re.compile(r"\bfree\b", re.I)
UNSUPPORTED = re.compile(r"\b(overtime|benefits?|union|apprentice\w*|offline|prevent\w*|avoid disputes?|boost\w*)\b", re.I)
BANNED_LISTING = re.compile(r"\b(offline|free|guarantee[sd]?|passive income|get rich|best[- ]?sellers?|cure[sd]?|"
                            r"medical|gumroad|nurture|overtime|benefits?|union|apprentice\w*|prevent\w*|"
                            r"avoid disputes?|boost\w*|save \d+|\d+\s*(?:%|percent))\b", re.I)
PROPS = {
    "plumb_elec": "a plumber with a wrench", "hvac": "an HVAC technician with a gauge set",
    "general": "a general contractor with a clipboard", "roofing": "a roofer with a safety harness",
    "landscape": "a landscaper with pruning shears", "painters": "a painter with a paint roller",
    "handyman": "a handyman with a toolbox", "other": "a tradesperson with a toolbox",
}
SHARED = """You are one brain inside Business Factory 5. The system prepares one product: a spreadsheet workbook for trade businesses, sold on Payhip (a digital download).
Owner notes and feedback are simple Urdu. Buyer-facing text is simple English with short sentences, US spelling.
EVIDENCE: every claim is labelled SOURCE (with a link), USER_INPUT (pasted or uploaded by the owner), GUESS or UNKNOWN. Never invent numbers, prices, sales, reviews, ratings, competitor counts or trends. Never put a percentage or a money figure in buyer text unless the owner gave it.
Never promise sales, income or results. No legal, tax or accounting advice. Never copy competitor names, text or brands.
Never claim a feature the workbook does not have (for example overtime, benefits, union tracking, offline use, or preventing disputes). Never write internal notes (font sizes, row heights, refinements, file styles) in buyer text.
Return ONLY valid JSON in the exact shape asked for, with no other text."""

# ---------------- facts the workbook really has (used by the sanitizer and the templates)
FACTS = {
    "job_costing": {
        "title_options": ["Service Business Profit & Job Costing Workbook",
                          "Job Costing and Profit Tracker for Service Businesses",
                          "Labor, Materials and Overhead Job Costing Sheet"],
        "description": ("Track every service job in one workbook. Enter the labor hours, labor rate, materials, "
                        "subcontractors and other costs for each job. The workbook adds the overhead and shows the "
                        "profit and profit margin for every job. The Dashboard lists the jobs with a loss and the jobs "
                        "below your target margin. It is a Google Sheets and Excel (.xlsx) template with no macros. It "
                        "has a desktop layout for laptops and a phone layout with bigger text. You type your own numbers "
                        "and the totals update as you type. Use it as a tracking tool for your own business. It gives no "
                        "tax, accounting or legal advice."),
        "hook": "Know the cost and profit of every job, with the numbers updating as you type.",
        "how_to": ["Open the file in Google Sheets or Excel.",
                   "Open Settings and check the overhead method and target margin.",
                   "Type one row per job in the yellow cells, then open the Dashboard to see the totals and warnings."],
        "included": ["Job costing tab for labor, materials, subcontractors and other costs",
                     "Overhead and profit margin calculated for every job",
                     "Dashboard with totals and warnings", "Settings tab with overhead method and target margin",
                     "Buyer guide inside the file"],
        "not_included": ["Accounting or tax advice", "Payroll or invoicing",
                         "Automatic link to your bank or accounting software"],
        "requirements": ["A Google account, or Microsoft Excel", "Google Sheets or Excel that opens .xlsx files"],
        "tags": ["job costing", "contractor", "profit margin", "spreadsheet", "google sheets", "excel template",
                 "labor cost", "small business"],
        "faq": [("What file do I get?", "One Excel (.xlsx) workbook with a laptop layout and a phone layout."),
                ("Does it need macros?", "No. The workbook has no macros."),
                ("Do I need to type formulas?", "No. The formulas are already in place and locked."),
                ("Can I change the overhead?", "Yes. Set the overhead method and target margin in Settings."),
                ("Is it tax advice?", "No. It is a tracking tool only.")],
    },
    "change_orders": {
        "title_options": ["Contractor Extra Work Approval Tracker",
                          "Extra Work and Change Order Log for Contractors",
                          "Client Approval and Extra Work Sheet"],
        "description": ("Log every extra-work request in one workbook. For each request, enter the job, the date, who asked, "
                        "the labor hours and rate, the materials and other costs. Set your markup, and the workbook shows "
                        "the proposed charge. Record the client decision, so you can see which requests are approved, "
                        "pending or rejected. The Dashboard shows the approved work that has no amount typed and the "
                        "approved work not billed yet. It is a Google Sheets and Excel (.xlsx) template with no macros, "
                        "with a desktop layout and a phone layout. You type your own numbers. It gives no legal, tax or "
                        "accounting advice."),
        "hook": "Log each extra-work request and see its client decision, proposed charge and billing status in one place.",
        "how_to": ["Open the file in Google Sheets or Excel.",
                   "Open Settings and set your business name and currency.",
                   "Type one row per extra-work request in the yellow cells, then open the Dashboard to check approved work."],
        "included": ["Extra work log for each request", "Client decision list with pending, approved and rejected",
                     "Proposed charge with your markup", "Dashboard with approved work not billed yet",
                     "Buyer guide inside the file"],
        "not_included": ["Legal advice on contracts or change orders", "Payroll or invoicing",
                         "Automatic link to your accounting software"],
        "requirements": ["A Google account, or Microsoft Excel", "Google Sheets or Excel that opens .xlsx files"],
        "tags": ["extra work", "change order", "contractor", "client approval", "spreadsheet", "google sheets",
                 "excel template", "small business"],
        "faq": [("What file do I get?", "One Excel (.xlsx) workbook with a laptop layout and a phone layout."),
                ("Does it need macros?", "No. The workbook has no macros."),
                ("Can I use it on a phone?", "Yes. Open it in Google Sheets or Excel on your phone."),
                ("Is it legal advice?", "No. It is a tracking tool only."),
                ("Can I change the markup?", "Yes. Type the markup for each request.")],
    },
    "receivables": {
        "title_options": ["Contractor Invoice and Payment Collection Tracker",
                          "Invoice, Payment and Aging Tracker for Contractors",
                          "Follow-up Sheet for Contractor Invoices"],
        "description": ("Track every invoice and payment in one workbook. Enter each invoice, the amount, the payments "
                        "received and the due date. The workbook shows the balance, the payment status and the aging "
                        "buckets from 1-30 to 90+ days. The Dashboard lists the overdue invoices and the follow-ups due "
                        "now or late. It is a Google Sheets and Excel (.xlsx) template with no macros, with a desktop "
                        "layout and a phone layout. You type your own numbers. It gives no legal, tax or accounting advice."),
        "hook": "See every open balance, overdue invoice and follow-up in one workbook.",
        "how_to": ["Open the file in Google Sheets or Excel.",
                   "Open Settings and set your business name and currency.",
                   "Type one row per invoice in the yellow cells, then open the Dashboard to see overdue invoices and follow-ups."],
        "included": ["Invoice log with amount, payments and due date", "Balance and payment status for each invoice",
                     "Aging buckets from 1-30 to 90+ days", "Dashboard with overdue invoices and follow-ups",
                     "Buyer guide inside the file"],
        "not_included": ["Legal advice on debt collection", "Payment processing", "Automatic link to your bank"],
        "requirements": ["A Google account, or Microsoft Excel", "Google Sheets or Excel that opens .xlsx files"],
        "tags": ["invoice tracker", "payment tracking", "contractor", "aging report", "spreadsheet", "google sheets",
                 "excel template", "small business"],
        "faq": [("What file do I get?", "One Excel (.xlsx) workbook with a laptop layout and a phone layout."),
                ("Does it need macros?", "No. The workbook has no macros."),
                ("Does it send reminders?", "No. It shows the follow-ups; you send the reminders yourself."),
                ("Is it legal advice?", "No. It is a tracking tool only."),
                ("Can I track partial payments?", "Yes. Type each payment in its column.")],
    },
    "bundle": {
        "title_options": ["All-in-One Master Contractor Bundle: Job Costing, Extra Work and Invoices",
                          "Contractor Business Bundle in One Workbook",
                          "Job Costing, Extra Work and Payment Tracker Bundle"],
        "description": ("Three trade workbooks in one file: job costing and profit, extra-work approvals, and invoices "
                        "and payments. Each tab has the same clear layout, and the Dashboard shows the warnings from all "
                        "three parts. It is a Google Sheets and Excel (.xlsx) template with no macros, with a desktop "
                        "layout and a phone layout. You type your own numbers. It gives no legal, tax or accounting advice."),
        "hook": "Job costing, extra-work approvals and invoices in one workbook.",
        "how_to": ["Open the file in Google Sheets or Excel.",
                   "Open Settings and set your business name, currency and overhead method.",
                   "Type rows in the yellow cells of each tab, then open the Dashboard to see every total and warning."],
        "included": ["Job costing tab with overhead and profit", "Extra work log with client decisions",
                     "Invoice tracker with aging", "One Dashboard with the warnings from all three parts",
                     "Buyer guide inside the file"],
        "not_included": ["Legal, tax or accounting advice", "Payroll", "Automatic link to bank or accounting software"],
        "requirements": ["A Google account, or Microsoft Excel", "Google Sheets or Excel that opens .xlsx files"],
        "tags": ["contractor bundle", "job costing", "extra work", "invoice tracker", "spreadsheet", "google sheets",
                 "excel template", "small business"],
        "faq": [("What file do I get?", "One Excel (.xlsx) workbook with a laptop layout and a phone layout."),
                ("Does it need macros?", "No. The workbook has no macros."),
                ("Can I use only one tab?", "Yes. Each tab works on its own."),
                ("Is it legal advice?", "No. It is a tracking tool only."),
                ("Can I change the overhead?", "Yes. Set it in Settings.")],
    },
}
GUIDE_TEMPLATE = [
    ("What you get", "One Excel (.xlsx) workbook with a laptop layout and a phone layout. It opens in Google Sheets or Excel."),
    ("Before you start", "Open the file, then go to Settings and fill in the yellow cells."),
    ("First 10 minutes", "1. Open Settings. 2. Check the yellow values. 3. Type one row in the first data tab. 4. Open the Dashboard."),
    ("Colour guide", "Yellow cells: type here. Grey cells: automatic. Do not type in grey cells."),
    ("Each tab", "Type one row per item in the yellow cells of each data tab. The grey cells calculate on their own."),
    ("Common mistakes", "Leave the grey cells alone, and type percentages with the % sign, for example 12%."),
    ("Dashboard", "The Dashboard shows the totals and the warnings. Check it after each entry."),
    ("FAQ", "Does it need macros? No. Is it legal or tax advice? No. It is a tracking tool only."),
]
TRADE_TERMS = {"job": "job", "labour": "labor", "client": "client", "change": "extra work"}
STARTS_TEMPLATE = ["Welcome to your workbook.", "Type your own numbers in the yellow cells.",
                   "Grey cells are automatic. Do not type in them.",
                   "Formula cells are locked without a password, so only yellow cells change.",
                   "Open the Dashboard to see the totals and warnings."]
PRICE_TEMPLATE = [{"range": "USD 19 to 29", "purpose": "entry price ESTIMATE"},
                  {"range": "USD 29 to 39", "purpose": "standard price ESTIMATE"},
                  {"range": "USD 39 to 50", "purpose": "bundle price ESTIMATE"}]
HOW_TO_BRIEF = "Owner steps are in 14_how_to_upload.txt."


def _texts(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _texts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _texts(v)


CTX_DEFAULTS = {
    "market": "United States", "audience": "small contractors", "research_text": "", "source": "owner",
    "shot_note": "none", "images": [], "complaints": [], "prev": None, "prev_style": None, "recent": [],
    "results_text": "none", "owner_notes": "", "fix_notes": [], "grounding": False, "sources": [],
    "use_web": False, "tavily_key": "", "tavily_keys": [], "research_passes": RESEARCH_DEFAULT,
    "currency": "USD", "brand": config.BRAND_NAME, "style_changes": [], "notes": [], "log": [], "keys": [],
    "slots": [], "product": None, "product_fixed": False,
}


def normalize_ctx(ctx):
    """Fill every key the brains read, so a short context from the app cannot break a run.
    The owner's values always win; only missing keys are filled."""
    for k, v in CTX_DEFAULTS.items():
        if k not in ctx:
            ctx[k] = list(v) if isinstance(v, list) else (dict(v) if isinstance(v, dict) else v)
    ctx["trade"] = ctx.get("trade") or "plumb_elec"
    if ctx["trade"] not in sheets.TRADES:
        ctx["trade"] = "other"
    ctx.setdefault("trade_label", sheets.TRADES[ctx["trade"]]["label"])
    ctx.setdefault("business", ctx["brand"])
    if not ctx.get("style"):
        ctx["style"] = sheets.refine_style(None)[0]
    return ctx


def prev_description(ctx):
    """The last approved listing description, or '' when there is none or the shape is unexpected."""
    try:
        return ctx["prev"]["brains"]["7"]["data"]["description"]
    except Exception:
        return ""


def _safe(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(s)).strip("_")[:60] or "file"


def _claims(d):
    return any(RISKY.search(s) or FREE_WORD.search(s) or UNSUPPORTED.search(s) for s in _texts(d))


def _headers(product):
    tabs = sheets.PRODUCT_SHEETS[product]
    headers = [c[0] for t in tabs for c in sheets.COLUMNS[t]]
    labels = [it[0] for _, items in sheets.dashboard_blocks(product) for it in items]
    return tabs, headers, labels


def _ask(ctx, job, brain, role, user, check, images=(), rotate=0, grounding=False):
    system = SHARED + f"\n\nBRAIN {brain} - {BRAIN_NAMES[brain]}\n{role}"
    if ctx.get("fix_notes"):
        user += "\n\nCRITIC NOTES (fix every one; do not repeat the same problem):\n" + "\n".join(ctx["fix_notes"])
    if ctx.get("owner_notes"):
        user += f"\n\nOWNER NOTES (the owner wants this changed): {ctx['owner_notes']}"
    return engine.json_job(job, system, user, ctx["slots"], ctx["log"], ctx["keys"], check, images,
                           grounding=grounding, sources=ctx.get("sources") if grounding else None, rotate=rotate)


def _ok_text(s):
    s = str(s)
    return not (BANNED_LISTING.search(s) or sheets.INTERNAL_NOTE.search(s))


def _sentences(text):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", str(text)) if x.strip()]


def _uniq(seq):
    out, seen = [], set()
    for x in seq:
        k = str(x).strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(str(x).strip())
    return out


# ---------------- brain 1: research passes
ROLE1 = """TASK: one research pass for the angle given. Return evidence items.
Each item: {"id": "E1", "text": "one clear fact or observation", "label": "SOURCE | USER_INPUT | GUESS | UNKNOWN", "source": "a link, or 'owner', or ''", "date": "YYYY-MM-DD or ''"}.
A SOURCE item must have a link. If there is no research and no web result for this angle, you may add GUESS items about the trade only.
Shape: {"items": [4 to 12 items]}"""


def check_evidence(d):
    if not isinstance(d, dict) or not isinstance(d.get("items"), list) or not d["items"]:
        return ["items must be a non-empty list"]
    probs, ids = [], set()
    for it in d["items"]:
        if not isinstance(it, dict):
            probs.append("an item is not an object")
            continue
        if it.get("label") not in EVIDENCE_LABELS:
            probs.append(f"bad label {it.get('label')}")
        if not str(it.get("text", "")).strip():
            probs.append("an item has no text")
        if it.get("id") in ids:
            probs.append(f"duplicate id {it.get('id')}")
        ids.add(it.get("id"))
    return probs[:6]


def merge_evidence(items):
    """Join the passes, drop repeats, label SOURCE only with a link, and number E1, E2, ..."""
    seen, out = set(), []
    for it in items:
        text = str(it.get("text", "")).strip()
        key = re.sub(r"\W+", " ", text.lower()).strip()[:90]
        if not key or key in seen:
            continue
        seen.add(key)
        label = it.get("label")
        source = str(it.get("source", ""))
        if label == "SOURCE" and not source.startswith("http"):
            label = "GUESS"
        out.append({"id": f"E{len(out) + 1}", "text": text, "label": label, "source": source,
                    "date": it.get("date", ""), "angle": it.get("angle", "")})
    return out


def brain1(ctx):
    n = max(RESEARCH_MIN, min(RESEARCH_MAX, int(ctx.get("research_passes", RESEARCH_DEFAULT))))
    items, passes, slots_used, failed = [], [], [], []
    for i in range(n):
        angle, desc, qword = ANGLES[i]
        web_text, web_items = "", []
        if ctx.get("use_web") and (ctx.get("tavily_keys") or ctx.get("tavily_key")):
            tkeys = ctx.get("tavily_keys") or [ctx["tavily_key"]]
            query = f"{ctx['trade_label']} {qword} spreadsheet {ctx['market']}"
            for tk in tkeys:
                try:
                    web_items = []
                    web_text = engine.tavily(tk, query, web_items)
                    break
                except Exception as e:
                    ctx.setdefault("notes", []).append(f"web pass {i + 1}, one Tavily key failed: {engine.scrub(e, ctx['keys'])}")
        user = (f"PASS {i + 1} of {n}, ANGLE: {angle}. {desc}\nTRADE: {ctx['trade_label']}\n"
                f"MARKET: {ctx['market']}\nAUDIENCE: {ctx['audience']}\n"
                f"SOURCE OF PASTED RESEARCH: {ctx['source'] or 'owner'}\n\n"
                f"PASTED RESEARCH (owner input):\n{ctx['research_text'].strip()[:12000] or 'none'}\n\n"
                f"WEB RESULTS FOR THIS ANGLE:\n{web_text[:8000] or 'none'}\n\n"
                f"SCREENSHOT NOTES: {ctx['shot_note']}")
        try:
            data, slot = _ask(ctx, "Research", 1, ROLE1, user, check_evidence,
                              ctx["images"] if i == 0 else (), rotate=i, grounding=bool(ctx.get("grounding")))
        except Exception as e:
            failed.append(f"pass {i + 1} ({angle}): {engine.scrub(e, ctx['keys'])[:120]}")
            continue
        for it in data["items"]:
            items.append(dict(it, angle=angle))
        passes.append({"angle": angle, "items": len(data["items"]), "web": len(web_items), "slot": slot})
        slots_used.append(slot)
    merged = merge_evidence(items)
    if not merged:
        merged = merge_evidence([{"text": b, "label": "GUESS", "source": "", "angle": "product features"}
                                 for b in FACTS[ctx["product"] or "job_costing"]["hook"].split(". ")] +
                                [{"text": f, "label": "GUESS", "source": "", "angle": "product features"}
                                 for f in FACTS[ctx["product"] or "job_costing"]["included"]])
        slot = "template (no pass answered)"
    else:
        slot = " + ".join(dict.fromkeys(slots_used))
    return {"items": merged, "passes": passes, "requested": n, "failed": failed}, slot


# ---------------- brain 2: gaps and complaints
ROLE2 = """TASK: find the market gaps and the buyer complaints this product can solve.
Use only the EVIDENCE items (name their ids) and the complaints. A gap with no evidence id must have "guess": true.
Shape: {"gaps": [{"gap": "...", "evidence_ids": ["E1"], "guess": false, "complaint": false}], "complaints_used": ["..."], "no_gap_reason": ""}
If no gap can be shown, give an empty gaps list and write the reason in no_gap_reason."""


def check_gaps(d, ids):
    if not isinstance(d, dict) or not isinstance(d.get("gaps"), list):
        return ["gaps must be a list"]
    probs = []
    if not d["gaps"] and not str(d.get("no_gap_reason", "")).strip():
        probs.append("give gaps, or write the reason in no_gap_reason")
    for g in d["gaps"]:
        if not isinstance(g, dict) or not str(g.get("gap", "")).strip():
            probs.append("a gap has no text")
            continue
        bad = [e for e in g.get("evidence_ids", []) if e not in ids]
        if bad:
            probs.append(f"unknown evidence id {bad[0]}")
        if not g.get("evidence_ids") and not g.get("guess"):
            probs.append("a gap without evidence must have guess: true")
    return probs[:6]


def brain2(ctx):
    ev = ctx["out"]["1"]["items"]
    ids = {i["id"] for i in ev}
    user = ("EVIDENCE (merged from all research passes):\n" +
            "\n".join(f"{i['id']} [{i['label']}] ({i.get('angle', '')}) {i['text']} | {i.get('source', '')}" for i in ev) +
            "\n\nBUYER COMPLAINTS (owner input):\n" + ("\n".join(f"- {c}" for c in ctx["complaints"]) or "none"))
    return _ask(ctx, "Research", 2, ROLE2, user, lambda d: check_gaps(d, ids))


# ---------------- brain 3: trade profile
ROLE3 = """TASK: write the wording for the trade {label}, using the words a real {label} uses on site.
Shape: {"example_rows": ["3 short example job rows, one sentence each"], "terms": {"job": "...", "labour": "...", "client": "...", "change": "..."}, "pin_hook": "one line, 90 characters or fewer"}
Plain English. No brands. No claims about results or features."""


def check_trade(d):
    if not isinstance(d, dict):
        return ["the reply is not an object"]
    probs = []
    rows = d.get("example_rows")
    if not isinstance(rows, list) or len(rows) != 3:
        probs.append("example_rows must have exactly 3 items")
    terms = d.get("terms") if isinstance(d.get("terms"), dict) else {}
    for k in ("job", "labour", "client", "change"):
        if not str(terms.get(k, "")).strip():
            probs.append(f"terms.{k} is empty")
    if len(str(d.get("pin_hook", ""))) > 90:
        probs.append("pin_hook must be 90 characters or fewer")
    if _claims(d):
        probs.append("remove risky, FREE or unsupported wording")
    return probs[:6]


def brain3(ctx):
    role = ROLE3.replace("{label}", ctx["trade_label"])
    user = f"TRADE: {ctx['trade_label']}\nAUDIENCE: {ctx['audience']}\nMARKET: {ctx['market']}\nBUSINESS NAME: {ctx['brand']}"
    return _ask(ctx, "Research", 3, role, user, check_trade)


def fallback_trade(ctx):
    t = sheets.TRADES.get(ctx["trade"], sheets.TRADES["other"])
    return {"example_rows": [f"{t['example']}, one visit.", f"{t['example']} with one extra part.",
                             f"{t['example']} that needs a second visit."],
            "terms": dict(TRADE_TERMS), "pin_hook": f"Track every {ctx['trade_label'].split(' & ')[0].lower()} job in one workbook."}


# ---------------- brain 4: change plan
ROLE4 = """TASK: choose the product to make today and plan what is different from the last approved version.
Product keys: job_costing, change_orders, receivables, bundle. If the owner fixed the product, use it.
Change types allowed: colour, font, layout, feature, ease_of_use, complaint_fix, content, price_guidance.
The trade palette is fixed by the trade, so do not plan a new header colour.
Plan at least TWO different change types. With buyer complaints, one change must be complaint_fix.
If REQUIRED LAYOUT REFINEMENT is given, one change must be of type layout and must describe those refinements.
If RESULTS OF PAST VERSIONS are given, do not simply repeat a product or change that got no sales after 100 views; say what the results taught in results_considered.
Shape: {"product": "job_costing", "summary": "one sentence", "results_considered": "what past results showed, or empty", "changes": [{"type": "layout", "what": "...", "why": "...", "evidence_ids": ["E1"]}]}"""


def check_plan(d, ctx):
    if not isinstance(d, dict):
        return ["the reply is not an object"]
    probs = []
    if d.get("product") not in PRODUCT_TITLES:
        probs.append("product must be job_costing, change_orders, receivables or bundle")
    if ctx["product_fixed"] and d.get("product") != ctx["product"]:
        probs.append(f"the owner fixed the product to {ctx['product']}")
    changes = d.get("changes")
    if not isinstance(changes, list) or not changes:
        return probs + ["changes must be a non-empty list"]
    types = {c.get("type") for c in changes if isinstance(c, dict)}
    if any(t not in CHANGE_TYPES for t in types):
        probs.append("a change type is not allowed")
    if len(types - {None}) < 2:
        probs.append("plan at least two different change types")
    if ctx["complaints"] and "complaint_fix" not in types:
        probs.append("with buyer complaints, one change must be complaint_fix")
    if ctx.get("style_changes") and "layout" not in types:
        probs.append("include a layout change that describes the style refinements")
    if not str(d.get("summary", "")).strip():
        probs.append("summary is empty")
    if ctx.get("results_text", "none") != "none" and not str(d.get("results_considered", "")).strip():
        probs.append("results exist: say in results_considered what they showed")
    return probs[:6]


def brain4(ctx):
    user = (f"PRODUCT FIXED BY OWNER: {ctx['product'] if ctx['product_fixed'] else 'no, the brain chooses'}\n"
            f"GAPS:\n{json.dumps(ctx['out']['2'], ensure_ascii=False)[:6000]}\n\n"
            f"TRADE PROFILE:\n{json.dumps(ctx['out']['3'], ensure_ascii=False)[:2000]}\n\n"
            f"BUYER COMPLAINTS:\n{chr(10).join('- ' + c for c in ctx['complaints']) or 'none'}\n\n"
            f"LAST APPROVED VERSION: {ctx['prev']['summary'] if ctx.get('prev') else 'none (first version)'}\n\n"
            f"REQUIRED LAYOUT REFINEMENT: {'; '.join(ctx.get('style_changes', [])) or 'none'}\n\n"
            "RECENT DAYS (avoid repeating):\n" + ("\n".join(
                f"- {r.get('date', '')}: {r.get('product', '')}, changes {', '.join(r.get('types', []))}"
                for r in ctx.get("recent", [])) or "none") + "\n\n"
            f"RESULTS OF PAST VERSIONS (owner's own numbers):\n{ctx.get('results_text', 'none')}")
    return _ask(ctx, "Decide", 4, ROLE4, user, lambda d: check_plan(d, ctx))


def fallback_plan(ctx):
    product = ctx["product"] or "job_costing"
    changes = [{"type": "layout", "what": "Phone layout: " + ("; ".join(ctx.get("style_changes", [])) or "kept"),
                "why": "Easier to read on a phone", "evidence_ids": []},
               {"type": "content", "what": "Listing rewritten for Payhip with the workbook's real features",
                "why": "Accurate buyer text", "evidence_ids": []}]
    if ctx["complaints"]:
        changes.append({"type": "complaint_fix", "what": "Clearer steps for the first entry",
                        "why": "Buyer complaint: " + ctx["complaints"][0][:80], "evidence_ids": []})
    return {"product": product, "summary": "Phone layout refinement and a clearer Payhip listing",
            "results_considered": "" if ctx.get("results_text", "none") == "none" else "Results were read by the owner",
            "changes": changes}


# ---------------- brain 5: sheet text (checked against the real columns)
ROLE5 = """TASK: write the text that goes into the workbook: start lines for the START HERE tab, and one hint for each data tab.
Name only columns and tabs that exist in the list you are given. Never mention file styles, font sizes, row heights, pt, refinements or internal notes; the buyer only needs to know how to use the sheet.
Shape: {"start_lines": ["3 to 10 short English lines"], "hints": {"Tab name": "one short English line"}} with one hint for every tab listed."""


def check_text(d, tabs):
    if not isinstance(d, dict):
        return ["the reply is not an object"]
    probs = []
    if not isinstance(d.get("start_lines"), list) or not (3 <= len(d["start_lines"]) <= 10):
        probs.append("start_lines must have 3 to 10 lines")
    hints = d.get("hints") if isinstance(d.get("hints"), dict) else {}
    missing = [t for t in tabs if not str(hints.get(t, "")).strip()]
    if missing:
        probs.append(f"missing hint for {missing[0]}")
    if any(sheets.INTERNAL_NOTE.search(str(s)) for s in _texts(d)):
        probs.append("remove internal notes (font, row height, refinement) from START HERE")
    if any(len(s) > 220 for s in _texts(d)):
        probs.append("a line is longer than 220 characters")
    if _claims(d):
        probs.append("remove risky, FREE or unsupported wording")
    return probs[:6]


def brain5(ctx):
    plan = ctx["out"]["4"]
    tabs, headers, labels = _headers(plan["product"])

    def check(d):
        probs = check_text(d, tabs)
        if isinstance(d, dict) and isinstance(d.get("start_lines"), list):
            probs += sheets.start_text_problems([str(x) for x in d["start_lines"]], headers, labels)
        return probs[:8]

    user = (f"PLAN:\n{json.dumps(plan, ensure_ascii=False)[:4000]}\n\n"
            f"TABS (one hint each): {', '.join(tabs)}\n"
            f"COLUMNS (exact names): {', '.join(headers)}\n"
            f"DASHBOARD ITEMS: {', '.join(labels)}\n"
            f"TRADE TERMS: {json.dumps(ctx['out']['3'].get('terms', {}), ensure_ascii=False)}")
    return _ask(ctx, "Guide", 5, ROLE5, user, check)


def sanitize_start(d, product):
    """Keep only lines that are true for this workbook; fill up with the template when needed."""
    tabs, headers, labels = _headers(product)
    lines = [str(x).strip() for x in (d.get("start_lines") or []) if str(x).strip()]
    keep = []
    for line in lines:
        if sheets.INTERNAL_NOTE.search(line) or sheets.start_text_problems([line], headers, labels):
            continue
        keep.append(line)
    for t in STARTS_TEMPLATE:
        if len(keep) >= 3:
            break
        if t not in keep:
            keep.append(t)
    hints = {t: str((d.get("hints") or {}).get(t, "")).strip() for t in tabs}
    for t in tabs:
        if not hints[t] or sheets.INTERNAL_NOTE.search(hints[t]):
            hints[t] = "Type one row per item in the yellow cells."
    return {"start_lines": keep[:10], "hints": hints}


def fallback_text(ctx):
    plan = ctx["out"]["4"]
    return sanitize_start({"start_lines": [], "hints": {}}, plan["product"])


# ---------------- brain 6: decision and price
ROLE6 = """TASK: decide the next step for today's product and give a price test.
Price tests: three ranges in the given currency. Each purpose ends with the word ESTIMATE. Do not claim what the market pays.
Features: the five workbook features that matter most to this buyer, in order. Only features that exist in the workbook.
Risks: at least three. Test: what to record in 14 days, and go / no-go questions for the owner to answer.
Shape: {"verdict": "...", "buyer": "one sentence", "price_tests": [{"range": "...", "purpose": "... ESTIMATE"}] (exactly 3), "features": [5 strings], "risks": [3 or more strings], "test14": {"record": ["views", "saves", "clicks", "sales"], "go_no_go": ["question", "question"]}}"""


def check_decision(d):
    if not isinstance(d, dict):
        return ["the reply is not an object"]
    probs = []
    pt = d.get("price_tests")
    if not isinstance(pt, list) or len(pt) != 3:
        probs.append("price_tests must have exactly 3 items")
    if not isinstance(d.get("features"), list) or len(d.get("features", [])) != 5:
        probs.append("features must have exactly 5 items")
    if not isinstance(d.get("risks"), list) or len(d.get("risks", [])) < 3:
        probs.append("risks must have 3 or more items")
    if _claims(d):
        probs.append("remove risky, FREE or unsupported wording")
    return probs[:6]


def brain6(ctx):
    user = (f"PLAN:\n{json.dumps(ctx['out']['4'], ensure_ascii=False)[:4000]}\n\n"
            f"EVIDENCE:\n{json.dumps(ctx['out']['1'], ensure_ascii=False)[:8000]}\n\n"
            f"RESEARCH PASSES: {json.dumps(ctx['out']['1'].get('passes', []), ensure_ascii=False)}\n\n"
            f"CURRENCY: {ctx['currency']}")
    return _ask(ctx, "Decide", 6, ROLE6, user, check_decision)


def sanitize_decision(d):
    tests = []
    for i, t in enumerate(d.get("price_tests") or []):
        if isinstance(t, dict):
            purpose = str(t.get("purpose", "")).strip() or PRICE_TEMPLATE[min(i, 2)]["purpose"]
            if "ESTIMATE" not in purpose:
                purpose += " ESTIMATE"
            tests.append({"range": str(t.get("range", "")).strip() or PRICE_TEMPLATE[min(i, 2)]["range"],
                          "purpose": purpose})
    for t in PRICE_TEMPLATE:
        if len(tests) >= 3:
            break
        tests.append(dict(t))
    out = dict(d)
    out["price_tests"] = tests[:3]
    return out


def fallback_decision(ctx):
    return {"verdict": "Start with this product and read the 14-day test before changing anything.",
            "buyer": "Contractors who track jobs, extra work or invoices in a spreadsheet.",
            "price_tests": [dict(t) for t in PRICE_TEMPLATE],
            "features": FACTS.get(ctx["product"] or "job_costing", FACTS["job_costing"])["included"][:5],
            "risks": ["Few views in the first days", "Other templates on the market", "Buyers may not type their numbers"],
            "test14": {"record": ["views", "saves", "clicks", "sales"],
                       "go_no_go": ["Did clicks reach 10?", "Did a buyer ask a question?"]}}


# ---------------- brain 7: Payhip listing (validation sanitized, never blocks)
ROLE7 = """TASK: write the Payhip listing for today's product. Payhip is the store; the product is a digital download (.xlsx).
Include: 3 title options (product keyword first, 70 characters or fewer); a 2-line hook; a description of at least 300 characters that says in plain words what the workbook does; what is included (4 or more); 3 how-to steps; what it does NOT do (2 or more); requirements (2 or more, naming Google Sheets or Excel); 8 tags; 5 FAQ questions.
Rules: never use the words offline, free, gumroad or nurture. Never write a percentage or a money figure. Never mention internal notes, fonts, row heights or layout tuning. Do not claim a feature that is not in the list of included items.
Shape: {"titles": [3 strings], "hook": "...", "description": "...", "included": [4 or more], "how_to": [3], "not_included": [2 or more], "requirements": [2 or more], "tags": [8], "faq": [{"q": "...", "a": "..."}] (exactly 5)}"""


def sanitize_listing(d, product):
    """Keep every sentence that is true and allowed; fill any missing part from the product's own facts."""
    f = FACTS[product]
    kw = PRODUCT_KEYWORD[product]
    titles = [t for t in (d.get("titles") or []) if isinstance(t, str) and _ok_text(t)
              and len(t) <= 70 and kw in t.lower()]
    titles = _uniq(titles + f["title_options"])[:3]
    desc_parts = [s for s in _sentences(d.get("description", "")) if _ok_text(s)]
    desc = " ".join(desc_parts)
    if len(desc) < 300:
        desc = f["description"]
    hook = str(d.get("hook", "")).strip()
    if not hook or not _ok_text(hook):
        hook = f["hook"]
    how = [s for s in (str(x).strip() for x in (d.get("how_to") or [])) if s and _ok_text(s)]
    for step in f["how_to"]:
        if len(how) >= 3:
            break
        if step not in how:
            how.append(step)
    included = _uniq([s for s in (d.get("included") or []) if isinstance(s, str) and _ok_text(s)] + f["included"])[:8]
    not_inc = _uniq([s for s in (d.get("not_included") or []) if isinstance(s, str) and _ok_text(s)] + f["not_included"])[:6]
    req = _uniq([s for s in (d.get("requirements") or []) if isinstance(s, str) and _ok_text(s)] + f["requirements"])[:6]
    if not any("google sheets" in r.lower() or "excel" in r.lower() for r in req):
        req.insert(0, f["requirements"][1])
    tags = [t.strip().lower() for t in (d.get("tags") or []) if isinstance(t, str) and _ok_text(t) and len(t) <= 30]
    tags = _uniq(tags + f["tags"])[:8]
    faq = []
    for item in (d.get("faq") or []):
        if isinstance(item, dict) and _ok_text(item.get("q", "")) and _ok_text(item.get("a", "")):
            faq.append({"q": str(item["q"]).strip(), "a": str(item["a"]).strip()})
    for q, a in f["faq"]:
        if len(faq) >= 5:
            break
        if q not in [x["q"] for x in faq]:
            faq.append({"q": q, "a": a})
    return {"titles": titles, "hook": hook, "description": desc, "included": included, "how_to": how[:3],
            "not_included": not_inc, "requirements": req, "tags": tags, "faq": faq[:5], "platform": "Payhip"}


def brain7(ctx):
    plan = ctx["out"]["4"]
    _, headers, labels = _headers(plan["product"])
    user = (f"PRODUCT NAME (use this title family): {PRODUCT_TITLES[plan['product']]}\n"
            f"BRAND: {ctx['brand']}\nMARKET: {ctx['market']} (US spelling)\n"
            f"PLAN:\n{json.dumps(plan, ensure_ascii=False)[:3000]}\n\n"
            f"DECISION (ESTIMATE prices only):\n{json.dumps(ctx['out']['6'], ensure_ascii=False)[:2500]}\n\n"
            f"SHEET TEXT:\n{json.dumps(ctx['out']['5'], ensure_ascii=False)[:1500]}\n\n"
            f"COLUMNS (exact): {', '.join(headers)}\nDASHBOARD ITEMS (exact): {', '.join(labels)}\n\n"
            f"LAST VERSION DESCRIPTION (write a NEW description; do not copy it):\n"
            f"{prev_description(ctx)[:3000] or 'none'}")

    def check(d):
        if not isinstance(d, dict):
            return ["the reply is not an object"]
        return []  # the sanitizer below makes every reply valid; no retry loop
    return _ask(ctx, "Listing", 7, ROLE7, user, check)


def fallback_listing(ctx):
    return sanitize_listing({}, ctx["out"]["4"]["product"])


# ---------------- brain 8: buyer guide
ROLE8 = """TASK: write the buyer guide for a non-technical buyer who may use only a phone.
Use the SHEET TEXT and the tab list exactly. Never describe a tab, column or formula that is not in the list.
Sections: What you get; Before you start; First 10 minutes (numbered); Colour guide; Each tab, what to type; Common mistakes and fixes; Dashboard, what each number means; FAQ (5 questions).
Shape: {"sections": [{"title": "...", "text": "..."}] (at least 7 sections)}. Somewhere the text must say the file opens in Google Sheets or Excel. Never mention offline use."""


def sanitize_guide(d, product):
    _, headers, labels = _headers(product)
    secs = []
    for s in (d.get("sections") or []):
        if isinstance(s, dict) and _ok_text(s.get("title", "")) and _ok_text(s.get("text", "")):
            if not sheets.start_text_problems([str(s.get("text", ""))], headers, labels):
                secs.append({"title": str(s["title"]).strip(), "text": str(s["text"]).strip()})
    titles = [s["title"] for s in secs]
    for t, x in GUIDE_TEMPLATE:
        if len(secs) >= 7:
            break
        if t not in titles:
            secs.append({"title": t, "text": x})
    return {"sections": secs[:9]}


def brain8(ctx):
    plan = ctx["out"]["4"]
    _, headers, labels = _headers(plan["product"])
    user = (f"SHEET TEXT:\n{json.dumps(ctx['out']['5'], ensure_ascii=False)[:3000]}\n\n"
            f"COLUMNS (exact): {', '.join(headers)}\nDASHBOARD ITEMS (exact): {', '.join(labels)}\n\n"
            f"TITLE OPTIONS: {', '.join(ctx['out']['7']['titles'])}")
    return _ask(ctx, "Guide", 8, ROLE8, user, lambda d: [] if isinstance(d, dict) and d.get("sections") else ["sections missing"])


def fallback_guide(ctx):
    return sanitize_guide({}, ctx["out"]["4"]["product"])


# ---------------- brain 9: pins and poster
ROLE9 = """TASK: write 5 Pinterest pins for today's product. Text only. Use the trade's own words.
Each pin: headline (60 characters or fewer), text_on_image (8 words or fewer), description (2 sentences), board (a board name), cta (one call to action). No FREE, no promises, no percentages, no features the workbook does not have.
Shape: {"pins": [5 objects with headline, text_on_image, description, board, cta]}"""


def sanitize_pins(d, product, trade_label):
    pins = []
    for p in (d.get("pins") or []):
        if isinstance(p, dict) and all(_ok_text(p.get(k, "")) for k in ("headline", "text_on_image", "description")):
            if len(str(p.get("headline", ""))) <= 60 and len(str(p.get("text_on_image", "")).split()) <= 8:
                pins.append({k: str(p.get(k, "")).strip() for k in ("headline", "text_on_image", "description", "board", "cta")})
    tag = FACTS[product]["hook"]
    fallback = [{"headline": f"{trade_label}: {t}"[:60], "text_on_image": t[:60],
                 "description": f"{tag} Open the workbook on your laptop or phone.", "board": "Contractor tools",
                 "cta": "Get the workbook"} for t in FACTS[product]["included"][:5]]
    for fb in fallback:
        if len(pins) >= 5:
            break
        pins.append(fb)
    return {"pins": pins[:5]}


def brain9(ctx):
    t = sheets.TRADES[ctx["trade"]]
    user = (f"LISTING (sanitized):\n{json.dumps(ctx['out']['7'], ensure_ascii=False)[:5000]}\n\n"
            f"TRADE: {ctx['trade_label']}\nBRAND: {ctx['brand']}")
    data, slot = _ask(ctx, "Pins", 9, ROLE9, user, lambda d: [] if isinstance(d, dict) and d.get("pins") else ["pins missing"])
    data = sanitize_pins(data, ctx["out"]["4"]["product"], ctx["trade_label"])
    data["poster"] = {"headline": poster.HEADLINES.get(ctx["trade"], poster.HEADLINES["other"]),
                      "tagline": poster.TAGLINE.get(ctx["out"]["4"]["product"], ""),
                      "badges": poster.BADGES.get(ctx["out"]["4"]["product"], poster.BADGES["bundle"]),
                      "cta": poster.CTA}
    return data, slot


def fallback_pins(ctx):
    data = sanitize_pins({}, ctx["out"]["4"]["product"], ctx["trade_label"])
    data["poster"] = {"headline": poster.HEADLINES.get(ctx["trade"], poster.HEADLINES["other"]),
                      "tagline": poster.TAGLINE.get(ctx["out"]["4"]["product"], ""),
                      "badges": poster.BADGES.get(ctx["out"]["4"]["product"], poster.BADGES["bundle"]),
                      "cta": poster.CTA}
    return data


FALLBACK = {1: lambda c: brain1(c), 2: lambda c: ({"gaps": [], "complaints_used": [],
                                                    "no_gap_reason": "Not enough evidence to name a gap; the workbook's own features are used."}, "template"),
            3: fallback_trade, 4: fallback_plan, 5: fallback_text, 6: fallback_decision,
            7: fallback_listing, 8: fallback_guide, 9: fallback_pins}
BRAIN_FN = {1: brain1, 2: brain2, 3: brain3, 4: brain4, 5: brain5, 6: brain6, 7: brain7, 8: brain8, 9: brain9}


def _template_for(n, ctx):
    if n == 1:
        return brain1(dict(ctx, use_web=False, images=[]))
    if n == 2:
        return ({"gaps": [], "complaints_used": [], "no_gap_reason": "Not enough evidence to name a gap; the workbook's own features are used."}, "template")
    if n == 3:
        return (fallback_trade(ctx), "template")
    if n == 4:
        return (fallback_plan(ctx), "template")
    if n == 5:
        return (fallback_text(ctx), "template")
    if n == 6:
        return (fallback_decision(ctx), "template")
    if n == 7:
        return (fallback_listing(ctx), "template")
    if n == 8:
        return (fallback_guide(ctx), "template")
    if n == 9:
        return (fallback_pins(ctx), "template")
    raise ValueError(n)


# ---------------- brain 10: mobile and layout reviewer (code)
def mobile_check(ctx, state):
    """Build the phone file for this run and check it. Returns (rows, file bytes)."""
    ctx = normalize_ctx(ctx)
    out = {k: v["data"] for k, v in state["brains"].items()}
    text = {"start_lines": out["5"]["start_lines"], "hints": out["5"]["hints"]}
    blob = sheets.build_workbook(state["product"], ctx["currency"], ctx["business"], "phone",
                                 trade=ctx["trade"], style=state.get("style") or ctx["style"], text=text,
                                 brand=ctx["brand"])
    return sheets.mobile_report(blob), blob


# ---------------- brain 11: critic and gate
def brain11(ctx, state):
    """Code checks. Only a broken file or an empty evidence set blocks. Everything else is a warning."""
    out = ctx["out"]
    plan = out["4"]
    checks, fix, problems, block, warn = [], set(), [], False, []
    passes = out["1"].get("passes", [])
    evidence = out["1"].get("items", [])
    ok = bool(evidence)
    checks.append(("Evidence is present", "PASS" if ok else "BLOCK", f"{len(passes)} passes answered, {len(evidence)} items"))
    block = block or not ok
    if out["1"].get("failed"):
        warn.append(f"{len(out['1']['failed'])} research pass(es) did not answer and were skipped")
    types = {c["type"] for c in plan["changes"] if isinstance(c, dict)}
    ok = len(types) >= 2
    checks.append(("At least two change types", "PASS" if ok else "WARNING", ", ".join(sorted(types))))
    style_ok = ctx.get("style") != ctx.get("prev_style")
    checks.append(("Layout refinement applied", "PASS" if style_ok else "BLOCK",
                   "; ".join(ctx.get("style_changes", [])) or "no change"))
    block = block or not style_ok
    if ctx["complaints"]:
        ok = "complaint_fix" in types
        checks.append(("A complaint is answered", "PASS" if ok else "WARNING", "complaint_fix present" if ok else "missing"))
    listing = out["7"]
    bad = [s for s in _texts(listing) if BANNED_LISTING.search(s)]
    checks.append(("Listing has no banned words (offline, FREE, internal notes, numbers)", "PASS" if not bad else "BLOCK",
                   "clean" if not bad else bad[0][:60]))
    block = block or bool(bad)
    _, headers, labels = _headers(state["product"])
    sheet_probs = sheets.start_text_problems([str(x) for x in out["5"]["start_lines"]], headers, labels)
    checks.append(("START HERE matches the columns", "PASS" if not sheet_probs else "BLOCK",
                   sheet_probs[0] if sheet_probs else "every claim matches a column or Dashboard item"))
    block = block or bool(sheet_probs)
    listing_probs = sheets.start_text_problems(list(_texts(listing)), headers, labels)
    checks.append(("Listing matches the workbook", "PASS" if not listing_probs else "WARNING",
                   listing_probs[0] if listing_probs else "every topic is in the workbook"))
    if listing_probs:
        warn.append("listing wording needs a look")
    prev_desc = prev_description(ctx)
    if prev_desc:
        ratio = difflib.SequenceMatcher(None, prev_desc, listing["description"]).ratio()
        checks.append(("Listing is new, not a copy of the last version", "PASS" if ratio < 0.85 else "WARNING",
                       f"similarity {ratio:.2f} (limit 0.85)"))
    for name, status, detail in sheets.palette_problems(ctx["trade"]):
        checks.append((f"Palette: {name}", status, detail))
        if status == "FIX":
            block = True
    try:
        rows, _blob = mobile_check(ctx, state)
        bad_rows = [r for r in rows if r[1] == "FIX"]
        for name, status, detail in rows:
            if status != "PASS":
                checks.append((f"Phone: {name}", status, detail))
        checks.append(("Phone file checks", "PASS" if not bad_rows else "BLOCK",
                       f"{len(rows) - len(bad_rows)} of {len(rows)} passed"))
        block = block or bool(bad_rows)
    except Exception as e:
        checks.append(("Phone file checks", "BLOCK", "could not build: " + str(e)[:120]))
        block = True
    if any("Critic" in e.get("duties", []) for e in engine.ready_entries(ctx["slots"])):
        summary = {"plan": plan.get("summary", ""), "listing_description": listing["description"][:1500],
                   "sheet_hints": list(out["5"]["hints"].values())[:6]}
        try:
            crit, _slot = engine.json_job(
                "Critic", SHARED + "\n\nBRAIN 11 - Critic and gate\nTASK: read the summary and reply JSON: "
                '{"verdict": "PASS or FIX", "problems": ["..."]}. Look for claims without evidence, buyer promises, '
                "wording that does not match the plan, and anything a buyer could misread.",
                json.dumps(summary, ensure_ascii=False), ctx["slots"], ctx["log"], ctx["keys"],
                lambda d: [] if isinstance(d, dict) and d.get("verdict") in ("PASS", "FIX") else ["verdict must be PASS or FIX"])
            notes = [str(x) for x in crit.get("problems", [])][:5]
            checks.append(("AI critic (advisory)", "PASS" if crit["verdict"] == "PASS" else "WARNING",
                           "; ".join(notes) or "no concerns"))
        except Exception as e:
            checks.append(("AI critic (advisory)", "WARNING", "skipped: " + engine.scrub(e, ctx["keys"])[:120]))
    if any(s == "WARNING" for _, s, _ in checks):
        warn.append("some checks show warnings; read them before approving")
    verdict = "BLOCK" if block else ("FIX" if fix else "PASS")
    checks.append(("Overall gate", verdict, f"{len(checks)} checks, {len(warn)} warning(s)"))
    problems = problems + [w for w in warn]
    return {"verdict": verdict, "checks": checks, "fix_brains": sorted(fix), "problems": problems}


# ---------------- pipeline (never stops for wording; falls back and says so)
def new_state(product_key):
    return {"status": "idle", "product": product_key, "brains": {}, "slots": {}, "errors": [],
            "checks": [], "problems": [], "fix_round": 0, "product_fixed": product_key is not None,
            "started": datetime.now().strftime("%Y-%m-%d %H:%M")}


def run_pipeline(state, ctx, save, pins_on=True):
    ctx = normalize_ctx(ctx)
    state.setdefault("style", ctx["style"])
    state.setdefault("style_changes", list(ctx.get("style_changes", [])))
    b = state["brains"]
    state["pins_on"] = pins_on
    order = [n for n in AI_ORDER if pins_on or n != 9]
    state["status"] = "running"
    state["errors"] = state.get("errors", [])
    save(state)
    for n in order:
        if str(n) in b:
            continue
        ctx["out"] = {k: v["data"] for k, v in b.items()}
        try:
            data, slot = BRAIN_FN[n](ctx)
        except Exception as e:
            state["errors"].append({"brain": n, "name": BRAIN_NAMES[n], "msg": engine.scrub(e, ctx["keys"])[:300],
                                    "at": datetime.now().strftime("%H:%M:%S"), "used": "template"})
            try:
                data, slot = _template_for(n, ctx)
                slot = f"template (after error)"
            except Exception as e2:
                state["status"] = "error"
                state["errors"].append({"brain": n, "name": BRAIN_NAMES[n], "msg": "template failed: " + str(e2)[:200],
                                        "at": datetime.now().strftime("%H:%M:%S")})
                save(state)
                return "error"
        if n == 4:
            data = data
            state["product"] = data["product"]
        if n == 5:
            data = sanitize_start(data, state["product"])
        if n == 6:
            data = sanitize_decision(data)
        if n == 7:
            data = sanitize_listing(data, state["product"])
        if n == 8:
            data = sanitize_guide(data, state["product"])
        if n == 1:
            ctx["research_passes_done"] = len(data.get("passes", []))
        b[str(n)] = {"data": data, "slot": slot, "at": datetime.now().strftime("%H:%M:%S")}
        state["slots"][str(n)] = slot
        save(state)
    ctx["out"] = {k: v["data"] for k, v in b.items()}
    gate = brain11(ctx, state)
    state["checks"], state["problems"] = gate["checks"], gate["problems"]
    state["status"] = "waiting_approval" if gate["verdict"] != "BLOCK" else "blocked"
    save(state)
    return state["status"]


# ---------------- brain 12: package (code only)
DOCS = [
    ("01_research.json", "1", "Research (merged passes, with sources)"),
    ("02_gaps_and_complaints.json", "2", "Gaps and complaints"),
    ("03_trade_profile.json", "3", "Trade profile"),
    ("04_change_plan.json", "4", "Change plan: what is different from the last version, and why"),
    ("05_sheet_text.json", "5", "Sheet text (START HERE and tab hints)"),
    ("06_decision_and_price_test.json", "6", "Decision and price test (ESTIMATE ranges)"),
    ("07_payhip_listing.json", "7", "Payhip listing, FAQ and tags"),
    ("08_buyer_guide.json", "8", "Buyer guide"),
    ("09_pins.json", "9", "Pinterest pins"),
]
HOW_TO = """ادائیگی سے پہلے یہ مراحل کریں (صرف اپنے لیے)
1. ZIP کھولیں۔ لیپ ٹاپ فائل کمپیوٹر کے لیے، فون فائل فون کے لیے ہے۔
2. google_test فولڈر کی تین فائلیں گوگل ڈرائیو پر اپلوڈ کر کے Google Sheets میں کھولیں: full، plain، no_protection۔ جو ٹھیک کھلے وہی اصل فائل بنے گی۔
3. Payhip پر نیا ڈیجیٹل پروڈکٹ بنائیں، xlsx فائل اپلوڈ کریں، لسٹنگ (07) چسپاں کریں، قیمت فیصلے (06) کے مطابق اور ملک کی کرنسی کے ساتھ رکھیں۔
4. پوسٹر (12_pinterest_poster.png) اور پن (09) Pinterest پر خود پوسٹ کریں۔
5. گیٹ کی رپورٹ (12_quality_gate.txt) اور فون کی جانچ (11_mobile_check.txt) دیکھیں، پھر اپلوڈ کریں۔
کسی بھی پلیٹ فارم کے موجودہ قواعد اپلوڈ سے پہلے خود دیکھیں۔ یہ قانونی یا ٹیکس مشورہ نہیں۔
"""


def package_member(zip_bytes, name):
    """One file out of a saved package, or None."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            return z.read(name)
    except Exception:
        return None


def build_package(ctx, state, version_no):
    """Workbooks, Google test files, documents, the poster and checksums. Returns (zip bytes, manifest)."""
    ctx = normalize_ctx(ctx)
    out = {k: v["data"] for k, v in state["brains"].items()}
    prod = state["product"]
    text = {"start_lines": out["5"]["start_lines"], "hints": out["5"]["hints"]}
    cur, biz, brand, trade = ctx["currency"], ctx["business"], ctx["brand"], ctx["trade"]
    style = state.get("style") or ctx["style"]
    changes = state.get("style_changes") or ctx.get("style_changes", [])
    base = f"{_safe(biz)}_{prod}_v{version_no}"
    kw = dict(trade=trade, style=style, text=text, brand=brand)
    laptop_book = sheets.build_workbook(prod, cur, biz, "laptop", **kw)
    phone_book = sheets.build_workbook(prod, cur, biz, "phone", **kw)
    files = {
        f"{base}_laptop.xlsx": laptop_book,
        f"{base}_phone.xlsx": phone_book,
        f"google_test/{base}_full.xlsx": laptop_book,
        f"google_test/{base}_plain.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", protect=False,
                                                               validations=False, conditional=False, **kw),
        f"google_test/{base}_no_protection.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", protect=False, **kw),
    }
    for fname, n, title in DOCS:
        files[fname] = f"{title}\n\n" + json.dumps(out[n], ensure_ascii=False, indent=2)
    laptop_png = poster.screen_or_table(poster.add_sample_rows(laptop_book, prod, sheets), prod, "laptop")
    uploaded = ctx.get("phone_shot")
    phone_sample = not uploaded
    if uploaded:
        phone_png = uploaded
    else:
        phone_png = poster.screen_or_table(poster.add_sample_rows(phone_book, prod, sheets, layout="phone"), prod, "phone")
    pdata = out.get("9", {}).get("poster") or {}
    headline = pdata.get("headline") or poster.HEADLINES.get(trade, poster.HEADLINES["other"])
    png, status = poster.make_poster(trade, prod, ctx["trade_label"], brand,
                                     sheets.TRADES[trade]["primary"], sheets.TRADES[trade]["accent"],
                                     laptop_png, phone_png, laptop_sample=True, phone_sample=phone_sample,
                                     headline=headline, tagline=pdata.get("tagline"),
                                     badges=pdata.get("badges"), cta=pdata.get("cta"))
    files["12_pinterest_poster.png"] = png
    files["12b_poster_status.txt"] = (f"Headline: {headline}\nScreens: {status}\n"
                                      "Text is drawn by code. Screens are the real workbook; sample rows are marked SAMPLE.")
    rows, _ = mobile_check(ctx, state)
    files["11_mobile_check.txt"] = "\n".join(f"{n}: {s}. {d}" for n, s, d in rows)
    files["12_quality_gate.txt"] = "\n".join(f"{n}: {s}. {d}" for n, s, d in state["checks"])
    files["10_poster_brief.txt"] = f"Trade: {ctx['trade_label']}\nHeadline: {headline}\nBrand: {brand}\nPalette: {sheets.TRADES[trade]['palette']}"
    files["13_sheet_specification.txt"] = sheets.spec_text(prod, cur, biz)
    files["14_how_to_upload.txt"] = HOW_TO
    files["layout_refinement.txt"] = "\n".join(changes) or "no change"
    manifest = {name: hashlib.sha256(d if isinstance(d, bytes) else d.encode("utf-8")).hexdigest()
                for name, d in files.items()}
    files["MANIFEST.txt"] = "\n".join(f"{h}  {n}" for n, h in manifest.items())
    files["README.txt"] = ("Made with Business Factory 5 for " + brand + " (Payhip listing). Check every file yourself. "
                           "Read the current Payhip and Pinterest rules before you publish. Upload and post manually. "
                           "Not legal, tax or accounting advice.\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, bytes) else data.encode("utf-8"))
    return buf.getvalue(), manifest
