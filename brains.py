"""Business Factory 5 - the brains (version 6).

Twelve brains, one job each.
- Brains 1 to 9 use AI. Every reply is checked by code; a rejected reply gets one retry with the reason.
- Brain 1 runs up to five research passes, one angle each, on different free keys, then merges the evidence.
- Brain 10 builds the phone file and checks it for phones (code).
- Brain 11 is the critic and the gate: its checks are code, which the AI cannot override. An AI critic may
  add advisory notes, but it never blocks.
- Brain 12 packages the files with checksums (code).
A FIX sends the brains that need it back through the pipeline (at most two fix rounds). A BLOCK stops the run.
Nothing is approved without the owner.
"""
import difflib
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime

import engine
import sheets

PRODUCT_TITLES = {
    "job_costing": "Service Business Profit & Job Costing",
    "change_orders": "Contractor Extra Work Approval Tracker",
    "receivables": "Contractor Invoice & Payment Collection",
    "bundle": "All-in-One Master Contractor Bundle",
}
CHANGE_TYPES = ["colour", "font", "layout", "feature", "ease_of_use", "complaint_fix", "content", "price_guidance"]
EVIDENCE_LABELS = ["SOURCE", "USER_INPUT", "GUESS", "UNKNOWN"]
BRAIN_NAMES = {
    1: "Research (up to 5 passes)", 2: "Gaps and complaints", 3: "Trade profile", 4: "Change plan",
    5: "Sheet text", 6: "Decision and price", 7: "Gumroad listing", 8: "Buyer guide",
    9: "Pins and image brief", 10: "Mobile and layout reviewer (code)", 11: "Critic and gate (code + AI advisory)",
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
PROPS = {
    "plumb_elec": "a plumber with a wrench", "hvac": "an HVAC technician with a gauge set",
    "general": "a general contractor with a clipboard", "roofing": "a roofer with a safety harness",
    "landscape": "a landscaper with pruning shears", "painters": "a painter with a paint roller",
    "handyman": "a handyman with a toolbox", "other": "a tradesperson with a toolbox",
}
SHARED = """You are one brain inside Business Factory 5. The system prepares one product: a spreadsheet workbook for trade businesses, sold on Gumroad.
Owner notes and feedback are simple Urdu. Buyer-facing text is simple English with short sentences.
EVIDENCE: every claim is labelled SOURCE (with a link), USER_INPUT (pasted or uploaded by the owner), GUESS or UNKNOWN. Never invent numbers, prices, sales, reviews, ratings, competitor counts or trends.
Never promise sales, income or results. No legal, tax or accounting advice. Never copy competitor names, text or brands.
Never claim a feature the workbook does not have (for example overtime, benefits, union tracking, offline use, or preventing disputes).
Return ONLY valid JSON in the exact shape asked for, with no other text."""


def _texts(obj):
    """Every string inside a JSON-like object."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _texts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _texts(v)


def _safe(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(s)).strip("_")[:60] or "file"


def _ask(ctx, job, brain, role, user, check, images=(), rotate=0, grounding=False):
    system = SHARED + f"\n\nBRAIN {brain} - {BRAIN_NAMES[brain]}\n{role}"
    if ctx.get("fix_notes"):
        user += "\n\nCRITIC NOTES (fix every one; do not repeat the same problem):\n" + "\n".join(ctx["fix_notes"])
    if ctx.get("owner_notes"):
        user += f"\n\nOWNER NOTES (the owner wants this changed): {ctx['owner_notes']}"
    return engine.json_job(job, system, user, ctx["slots"], ctx["log"], ctx["keys"], check, images,
                           grounding=grounding, sources=ctx.get("sources") if grounding else None, rotate=rotate)


def _claims(d):
    """Risky, FREE or unsupported wording inside a reply."""
    return any(RISKY.search(s) or FREE_WORD.search(s) or UNSUPPORTED.search(s) for s in _texts(d))


def _headers(product):
    tabs = sheets.PRODUCT_SHEETS[product]
    headers = [c[0] for t in tabs for c in sheets.COLUMNS[t]]
    labels = [it[0] for _, items in sheets.dashboard_blocks(product) for it in items]
    return tabs, headers, labels


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
        if it.get("label") == "SOURCE" and not str(it.get("source", "")).startswith("http"):
            probs.append("a SOURCE item needs a link; label it GUESS or USER_INPUT instead")
    return probs[:6]


def merge_evidence(items):
    """Join the passes, drop repeats, and number the evidence E1, E2, ..."""
    seen, out = set(), []
    for it in items:
        text = str(it.get("text", "")).strip()
        key = re.sub(r"\W+", " ", text.lower()).strip()[:90]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"id": f"E{len(out) + 1}", "text": text, "label": it.get("label"),
                    "source": it.get("source", ""), "date": it.get("date", ""), "angle": it.get("angle", "")})
    return out


def brain1(ctx):
    n = max(RESEARCH_MIN, min(RESEARCH_MAX, int(ctx.get("research_passes", RESEARCH_DEFAULT))))
    items, passes, slots_used = [], [], []
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
        data, slot = _ask(ctx, "Research", 1, ROLE1, user, check_evidence,
                          ctx["images"] if i == 0 else (), rotate=i, grounding=bool(ctx.get("grounding")))
        for it in data["items"]:
            items.append(dict(it, angle=angle))
        passes.append({"angle": angle, "items": len(data["items"]), "web": len(web_items), "slot": slot})
        slots_used.append(slot)
    merged = merge_evidence(items)
    return {"items": merged, "passes": passes, "requested": n}, " + ".join(dict.fromkeys(slots_used))


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


# ---------------- brain 4: change plan
ROLE4 = """TASK: choose the product to make today and plan what is different from the last approved version.
Product keys: job_costing, change_orders, receivables, bundle. If the owner fixed the product, use it.
Change types allowed: colour, font, layout, feature, ease_of_use, complaint_fix, content, price_guidance.
The trade palette is fixed by the trade, so do not plan a new colour for the headers. Colour changes are only allowed in the layout notes.
Plan at least TWO different change types. With buyer complaints, one change must be complaint_fix.
If REQUIRED LAYOUT REFINEMENT is given, one change must be of type layout and must describe those refinements.
If RESULTS OF PAST VERSIONS are given, do not simply repeat a product or change that got no sales after 100 views; say what the results taught in results_considered.
Avoid repeating the same product on several days in a row unless there is a clear reason.
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
            f"RECENT DAYS (avoid repeating):\n" + ("\n".join(
                f"- {r.get('date', '')}: {r.get('product', '')}, changes {', '.join(r.get('types', []))}"
                for r in ctx.get("recent", [])) or "none") + "\n\n"
            f"RESULTS OF PAST VERSIONS (owner's own numbers):\n{ctx.get('results_text', 'none')}")
    return _ask(ctx, "Decide", 4, ROLE4, user, lambda d: check_plan(d, ctx))


# ---------------- brain 5: sheet text (checked against the real columns)
ROLE5 = """TASK: write the text that goes into the workbook: start lines for the START HERE tab, and one hint for each data tab.
Name only columns and tabs that exist in the list you are given. Never mention file styles, font sizes, row heights, pt, refinements or internal notes; the buyer only needs to know how to use the sheet. Keep the layout refinement visible in one line if one is given.
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
            f"TRADE TERMS: {json.dumps(ctx['out']['3'].get('terms', {}), ensure_ascii=False)}\n"
            f"LAYOUT REFINEMENT: {'; '.join(ctx.get('style_changes', [])) or 'none'}")
    return _ask(ctx, "Guide", 5, ROLE5, user, check)


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
    elif any("ESTIMATE" not in str(p.get("purpose", "")) for p in pt if isinstance(p, dict)):
        probs.append("each price test purpose must end with ESTIMATE")
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


# ---------------- brain 7: listing
ROLE7 = """TASK: write the Gumroad listing for today's product.
Include: 3 title options (product keyword first, no hype, 70 characters or fewer); a 2-line hook; a description of at least 300 characters that says in plain words what changed from the last version; what is included; 3 how-to steps; what it does NOT do; requirements (a Google account, and Google Sheets or Excel); 8 tags; 5 FAQ questions.
Do not use the word FREE. Say the buyer types their own numbers and results depend on those numbers.
Shape: {"titles": [3 strings], "hook": "...", "description": "...", "included": [4 or more], "how_to": [3], "not_included": [2 or more], "requirements": [2 or more], "tags": [8], "faq": [{"q": "...", "a": "..."}] (exactly 5)}"""


def check_listing(d, headers, labels):
    if not isinstance(d, dict):
        return ["the reply is not an object"]
    probs = []
    for key, k, msg in [("titles", 3, "need 3 titles"), ("included", 4, "need 4 included items"),
                        ("how_to", 3, "need 3 how-to steps"), ("not_included", 2, "need 2 not-included items"),
                        ("requirements", 2, "need 2 requirements"), ("tags", 8, "need 8 tags"),
                        ("faq", 5, "need 5 FAQ items")]:
        if not isinstance(d.get(key), list) or len(d[key]) < k:
            probs.append(msg)
    if len(str(d.get("description", ""))) < 300:
        probs.append("description must be at least 300 characters")
    if any(isinstance(t, str) and len(t) > 70 for t in d.get("titles", [])):
        probs.append("titles must be 70 characters or fewer")
    if _claims(d):
        probs.append("remove risky, FREE or unsupported wording")
    if not any("google sheets" in s.lower() or "excel" in s.lower() for s in _texts(d.get("requirements", []))):
        probs.append("requirements must name Google Sheets or Excel")
    probs += sheets.start_text_problems(list(_texts(d)), headers, labels)
    return probs[:8]


def brain7(ctx):
    plan = ctx["out"]["4"]
    _, headers, labels = _headers(plan["product"])
    user = (f"PLAN:\n{json.dumps(plan, ensure_ascii=False)[:4000]}\n\n"
            f"DECISION:\n{json.dumps(ctx['out']['6'], ensure_ascii=False)[:4000]}\n\n"
            f"SHEET TEXT:\n{json.dumps(ctx['out']['5'], ensure_ascii=False)[:2000]}\n\n"
            f"COLUMNS (exact): {', '.join(headers)}\n\n"
            f"LAST VERSION DESCRIPTION (write a NEW description; do not copy it):\n"
            f"{ctx['prev']['brains']['7']['data']['description'][:3000] if ctx.get('prev') else 'none'}")
    return _ask(ctx, "Listing", 7, ROLE7, user, lambda d: check_listing(d, headers, labels))


# ---------------- brain 8: buyer guide
ROLE8 = """TASK: write the buyer guide for a non-technical buyer who may use only a phone.
Use the SHEET TEXT and the tab list exactly. Never describe a tab, column or formula that is not in the list.
Sections: What you get; Before you start; First 10 minutes (numbered); Colour guide; Each tab, what to type; Common mistakes and fixes; Dashboard, what each number means; FAQ (5 questions).
Shape: {"sections": [{"title": "...", "text": "..."}] (at least 7 sections)}. Somewhere the text must say the file opens in Google Sheets or Excel."""


def check_guide(d, headers, labels):
    if not isinstance(d, dict) or not isinstance(d.get("sections"), list) or len(d["sections"]) < 7:
        return ["need at least 7 sections"]
    probs = []
    if not any("google sheets" in s.lower() or "excel" in s.lower() for s in _texts(d)):
        probs.append("say that the file opens in Google Sheets or Excel")
    if _claims(d):
        probs.append("remove risky, FREE or unsupported wording")
    probs += sheets.start_text_problems(list(_texts(d)), headers, labels)
    return probs[:8]


def brain8(ctx):
    plan = ctx["out"]["4"]
    _, headers, labels = _headers(plan["product"])
    user = (f"SHEET TEXT:\n{json.dumps(ctx['out']['5'], ensure_ascii=False)[:3000]}\n\n"
            f"COLUMNS (exact): {', '.join(headers)}\nDASHBOARD ITEMS (exact): {', '.join(labels)}\n\n"
            f"TITLE OPTIONS: {', '.join(ctx['out']['7']['titles'])}")
    return _ask(ctx, "Guide", 8, ROLE8, user, lambda d: check_guide(d, headers, labels))


# ---------------- brain 9: pins and image brief
ROLE9 = """TASK: write 5 Pinterest pins for today's product. Text only. Use the trade's own words.
Each pin: headline (60 characters or fewer), text_on_image (8 words or fewer), description (2 sentences), board (a board name), cta (one call to action). No FREE, no promises, no features the workbook does not have.
Shape: {"pins": [5 objects with headline, text_on_image, description, board, cta]}"""


def check_pins(d):
    if not isinstance(d, dict) or not isinstance(d.get("pins"), list) or len(d["pins"]) != 5:
        return ["pins must have exactly 5 items"]
    probs = []
    for p in d["pins"]:
        if not isinstance(p, dict):
            probs.append("a pin is not an object")
            continue
        if len(str(p.get("headline", ""))) > 60:
            probs.append("a headline is longer than 60 characters")
        if len(str(p.get("text_on_image", "")).split()) > 8:
            probs.append("text_on_image must be 8 words or fewer")
    if _claims(d):
        probs.append("remove risky, FREE or unsupported wording")
    return probs[:6]


def pin_image_prompt(trade, brand):
    """The image brief for the pin, built by code from the trade palette. The text is added later, not by the AI."""
    t = sheets.TRADES[trade]
    return ("Professional e-commerce Pinterest pin, vertical 2:3 ratio (1000x1500 px). "
            "Light wooden desk, bright soft studio lighting, commercial product photography. "
            "A modern laptop and a smartphone side by side. Both screens show a realistic spreadsheet with clean grey "
            "gridlines, a plain data table and a simple 2D bar chart. No fake app interface, no glowing 3D charts, "
            "no logos on any screen. "
            f"A confident, smiling trade professional, {PROPS.get(trade, PROPS['other'])}, stands beside the devices. "
            f"Colour palette: {t['palette']} (primary {t['primary']}, accent {t['accent']}). "
            "Leave a clean flat area in the upper third for a headline, an empty top-left corner for the brand mark "
            f"('{brand}', added later) and an empty area at the bottom for a button. "
            "No text inside the picture. "
            "Avoid: text on screens, misspelled words, watermarks, Microsoft or Google logos, distorted letters, cartoon style.")


def brain9(ctx):
    t = sheets.TRADES[ctx["trade"]]
    user = (f"LISTING:\n{json.dumps(ctx['out']['7'], ensure_ascii=False)[:5000]}\n\n"
            f"TRADE PALETTE: {t['palette']}\nBRAND: {ctx['brand']}")
    data, slot = _ask(ctx, "Pins", 9, ROLE9, user, check_pins)
    data = dict(data, image_brief=pin_image_prompt(ctx["trade"], ctx["brand"]))
    return data, slot


BRAIN_FN = {1: brain1, 2: brain2, 3: brain3, 4: brain4, 5: brain5, 6: brain6, 7: brain7, 8: brain8, 9: brain9}


# ---------------- brain 10: mobile and layout reviewer (code)
def mobile_check(ctx, state):
    """Build the phone file for this run and check it. Returns (rows, file bytes)."""
    out = {k: v["data"] for k, v in state["brains"].items()}
    text = {"start_lines": out["5"]["start_lines"], "hints": out["5"]["hints"]}
    blob = sheets.build_workbook(state["product"], ctx["currency"], ctx["business"], "phone",
                                 trade=ctx["trade"], style=ctx["style"], text=text, brand=ctx["brand"])
    return sheets.mobile_report(blob), blob


# ---------------- brain 11: critic and gate
def brain11(ctx, state):
    """Code checks first; the AI critic (if a Critic slot is ready) only adds advisory notes."""
    out = ctx["out"]
    plan = out["4"]
    checks, fix, problems, block = [], set(), [], False
    passes = out["1"].get("passes", [])
    ok = len(passes) >= 1 and len(out["1"]["items"]) >= 6
    checks.append(("Research depth", "PASS" if ok else "BLOCK",
                   f"{len(passes)} passes, {len(out['1']['items'])} evidence items"))
    block = block or not ok
    types = {c["type"] for c in plan["changes"] if isinstance(c, dict)}
    ok = len(types) >= 2
    checks.append(("At least two change types", "PASS" if ok else "BLOCK", ", ".join(sorted(types))))
    block = block or not ok
    style_ok = ctx.get("style") != ctx.get("prev_style")
    checks.append(("Layout refinement applied", "PASS" if style_ok else "BLOCK",
                   "; ".join(ctx.get("style_changes", [])) or "no change"))
    block = block or not style_ok
    if ctx["complaints"]:
        ok = "complaint_fix" in types
        checks.append(("A complaint is answered", "PASS" if ok else "FIX",
                       "complaint_fix present" if ok else "missing"))
        if not ok:
            fix.add(4)
            problems.append("a buyer complaint is not answered: add a complaint_fix change")
    prev = ctx.get("prev")
    if prev:
        ratio = difflib.SequenceMatcher(None, prev["brains"]["7"]["data"]["description"],
                                        out["7"]["description"]).ratio()
        ok = ratio < 0.85
        checks.append(("Listing is new, not a copy of the last version", "PASS" if ok else "FIX",
                       f"similarity {ratio:.2f} (limit 0.85)"))
        if not ok:
            fix.add(7)
            problems.append("the listing description is too similar to the last version: rewrite it around the changes")
        same = prev["brains"]["5"]["data"]["hints"] == out["5"]["hints"]
        checks.append(("Workbook text is new", "FIX" if same else "PASS",
                       "same as the last version" if same else "changed"))
        if same:
            fix.add(5)
            problems.append("the sheet text is the same as the last version: change the hints for the changes")
    for n in ["5", "6", "7", "8", "9"]:
        if n not in out:
            continue
        blob = list(_texts(out[n]))
        hits = sorted({m.group(0).lower() for s in blob for m in RISKY.finditer(s)}
                      | {m.group(0).lower() for s in blob for m in UNSUPPORTED.finditer(s)})
        free = any(FREE_WORD.search(s) for s in blob)
        ok = not hits and not free
        checks.append((f"Brain {n} wording is safe", "PASS" if ok else "FIX",
                       ", ".join(hits) or ("the word FREE" if free else "none found")))
        if not ok:
            fix.add(int(n))
            problems.append(f"brain {n}: remove " + (", ".join(hits) or "the word FREE"))
    _, headers, labels = _headers(state["product"])
    sheet_probs = sheets.start_text_problems([str(x) for x in out["5"]["start_lines"]], headers, labels)
    checks.append(("START HERE matches the columns", "PASS" if not sheet_probs else "FIX",
                   sheet_probs[0] if sheet_probs else "every claim matches a column or Dashboard item"))
    if sheet_probs:
        fix.add(5)
        problems += sheet_probs[:3]
    for name, status, detail in sheets.palette_problems(ctx["trade"]):
        checks.append((f"Palette: {name}", status, detail))
        if status == "FIX":
            block = True
    try:
        rows, _blob = mobile_check(ctx, state)
        bad = [r for r in rows if r[1] == "FIX"]
        for name, status, detail in rows:
            if status != "PASS":
                checks.append((f"Phone: {name}", status, detail))
        checks.append(("Phone file checks", "PASS" if not bad else "BLOCK",
                       f"{len(rows) - len(bad)} of {len(rows)} passed"))
        block = block or bool(bad)
        if bad:
            problems.append("phone file: " + "; ".join(r[0] for r in bad[:3]))
    except Exception as e:
        checks.append(("Phone file checks", "BLOCK", "could not build: " + str(e)[:120]))
        block = True
    if any("Critic" in e.get("duties", []) for e in engine.ready_entries(ctx["slots"])):
        summary = {"plan": plan.get("summary", ""), "listing_description": out["7"]["description"][:1500],
                   "sheet_hints": list(out["5"]["hints"].values())[:6]}
        try:
            crit, _slot = engine.json_job(
                "Critic", SHARED + "\n\nBRAIN 11 - Critic and gate\nTASK: read the summary and reply JSON: "
                '{"verdict": "PASS or FIX", "problems": ["..."]}. Look for claims without evidence, buyer promises, '
                "wording that does not match the plan, and anything a buyer could misread.",
                json.dumps(summary, ensure_ascii=False), ctx["slots"], ctx["log"], ctx["keys"],
                lambda d: [] if isinstance(d, dict) and d.get("verdict") in ("PASS", "FIX")
                else ["verdict must be PASS or FIX"])
            notes = [str(x) for x in crit.get("problems", [])][:5]
            checks.append(("AI critic (advisory)", "PASS" if crit["verdict"] == "PASS" else "WARNING",
                           "; ".join(notes) or "no concerns"))
        except Exception as e:
            checks.append(("AI critic (advisory)", "WARNING", "skipped: " + engine.scrub(e, ctx["keys"])[:120]))
    verdict = "BLOCK" if block else ("FIX" if fix else "PASS")
    checks.append(("Overall gate", verdict, f"{len(checks)} checks"))
    return {"verdict": verdict, "checks": checks, "fix_brains": sorted(fix), "problems": problems}


# ---------------- pipeline
def new_state(product_key):
    return {"status": "idle", "product": product_key, "brains": {}, "slots": {}, "errors": [],
            "checks": [], "problems": [], "fix_round": 0, "product_fixed": product_key is not None,
            "started": datetime.now().strftime("%Y-%m-%d %H:%M")}


def run_pipeline(state, ctx, save, pins_on=True):
    """Run the AI brains that are not done yet, in order, then the gate. Returns the status string."""
    b = state["brains"]
    state["pins_on"] = pins_on
    order = [n for n in AI_ORDER if pins_on or n != 9]
    state["status"] = "running"
    state["errors"] = []
    save(state)
    while True:
        for n in order:
            if str(n) in b:
                continue
            ctx["out"] = {k: v["data"] for k, v in b.items()}
            try:
                data, slot = BRAIN_FN[n](ctx)
            except Exception as e:
                state["status"] = "error"
                state["errors"].append({"brain": n, "name": BRAIN_NAMES[n], "msg": str(e)[:300],
                                        "at": datetime.now().strftime("%H:%M:%S")})
                save(state)
                return "error"
            b[str(n)] = {"data": data, "slot": slot, "at": datetime.now().strftime("%H:%M:%S")}
            state["slots"][str(n)] = slot
            if n == 4:
                state["product"] = data["product"]
            save(state)
        ctx["out"] = {k: v["data"] for k, v in b.items()}
        gate = brain11(ctx, state)
        state["checks"], state["problems"] = gate["checks"], gate["problems"]
        if gate["verdict"] == "PASS":
            state["status"] = "waiting_approval"
            save(state)
            return "waiting_approval"
        if gate["verdict"] == "BLOCK" or state["fix_round"] >= 2:
            state["status"] = "blocked"
            save(state)
            return "blocked"
        state["fix_round"] += 1
        ctx["fix_notes"] = gate["problems"]
        for n in range(min(gate["fix_brains"]), 10):
            b.pop(str(n), None)
        save(state)


# ---------------- brain 12: package (code only)
DOCS = [
    ("01_research.json", "1", "Research (merged passes, with sources)"),
    ("02_gaps_and_complaints.json", "2", "Gaps and complaints"),
    ("03_trade_profile.json", "3", "Trade profile"),
    ("04_change_plan.json", "4", "Change plan: what is different from the last version, and why"),
    ("05_sheet_text.json", "5", "Sheet text (START HERE and tab hints)"),
    ("06_decision_and_price_test.json", "6", "Decision and price test (ESTIMATE ranges)"),
    ("07_gumroad_listing.json", "7", "Gumroad listing and FAQ"),
    ("08_buyer_guide.json", "8", "Buyer guide"),
    ("09_pinterest_pins.json", "9", "Pinterest pins"),
]
HOW_TO = """ادائیگی سے پہلے یہ مراحل کریں (صرف اپنے لیے)
1. ZIP کھولیں۔
2. لیپ ٹاپ فائل کمپیوٹر کے لیے، موبائل فائل فون کے لیے ہے۔
3. google_test فولڈر کی تین فائلیں گوگل ڈرائیو پر اپ لوڈ کر کے Google Sheets میں کھولیں: full، plain، no_protection۔ جو ٹھیک کھلے وہی اصل فائل بنے گی۔
4. Gumroad پر نیا پروڈکٹ بنائیں، فائل اپ لوڈ کریں، لسٹنگ (07) چسپاں کریں، قیمت فیصلے (06) کے مطابق رکھیں۔
5. پن کی تصویر کا پرامپٹ (10) استعمال کریں۔ برانڈ کا نام اور سرخی تصویر پر خود لکھیں۔
6. گیٹ کی رپورٹ (12) اور فون کی جانچ (11) دیکھیں، پھر اپلوڈ کریں۔
کسی بھی پلیٹ فارم کے موجودہ قواعد اپلوڈ سے پہلے خود دیکھیں۔ یہ قانونی یا ٹیکس مشورہ نہیں۔
"""


def build_package(ctx, state, version_no):
    """Build the workbooks, the Google test variants, the documents and the checksums. Returns (zip bytes, manifest)."""
    out = {k: v["data"] for k, v in state["brains"].items()}
    prod = state["product"]
    text = {"start_lines": out["5"]["start_lines"], "hints": out["5"]["hints"]}
    cur, biz, brand, trade, style = ctx["currency"], ctx["business"], ctx["brand"], ctx["trade"], ctx["style"]
    base = f"{_safe(biz)}_{prod}_v{version_no}"
    kw = dict(trade=trade, style=style, text=text, brand=brand)
    files = {
        f"{base}_laptop.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", **kw),
        f"{base}_phone.xlsx": sheets.build_workbook(prod, cur, biz, "phone", **kw),
        f"google_test/{base}_full.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", **kw),
        f"google_test/{base}_plain.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", protect=False,
                                                               validations=False, conditional=False, **kw),
        f"google_test/{base}_no_protection.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", protect=False, **kw),
    }
    for fname, n, title in DOCS:
        files[fname] = f"{title}\n\n" + json.dumps(out[n], ensure_ascii=False, indent=2)
    files["10_pin_image_brief.txt"] = out["9"].get("image_brief", "") if "9" in out else "pins were not made"
    rows, _ = mobile_check(ctx, state)
    files["11_mobile_check.txt"] = "\n".join(f"{n}: {s}. {d}" for n, s, d in rows)
    files["12_quality_gate.txt"] = "\n".join(f"{n}: {s}. {d}" for n, s, d in state["checks"])
    files["13_sheet_specification.txt"] = sheets.spec_text(prod, cur, biz)
    files["14_how_to_upload.txt"] = HOW_TO
    files["layout_refinement.txt"] = "\n".join(ctx.get("style_changes", [])) or "no change"
    manifest = {name: hashlib.sha256(d if isinstance(d, bytes) else d.encode("utf-8")).hexdigest()
                for name, d in files.items()}
    files["MANIFEST.txt"] = "\n".join(f"{h}  {n}" for n, h in manifest.items())
    files["README.txt"] = ("Made with Business Factory 5 for " + brand + ". Check every file yourself. Read the current "
                           "Gumroad and Pinterest rules before you publish. Upload and post manually. "
                           "Not legal, tax or accounting advice.\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, bytes) else data.encode("utf-8"))
    return buf.getvalue(), manifest
