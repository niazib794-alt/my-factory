"""Business Factory 5 - the ten brains.

Brains 1-8 use AI. Each reply is checked by code, and a rejected reply gets one retry with the reason.
Brain 9 is the critic: its checks are code, so the AI cannot override them. A FIX sends only the brains
that need it back through the pipeline (at most two fix rounds). A BLOCK stops the run.
Brain 10 builds the files with code only. Nothing is approved without the owner.
The pipeline saves after every brain and resumes where it stopped.
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
BRAIN_NAMES = {1: "Evidence", 2: "Gaps and complaints", 3: "Change plan", 4: "Sheet text",
               5: "Decision and price", 6: "Gumroad listing", 7: "Buyer guide", 8: "Pins (optional)",
               9: "Critic and gate", 10: "Package"}
ORDER = [1, 2, 3, 4, 5, 6, 7, 8]
RISKY = re.compile(r"\b(guarantee[sd]?|best[- ]?sellers?|cure[sd]?|diagnos\w*|medical|treat(?:s|ment)?|"
                   r"passive income|get rich|income guarantee)\b", re.I)
FREE_WORD = re.compile(r"\bfree\b", re.I)
SHARED = """You are one brain inside Business Factory 5. The system prepares one product: a Google Sheets / Excel workbook for contractors and service businesses, sold on Gumroad.
Owner notes and feedback are simple Urdu. Buyer-facing text is simple English with short sentences.
EVIDENCE: every claim is labelled SOURCE (with a link), USER_INPUT (pasted or uploaded by the owner), GUESS or UNKNOWN. Never invent numbers, prices, sales, reviews, ratings, competitor counts or trends.
Never promise sales, income or results. No legal, tax or accounting advice. Never copy competitor names, text or brands.
Return ONLY valid JSON in the exact shape asked for, with no other text."""

ROLE1 = """TASK: turn the pasted research, web results and screenshot notes into evidence items.
Each item: {"id": "E1", "text": "one clear fact or observation", "label": "SOURCE | USER_INPUT | GUESS | UNKNOWN", "source": "a link, or 'owner', or ''", "date": "YYYY-MM-DD or ''"}.
A SOURCE item must have a link. If there is no research and no web result, you may add GUESS items about the product area only.
Shape: {"items": [6 to 25 items]}"""

ROLE2 = """TASK: find the market gaps and the buyer complaints this product can solve.
Use only the EVIDENCE items (name their ids) and the complaints. A gap with no evidence id must have "guess": true.
Shape: {"gaps": [{"gap": "...", "evidence_ids": ["E1"], "guess": false, "complaint": false}], "complaints_used": ["..."], "no_gap_reason": ""}
If no gap can be shown, give an empty gaps list and write the reason in no_gap_reason."""

ROLE3 = """TASK: choose the product to make today and plan what is different from the last approved version.
Product keys: job_costing, change_orders, receivables, bundle. If the owner fixed the product, use it.
Change types allowed: colour, font, layout, feature, ease_of_use, complaint_fix, content, price_guidance.
Plan at least TWO different change types. With buyer complaints, one change must be complaint_fix.
Theme: one of blue, green, purple, teal, amber, rose. It must differ from the last version's theme.
Avoid repeating the same product on several days in a row unless there is a clear reason.
If RESULTS OF PAST VERSIONS are given, do not simply repeat a product or change that got no sales after 100 views. Say what the results taught you in results_considered.
Shape: {"product": "job_costing", "theme": "green", "summary": "one sentence", "results_considered": "what past results showed, or empty if none", "changes": [{"type": "colour", "what": "...", "why": "...", "evidence_ids": ["E1"]}]}"""

ROLE4 = """TASK: write the text that goes into the workbook: start lines for the START HERE tab, and one hint for each tab.
Keep the planned changes visible in the text (for example, name the colour or layout change in a start line).
Shape: {"start_lines": ["3 to 10 short English lines"], "hints": {"Tab name": "one short English line"}} with one hint for every tab listed."""

ROLE5 = """TASK: decide the next step for today's product and give a price test.
Price tests: three ranges in the given currency. Each purpose ends with the word ESTIMATE. Do not claim what the market pays.
Features: the five workbook features that matter most to this buyer, in order.
Risks: at least three. Test: what to record in 14 days, and go / no-go questions for the owner to answer.
Shape: {"verdict": "...", "buyer": "one sentence", "price_tests": [{"range": "...", "purpose": "... ESTIMATE"}] (exactly 3), "features": [5 strings], "risks": [3 or more strings], "test14": {"record": ["views", "saves", "clicks", "sales"], "go_no_go": ["question", "question"]}}"""

ROLE6 = """TASK: write the Gumroad listing for today's product.
Include: 3 title options (product keyword first, no hype, 70 characters or fewer); a 2-line hook; a description of at least 300 characters that says in plain words what changed from the last version; what is included; 3 how-to steps; what it does NOT do; requirements (a Google account, and Google Sheets or Excel); 8 tags; 5 FAQ questions.
Do not use the word FREE. Say the buyer types their own numbers and results depend on those numbers.
Shape: {"titles": [3 strings], "hook": "...", "description": "...", "included": [4 or more], "how_to": [3], "not_included": [2 or more], "requirements": [2 or more], "tags": [8], "faq": [{"q": "...", "a": "..."}] (exactly 5)}"""

ROLE7 = """TASK: write the buyer guide for a non-technical buyer who may use only a phone.
Use the SHEET TEXT and the tab list exactly. Never describe a tab, column or formula that is not in the list.
Sections: What you get; Before you start; First 10 minutes (numbered); Colour guide; Each tab, what to type; Common mistakes and fixes; Dashboard, what each number means; FAQ (5 questions).
Shape: {"sections": [{"title": "...", "text": "..."}] (at least 7 sections)}. Somewhere the text must say the file opens in Google Sheets or Excel."""

ROLE8 = """TASK: write 5 Pinterest pins for today's product. Text only.
Each pin: headline (60 characters or fewer), text_on_image (8 words or fewer), description (2 sentences), board (a board name), cta (one call to action). No FREE, no promises.
Shape: {"pins": [5 objects with headline, text_on_image, description, board, cta]}"""


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


def _ask(ctx, job, brain, role, user, check, images=()):
    system = SHARED + f"\n\nBRAIN {brain} - {BRAIN_NAMES[brain]}\n{role}"
    if ctx.get("fix_notes"):
        user += "\n\nCRITIC NOTES (fix every one; do not repeat the same problem):\n" + "\n".join(ctx["fix_notes"])
    if ctx.get("owner_notes"):
        user += f"\n\nOWNER NOTES (the owner wants this changed): {ctx['owner_notes']}"
    return engine.json_job(job, system, user, ctx["slots"], ctx["log"], ctx["keys"], check, images,
                           grounding=ctx.get("grounding", False) and brain == 1, sources=ctx.get("sources"))


# ---------------- brain 1: evidence
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


def brain1(ctx):
    user = (f"PRODUCT AREA: {ctx['product_title']}\nAUDIENCE: {ctx['audience']}\nMARKETS: {ctx['markets']}\n"
            f"SOURCE OF PASTED RESEARCH: {ctx['source'] or 'owner'}\n\n"
            f"PASTED RESEARCH:\n{ctx['research_text'].strip()[:24000] or 'none'}\n\n"
            f"WEB RESULTS:\n{ctx['web_text'][:12000] or 'none'}\n\nSCREENSHOT NOTES: {ctx['shot_note']}")
    return _ask(ctx, "Research", 1, ROLE1, user, check_evidence, ctx["images"])


# ---------------- brain 2: gaps and complaints
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
    user = ("EVIDENCE:\n" + "\n".join(f"{i['id']} [{i['label']}] {i['text']} | {i.get('source', '')}" for i in ev) +
            "\n\nBUYER COMPLAINTS (owner input):\n" + ("\n".join(f"- {c}" for c in ctx["complaints"]) or "none"))
    return _ask(ctx, "Research", 2, ROLE2, user, lambda d: check_gaps(d, ids))


# ---------------- brain 3: change plan
def check_plan(d, ctx):
    if not isinstance(d, dict):
        return ["the reply is not an object"]
    probs = []
    if d.get("product") not in PRODUCT_TITLES:
        probs.append("product must be job_costing, change_orders, receivables or bundle")
    if ctx["product_fixed"] and d.get("product") != ctx["product"]:
        probs.append(f"the owner fixed the product to {ctx['product']}")
    if d.get("theme") not in sheets.THEMES:
        probs.append("theme must be one of " + ", ".join(sheets.THEMES))
    elif ctx.get("prev_theme") and d.get("theme") == ctx["prev_theme"]:
        probs.append(f"theme must differ from the last version ({ctx['prev_theme']})")
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
    if not str(d.get("summary", "")).strip():
        probs.append("summary is empty")
    if ctx.get("results_text", "none") != "none" and not str(d.get("results_considered", "")).strip():
        probs.append("results exist: say in results_considered what they showed")
    return probs[:6]


def brain3(ctx):
    gaps = ctx["out"]["2"]
    prev = ctx.get("prev")
    recent = "\n".join(f"- {r.get('date', '')}: {r.get('product', '')}, theme {r.get('theme', '')}, "
                       f"changes {', '.join(r.get('types', []))}" for r in ctx.get("recent", [])) or "none"
    user = (f"PRODUCT FIXED BY OWNER: {ctx['product'] if ctx['product_fixed'] else 'no, the brain chooses'}\n"
            f"GAPS:\n{json.dumps(gaps, ensure_ascii=False)[:6000]}\n\n"
            f"BUYER COMPLAINTS:\n{chr(10).join('- ' + c for c in ctx['complaints']) or 'none'}\n\n"
            f"LAST APPROVED VERSION: {prev['summary'] if prev else 'none (first version)'}\n"
            f"LAST THEME: {ctx.get('prev_theme') or 'none'}\n\n"
            f"RECENT DAYS (avoid repeating):\n{recent}")
    user += f"\n\nRESULTS OF PAST VERSIONS (owner's own numbers):\n{ctx.get('results_text', 'none')}"
    return _ask(ctx, "Decide", 3, ROLE3, user, lambda d: check_plan(d, ctx))


# ---------------- brain 4: sheet text
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
    if any(len(s) > 220 for s in _texts(d)):
        probs.append("a line is longer than 220 characters")
    if any(RISKY.search(s) or FREE_WORD.search(s) for s in _texts(d)):
        probs.append("remove risky or FREE wording")
    return probs[:6]


def brain4(ctx):
    plan = ctx["out"]["3"]
    tabs = sheets.PRODUCT_SHEETS[plan["product"]]
    user = (f"PLAN:\n{json.dumps(plan, ensure_ascii=False)[:4000]}\n\nTABS (one hint each): {', '.join(tabs)}\n"
            f"CURRENCY: {ctx['currency']}")
    return _ask(ctx, "Guide", 4, ROLE4, user, lambda d: check_text(d, tabs))


# ---------------- brain 5: decision and price
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
    if any(RISKY.search(s) or FREE_WORD.search(s) for s in _texts(d)):
        probs.append("remove risky or FREE wording")
    return probs[:6]


def brain5(ctx):
    user = (f"PLAN:\n{json.dumps(ctx['out']['3'], ensure_ascii=False)[:4000]}\n\n"
            f"EVIDENCE:\n{json.dumps(ctx['out']['1'], ensure_ascii=False)[:8000]}\n\nCURRENCY: {ctx['currency']}")
    user += f"\n\nRESULTS OF PAST VERSIONS:\n{ctx.get('results_text', 'none')}"
    return _ask(ctx, "Decide", 5, ROLE5, user, check_decision)


# ---------------- brain 6: listing
def check_listing(d):
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
    if any(RISKY.search(s) or FREE_WORD.search(s) for s in _texts(d)):
        probs.append("remove risky or FREE wording")
    if not any("google sheets" in s.lower() or "excel" in s.lower() for s in _texts(d.get("requirements", []))):
        probs.append("requirements must name Google Sheets or Excel")
    return probs[:6]


def brain6(ctx):
    plan = ctx["out"]["3"]
    prev = ctx.get("prev")
    prev_desc = prev["brains"]["6"]["data"]["description"] if prev else "none"
    user = (f"PLAN:\n{json.dumps(plan, ensure_ascii=False)[:4000]}\n\nDECISION:\n"
            f"{json.dumps(ctx['out']['5'], ensure_ascii=False)[:4000]}\n\nSHEET TEXT:\n"
            f"{json.dumps(ctx['out']['4'], ensure_ascii=False)[:2000]}\n\n"
            f"LAST VERSION DESCRIPTION (write a NEW description; do not copy it):\n{prev_desc[:3000]}")
    return _ask(ctx, "Listing", 6, ROLE6, user, check_listing)


# ---------------- brain 7: buyer guide
def check_guide(d):
    if not isinstance(d, dict) or not isinstance(d.get("sections"), list) or len(d["sections"]) < 7:
        return ["need at least 7 sections"]
    probs = []
    if not any("google sheets" in s.lower() or "excel" in s.lower() for s in _texts(d)):
        probs.append("say that the file opens in Google Sheets or Excel")
    if any(RISKY.search(s) or FREE_WORD.search(s) for s in _texts(d)):
        probs.append("remove risky or FREE wording")
    return probs[:6]


def brain7(ctx):
    user = (f"SHEET TEXT:\n{json.dumps(ctx['out']['4'], ensure_ascii=False)[:3000]}\n\n"
            f"TABS AND COLUMNS (exact):\n{sheets.spec_text(ctx['out']['3']['product'], ctx['currency'], ctx['business'])[:5000]}\n\n"
            f"TITLE OPTIONS: {', '.join(ctx['out']['6']['titles'])}")
    return _ask(ctx, "Guide", 7, ROLE7, user, check_guide)


# ---------------- brain 8: pins (optional)
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
    if any(RISKY.search(s) or FREE_WORD.search(s) for s in _texts(d)):
        probs.append("remove risky or FREE wording")
    return probs[:6]


def brain8(ctx):
    user = f"LISTING:\n{json.dumps(ctx['out']['6'], ensure_ascii=False)[:5000]}"
    return _ask(ctx, "Pins", 8, ROLE8, user, check_pins)


BRAIN_FN = {1: brain1, 2: brain2, 3: brain3, 4: brain4, 5: brain5, 6: brain6, 7: brain7, 8: brain8}


# ---------------- brain 9: critic and gate
def brain9(ctx):
    """Code checks first (the AI cannot override them). Returns verdict PASS, FIX or BLOCK."""
    out = ctx["out"]
    plan = out["3"]
    checks, fix, problems, block = [], set(), [], False
    types = {c.get("type") for c in plan["changes"] if isinstance(c, dict)}
    ok = len(types) >= 2
    checks.append(("At least two change types", "PASS" if ok else "BLOCK", ", ".join(sorted(types))))
    block = block or not ok
    if ctx.get("complaints"):
        ok = "complaint_fix" in types
        checks.append(("A complaint is answered", "PASS" if ok else "FIX", "complaint_fix present" if ok else "missing"))
        if not ok:
            fix.add(3)
            problems.append("a buyer complaint is not answered: add a complaint_fix change")
    prev = ctx.get("prev")
    if prev:
        same_theme = plan["theme"] == prev["theme"]
        checks.append(("Theme differs from the last version", "BLOCK" if same_theme else "PASS",
                       f"{prev['theme']} -> {plan['theme']}"))
        block = block or same_theme
        ratio = difflib.SequenceMatcher(None, prev["brains"]["6"]["data"]["description"],
                                        out["6"]["description"]).ratio()
        ok = ratio < 0.85
        checks.append(("Listing is new, not a copy of the last version", "PASS" if ok else "FIX",
                       f"similarity {ratio:.2f} (limit 0.85)"))
        if not ok:
            fix.add(6)
            problems.append("the listing description is too similar to the last version: rewrite it around the planned changes")
        same_hints = prev["brains"]["4"]["data"]["hints"] == out["4"]["hints"]
        checks.append(("Workbook text is new", "FIX" if same_hints else "PASS",
                       "same as the last version" if same_hints else "changed"))
        if same_hints:
            fix.add(4)
            problems.append("the sheet text is the same as the last version: change the hints for the planned changes")
    for n in ["4", "5", "6", "7", "8"]:
        if n not in out:
            continue
        blob = list(_texts(out[n]))
        hits = sorted({m.group(0).lower() for s in blob for m in RISKY.finditer(s)})
        free = any(FREE_WORD.search(s) for s in blob)
        ok = not hits and not free
        checks.append((f"Brain {n} wording is safe", "PASS" if ok else "FIX",
                       ", ".join(hits) or ("the word FREE" if free else "none found")))
        if not ok:
            fix.add(int(n))
            problems.append(f"brain {n}: remove " + (", ".join(hits) or "the word FREE"))
    if any("Critic" in e.get("duties", []) for e in engine.ready_entries(ctx["slots"])):
        summary = {"plan": plan.get("summary", ""), "listing_description": out["6"]["description"][:1500],
                   "sheet_hints": list(out["4"]["hints"].values())[:6]}
        try:
            crit, _slot = engine.json_job(
                "Critic", SHARED + "\n\nBRAIN 9 - Critic and gate\nTASK: read the summary and reply JSON: "
                '{"verdict": "PASS or FIX", "problems": ["..."]}. Look for claims without evidence, buyer promises, '
                "wording that does not match the plan, and anything a buyer could misread.",
                json.dumps(summary, ensure_ascii=False), ctx["slots"], ctx["log"], ctx["keys"],
                lambda d: [] if isinstance(d, dict) and d.get("verdict") in ("PASS", "FIX")
                else ["verdict must be PASS or FIX"])
            problems_ai = [str(x) for x in crit.get("problems", [])][:5]
            checks.append(("AI critic (advisory)", "PASS" if crit["verdict"] == "PASS" else "WARNING",
                           "; ".join(problems_ai) or "no concerns"))
        except Exception as e:
            checks.append(("AI critic (advisory)", "WARNING", "skipped: " + str(e)[:120]))
    verdict = "BLOCK" if block else ("FIX" if fix else "PASS")
    checks.append(("Overall gate", verdict, f"{len(checks)} checks"))
    return {"verdict": verdict, "checks": checks, "fix_brains": sorted(fix), "problems": problems}


# ---------------- pipeline
def new_state(product_key):
    return {"status": "idle", "product": product_key, "brains": {}, "slots": {}, "errors": [],
            "checks": [], "problems": [], "fix_round": 0, "started": datetime.now().strftime("%Y-%m-%d %H:%M")}


def run_pipeline(state, ctx, save, pins_on=True):
    """Run the brains that are not done yet, in order. Returns the status string."""
    b = state["brains"]
    order = [n for n in ORDER if pins_on or n != 8]
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
            if n == 3:
                state["product"] = data["product"]
            save(state)
        ctx["out"] = {k: v["data"] for k, v in b.items()}
        gate = brain9(ctx)
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
        for n in range(min(gate["fix_brains"]), 9):
            b.pop(str(n), None)
        save(state)


# ---------------- brain 10: package (code only)
DOCS = [
    ("01_evidence.json", "1", "Evidence"),
    ("02_gaps_and_complaints.json", "2", "Gaps and complaints"),
    ("03_change_plan.json", "3", "Change plan: what is different from the last version, and why"),
    ("04_sheet_text.json", "4", "Sheet text (start lines and tab hints)"),
    ("05_decision_and_price_test.json", "5", "Decision and price test (ESTIMATE ranges)"),
    ("06_gumroad_listing.json", "6", "Gumroad listing and FAQ"),
    ("07_buyer_guide.json", "7", "Buyer guide"),
    ("08_pinterest_pins.json", "8", "Pinterest pins (optional)"),
]
HOW_TO = """ادائیگی سے پہلے یہ مراحل کریں (صرف اپنے لیے)
1. ZIP کھولیں۔
2. لیپ ٹاپ فائل (…_laptop.xlsx) کمپیوٹر کے لیے، موبائل فائل (…_phone.xlsx) فون کے لیے ہے۔
3. google_test فولڈر کی تین فائلیں گوگل ڈرائیو پر اپ لوڈ کر کے Google Sheets میں کھولیں: full، plain، no_protection۔ جو ٹھیک کھلے وہی اصل فائل بنے گی۔
4. Gumroad پر نیا پروڈکٹ بنائیں، فائل اپ لوڈ کریں، لسٹنگ (06) چسپاں کریں، قیمت فیصلے (05) کے مطابق رکھیں۔
5. Pinterest پر پن (08) خود پوسٹ کریں۔
6. گیٹ کی رپورٹ (09) دیکھیں اور اپ لوڈ سے پہلے تصدیق کریں۔
کسی بھی پلیٹ فارم کے موجودہ قواعد اپلوڈ سے پہلے خود دیکھیں۔ یہ قانونی یا ٹیکس مشورہ نہیں۔
"""


def build_package(ctx, state, version_no):
    """Build the workbooks, the Google test variants, the documents, the checks and the ZIP.
    Returns (zip bytes, manifest dict of name -> sha256)."""
    out = {k: v["data"] for k, v in state["brains"].items()}
    prod = state["product"]
    theme = out["3"]["theme"]
    text = {"start_lines": out["4"]["start_lines"], "hints": out["4"]["hints"]}
    cur, biz = ctx["currency"], ctx["business"]
    base = f"{_safe(biz)}_{prod}_v{version_no}"
    files = {
        f"{base}_laptop.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", theme=theme, text=text),
        f"{base}_phone.xlsx": sheets.build_workbook(prod, cur, biz, "phone", theme=theme, text=text),
        f"google_test/{base}_full.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", theme=theme, text=text),
        f"google_test/{base}_plain.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", theme=theme, text=text,
                                                               protect=False, validations=False, conditional=False),
        f"google_test/{base}_no_protection.xlsx": sheets.build_workbook(prod, cur, biz, "laptop", theme=theme,
                                                                       text=text, protect=False),
    }
    for fname, n, title in DOCS:
        files[fname] = f"{title}\n\n" + json.dumps(out[n], ensure_ascii=False, indent=2)
    files["03_change_plan.json"] = (f"Change plan (what is different from the last version, and why)\n\n"
                                    + json.dumps(out["3"], ensure_ascii=False, indent=2))
    files["09_quality_gate.txt"] = "\n".join(f"{n}: {s}. {d}" for n, s, d in state["checks"])
    files["10_how_to_upload.txt"] = HOW_TO
    files["11_sheet_specification.txt"] = sheets.spec_text(prod, cur, biz)
    manifest = {name: hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()
                for name, data in files.items()}
    files["MANIFEST.txt"] = "\n".join(f"{h}  {n}" for n, h in manifest.items())
    files["README.txt"] = ("Made with Business Factory 5. Check every file yourself. Read the current Gumroad and "
                           "Pinterest rules before you publish. Upload and post manually. "
                           "Not legal, tax or accounting advice.\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, bytes) else data.encode("utf-8"))
    return buf.getvalue(), manifest
