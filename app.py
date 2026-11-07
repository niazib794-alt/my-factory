"""Business Factory 3 - Contractor Products. One app for phone and laptop.

Files: app.py (this file), sheets.py (workbook builder), requirements.txt.
Keys and duties: 'Keys, AI duties and routing' on the page, or Streamlit secrets.
Each AI slot has duties (what it is used for). A job goes first to the slots that have that
duty ticked. Other slots with keys act as backups. Every step keeps all its versions.
"""
import base64
import hashlib
import io
import json
import os
import random
import re
import time
import zipfile
from datetime import datetime

import requests
import streamlit as st

import sheets

st.set_page_config(page_title="Business Factory 3", page_icon="🧰", layout="centered")
st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 3rem; max-width: 960px;}
.stButton > button, .stDownloadButton > button {min-height: 46px; border-radius: 12px; font-weight: 700;}
div[data-testid="stTabs"] button {font-weight: 700;}
h1 {font-size: 1.7rem !important;}
@media (max-width: 700px) {
  .block-container {padding-left: .6rem; padding-right: .6rem;}
  h1 {font-size: 1.4rem !important;}
}
</style>
""", unsafe_allow_html=True)

ss = st.session_state
for _k, _v in {"ailog": [], "keystat": {}, "project": None, "out": None,
               "picture": None, "flash": None, "pending_sel": None}.items():
    if _k not in ss:
        ss[_k] = _v

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(BASE_DIR, "saved_projects")
SCHEMA = 4
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

PRODUCTS = {  # label shown to the owner -> product key used by sheets.py
    "1. Service Business Profit & Job Costing": "job_costing",
    "2. Contractor Extra Work Approval Tracker": "change_orders",
    "3. Contractor Invoice & Payment Collection": "receivables",
    "4. All-in-One Master Contractor Bundle": "bundle",
}
PRODUCT_LABEL = {v: k for k, v in PRODUCTS.items()}
AUDIENCES = ["Plumbers", "Electricians", "HVAC contractors", "General contractors",
             "Cleaning businesses", "Landscaping businesses", "Other service businesses"]
MARKETS = ["USA", "Canada", "United Kingdom", "European Union", "Australia"]
CURRENCIES = ["USD", "CAD", "GBP", "EUR", "AUD"]

DUTIES = ["Research", "Decide", "Guide", "Listing", "Pins", "Chat"]
SLOTS = [  # id, label, kind (gemini or openai-style), base URL, default duties
    {"id": "gem1", "label": "Gemini 1", "kind": "gemini", "base": "", "default": ["Research"]},
    {"id": "gem2", "label": "Gemini 2", "kind": "gemini", "base": "", "default": ["Guide"]},
    {"id": "gem3", "label": "Gemini 3", "kind": "gemini", "base": "", "default": ["Decide"]},
    {"id": "groq", "label": "Groq", "kind": "openai", "base": "https://api.groq.com/openai/v1",
     "default": ["Listing", "Pins"]},
    {"id": "mistral", "label": "Mistral", "kind": "openai", "base": "https://api.mistral.ai/v1", "default": []},
    {"id": "openrouter", "label": "OpenRouter", "kind": "openai", "base": "https://openrouter.ai/api/v1", "default": []},
    {"id": "cus1", "label": "Custom AI 1", "kind": "openai", "base": "", "default": ["Chat"]},
    {"id": "cus2", "label": "Custom AI 2", "kind": "openai", "base": "", "default": []},
    {"id": "cus3", "label": "Custom AI 3", "kind": "openai", "base": "", "default": []},
    {"id": "cus4", "label": "Custom AI 4", "kind": "openai", "base": "", "default": []},
]
SECRET_PREFIX = {"groq": "GROQ", "mistral": "MISTRAL", "openrouter": "OPENROUTER",
                 "cus1": "CUSTOM1", "cus2": "CUSTOM2", "cus3": "CUSTOM3", "cus4": "CUSTOM4"}
SLOT_MODEL_DEFAULT = {"groq": "llama-3.3-70b-versatile", "mistral": "mistral-large-latest",
                      "openrouter": "deepseek/deepseek-chat"}

STEPS = [("research", "Research", "Research"), ("decision", "Decision", "Decide"),
         ("guide", "Buyer guide", "Guide"), ("listing", "Listing", "Listing"), ("pins", "Pins", "Pins")]
STEP_JOB = {s: j for s, _, j in STEPS}
STEP_LABEL = {s: l for s, l, _ in STEPS}

QC_ITEMS = [
    "Every heading and column name is spelled correctly",
    "Yellow cells are inputs and blue cells are formulas",
    "Laptop file opened in Google Sheets on a laptop (test copy)",
    "Phone file opened in Google Sheets on a phone (test copy)",
    "Blank rows do not create misleading totals (tested with 2 sample rows)",
    "Dates, overdue days and partial payments checked",
    "Listing makes no claim the file cannot support (no income or result promises)",
    "No real customer data inside the file",
]
DOC_FILES = [
    ("01_research.txt", "research", "Research"),
    ("02_decision_and_price_test.txt", "decision", "Decision and price test"),
    ("03_sheet_specification.txt", None, "Sheet specification"),
    ("04_buyer_guide.txt", "guide", "Buyer guide"),
    ("05_gumroad_listing_and_faq.txt", "listing", "Gumroad listing and FAQ"),
    ("06_pins_optional.txt", "pins", "Pinterest pins (optional)"),
    ("07_quality_check.txt", None, "Quality check"),
    ("08_how_to_upload.txt", None, "How to upload"),
]
HOW_TO_UPLOAD = """HOW TO UPLOAD (simple steps)
1. Unzip the package on your computer or phone.
2. Choose the file: the laptop file (..._laptop.xlsx) for a computer, or the phone file (..._phone.xlsx) for a phone.
3. Upload it to Google Drive and open it with Google Sheets. Check that the formulas work in a copy.
4. Gumroad: create a new product. Upload the .xlsx file as the product file.
5. Paste the title, description and FAQ from file 05 into Gumroad. Set the price you decided in file 02.
6. Pinterest: post the pins from file 06 yourself. Add the Gumroad link when you post.
7. Read the quality check (file 07), tick the manual items, then publish.
Check the current Gumroad and Pinterest rules before you publish.
"""
RISKY = re.compile(r"\b(guarantee[sd]?|best[- ]?sellers?|cure[sd]?|diagnos\w*|medical|treat(?:s|ment)?|"
                   r"passive income|get rich|income guarantee)\b", re.I)

# ============================ AI ROLES (prompts) ============================
SHARED = """You help one owner (Bashir) sell Google Sheets workbooks to contractors and service businesses on Gumroad.
Buyers download an .xlsx file, open it in Google Sheets on a phone or laptop, and type their own numbers.
Owner-facing notes: simple Urdu. Buyer-facing text (listing, guide, FAQ, pins): simple English, short sentences.
EVIDENCE LABELS: SOURCE (with link and date), USER INPUT (pasted or uploaded by the owner), ESTIMATE (your reasoning), UNKNOWN.
Never invent search volumes, prices, sales, reviews, ratings, competitor counts, rankings or trend numbers.
Never promise sales, income or results. No legal, tax or accounting advice. Never copy competitor names, text or brands.
If OWNER FEEDBACK is given, it overrides earlier wording."""

RESEARCH_ROLE = """ROLE: evidence-first market analyst for one product.
Use only the USER INPUT and WEB EXTRACTS in the message. Anything from memory must be labelled ESTIMATE.
Sections:
1. Verdict: proceed, test or reject, with reasons and confidence.
2. Buyer and the job they want done.
3. Evidence table: claim, source or USER INPUT, label.
4. Demand signals: only what the input shows.
5. Competitors and substitutes: listing counts and prices only if sourced.
6. Gaps that existing products miss.
7. Keyword phrases buyers use (short, long, question), each labelled.
8. Risks and unknowns.
9. Three validation tests for the next 14 days."""

DECIDE_ROLE = """ROLE: product strategist. Give the single best next step for this product, with reasons.
Sections:
1. Verdict.
2. Buyer and their main pain (one sentence).
3. Why this product now, using USER INPUT and SOURCE items only.
4. Price test: three ranges in the given currency, each labelled ESTIMATE, with what each range is for.
5. Five workbook features that matter most to this buyer, in order.
6. Risks (at least three).
7. Fourteen-day test: what to post, where, how often; the numbers to record (views, saves, clicks, sales); the owner's go / no-go thresholds written as questions the owner must answer, not as facts."""

GUIDE_ROLE = """ROLE: buyer guide writer. The buyer is not technical and may use only a phone.
Sections: What you get (list the tabs). Before you start (Google account, open in Google Sheets). First 10 minutes (numbered steps). Colour guide. Each tab: what to type. Common mistakes and how to fix them. Dashboard: what each number means. FAQ (5 questions).
Short sentences. No tax or legal advice.
Use the SHEET SPECIFICATION exactly. Never describe a tab, column or formula that is not in it."""

LISTING_ROLE = """ROLE: Gumroad listing writer.
Output: 3 title options (product keyword first, no hype, under 70 characters); a 2-line hook; a description with what is included, who it is for, how to use in 3 steps, what it does NOT do, requirements (a Google account; Google Sheets or Excel); 8 tags; 5 FAQ questions with answers.
Say the file is for typing your own numbers, and that results depend on the user."""

PINS_ROLE = """ROLE: Pinterest copy writer.
Output: 5 pin ideas. Each has: headline (max 60 characters), text on image (max 8 words), description (2 sentences), board name, one call to action.
Then a 7-day posting plan for one person (one pin a day and one helpful tip). Platform tips are ideas, not rules."""

CHAT_ROLE = """ROLE: business assistant for the owner. Answer the question directly in simple Urdu.
Use the CONTEXT. For questions about the workbook, answer from the SHEET SPECIFICATION only.
If the owner asks to change the workbook, say exactly which tab and column would change, and that a change needs the code to be updated.
If something is not in the context, say so. Never invent data."""

SYS = {
    "Research": SHARED + "\n\n" + RESEARCH_ROLE,
    "Decide": SHARED + "\n\n" + DECIDE_ROLE,
    "Guide": SHARED + "\n\n" + GUIDE_ROLE,
    "Listing": SHARED + "\n\n" + LISTING_ROLE,
    "Pins": SHARED + "\n\n" + PINS_ROLE,
    "Chat": SHARED + "\n\n" + CHAT_ROLE,
}


# ============================ SMALL HELPERS ============================
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s)).strip("_")[:60] or "file"


def secret(name, default=""):
    try:
        v = st.secrets.get(name, default)
    except Exception:
        return default
    return str(v).strip() if v not in (None, "") else default


def scrub(err, keys):
    """Remove every key from an error message before it is shown or logged."""
    s = str(err)
    for k in keys:
        if k:
            s = s.replace(k, "***")
    return s[:300]


def img_mime(raw):
    return "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"


# ============================ AI CALLS ============================
def post_json(url, headers, body, timeout=120):
    for attempt in range(3):
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
        if r.status_code in (429, 500, 502, 503) and attempt < 2:
            time.sleep(2 ** attempt + random.random())
            continue
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
        return r.json()
    raise RuntimeError("no reply after retries")


def gemini_text(key, model, system, user, images=()):
    parts = [{"text": user}]
    for mime, raw in images:
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode("ascii")}})
    body = {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192}}
    data = post_json(f"{GEMINI}/models/{model}:generateContent",
                     {"Content-Type": "application/json", "x-goog-api-key": key}, body)
    try:
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Gemini blocked the reply or sent nothing")
    if not text.strip():
        raise RuntimeError("Gemini sent an empty reply")
    return text


def gemini_image(key, model, prompt):
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
    data = post_json(f"{GEMINI}/models/{model}:generateContent",
                     {"Content-Type": "application/json", "x-goog-api-key": key}, body, timeout=180)
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("no picture in the reply")
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    raise RuntimeError("the reply had no image")


def openai_text(base, key, model, system, user):
    data = post_json(base.rstrip("/") + "/chat/completions",
                     {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                     {"model": model, "temperature": 0.3,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("unexpected reply format")
    if not str(text or "").strip():
        raise RuntimeError("empty reply")
    return text


def tavily_search(key, query):
    data = post_json("https://api.tavily.com/search",
                     {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                     {"query": query[:300], "search_depth": "basic", "max_results": 6, "include_answer": True})
    out = []
    if data.get("answer"):
        out.append("TAVILY SUMMARY (open the links yourself): " + str(data["answer"]))
    for i, r in enumerate(data.get("results", []), 1):
        out.append(f"[{i}] {r.get('title', '')} | {r.get('url', '')}\n{str(r.get('content', ''))[:700]}")
    return "\n\n".join(out)


def gemini_model_names(key):
    r = requests.get(f"{GEMINI}/models?pageSize=200", headers={"x-goog-api-key": key}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return sorted(m["name"].split("/")[-1] for m in r.json().get("models", [])
                  if "generateContent" in m.get("supportedGenerationMethods", []))


def build_entries(cfg):
    """Slots that have a key and a model (and a base URL when needed)."""
    out = []
    for s in cfg["slots"]:
        if not s["key"] or not s["model"]:
            continue
        if s["kind"] == "openai" and not s["base"]:
            continue
        out.append(dict(s, vision=(s["kind"] == "gemini")))
    return out


def pick_entries(job, entries):
    """Slots with this duty first (in slot order), then the other ready slots as backups."""
    primary = [e for e in entries if job in e["duties"]]
    backup = [e for e in entries if job not in e["duties"]]
    return primary + backup


def call_entry(e, system, user, images=()):
    if e["kind"] == "gemini":
        return gemini_text(e["key"], e["model"], system, user, images)
    return openai_text(e["base"], e["key"], e["model"], system, user)


def log_ai(job, name, ok, note):
    ss["ailog"].append({"time": datetime.now().strftime("%H:%M:%S"), "job": job, "provider": name,
                        "result": "ok" if ok else "failed", "note": note[:140]})
    del ss["ailog"][:-200]
    ss["keystat"][name] = f"Works (last used for {job})" if ok else "Failed: " + note[:120]


def run_ai(job, system, user, images, cfg):
    """Ask the slots for this job in order. Returns (text, slot name)."""
    entries = build_entries(cfg)
    if not entries:
        raise RuntimeError("No AI slot is ready. Open 'Keys, AI duties and routing' and enter a key and a model name.")
    errs = []
    for e in pick_entries(job, entries):
        if images and not e["vision"]:
            continue
        try:
            text = call_entry(e, system, user, images)
            log_ai(job, e["name"], True, f"{len(text)} characters")
            return text, e["name"]
        except Exception as ex:
            msg = scrub(ex, cfg["all"])
            log_ai(job, e["name"], False, msg)
            errs.append(f"{e['name']}: {msg[:140]}")
    if images:
        raise RuntimeError("Screenshots need a Gemini slot with a key. " + "; ".join(errs))
    raise RuntimeError("; ".join(errs) or "No AI could answer.")


def test_all(cfg):
    for e in build_entries(cfg):
        try:
            call_entry(e, "Reply with the single word OK.", "Say OK.")
            log_ai("Test", e["name"], True, "test ok")
        except Exception as ex:
            log_ai("Test", e["name"], False, scrub(ex, cfg["all"]))


def web_for(cfg, query):
    if not cfg["tavily"]:
        st.warning("Tavily key not entered. Continuing without web search.")
        return ""
    try:
        out = tavily_search(cfg["tavily"], query)
        ss["keystat"]["Tavily"] = "Works"
        return out
    except Exception as e:
        ss["keystat"]["Tavily"] = "Failed: " + scrub(e, cfg["all"])[:120]
        st.warning("Web search failed. Continuing without it.")
        return ""


# ============================ PROJECTS AND VERSIONS ============================
def new_project(name, product, audience, markets, currency, business):
    stamp = now()
    return {"schema": SCHEMA, "id": hashlib.sha1(f"{name}{time.time()}".encode()).hexdigest()[:10],
            "name": name, "product": product, "audience": audience, "markets": list(markets),
            "currency": currency, "business": business, "created": stamp, "updated": stamp,
            "steps": {k: [] for k, _, _ in STEPS}, "builds": [], "chat": []}


def save_project(p):
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        p["updated"] = now()
        path = os.path.join(SAVE_DIR, p["id"] + ".json")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
        os.replace(path + ".tmp", path)
        return True, ""
    except Exception as e:
        return False, str(e)[:160]


def list_saved():
    out = []
    if os.path.isdir(SAVE_DIR):
        for fn in os.listdir(SAVE_DIR):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(SAVE_DIR, fn), encoding="utf-8") as f:
                        d = json.load(f)
                    out.append((d.get("updated", ""), d["id"], d.get("name", "?"),
                                PRODUCT_LABEL.get(d.get("product"), "?")))
                except Exception:
                    continue
    return sorted(out, reverse=True)


def apply_project(p):
    if not isinstance(p, dict) or p.get("product") not in sheets.PRODUCT_SHEETS or not isinstance(p.get("steps"), dict):
        raise ValueError("this file is not a Business Factory 3 project")
    for k, _, _ in STEPS:
        p["steps"].setdefault(k, [])
    p.setdefault("builds", [])
    p.setdefault("chat", [])
    ss["project"] = p
    ss["pending_sel"] = {
        "prod_sel": PRODUCT_LABEL[p["product"]],
        "cur_sel": p["currency"] if p.get("currency") in CURRENCIES else "USD",
        "biz_sel": p.get("business", "Contractor Business Toolkit"),
        "mk_sel": [m for m in p.get("markets", []) if m in MARKETS] or list(MARKETS),
        "aud_sel": p.get("audience") if p.get("audience") in AUDIENCES else "Other service businesses",
        "aud_other": p.get("audience", ""),
    }
    ss["out"] = None


def latest_in(proj, step):
    vers = proj["steps"].get(step, [])
    return vers[-1] if vers else None


def add_version(step, text, by, feedback):
    p = ss["project"]
    vers = p["steps"][step]
    v = {"v": len(vers) + 1, "at": now(), "by": by, "feedback": feedback.strip(), "text": text}
    vers.append(v)
    ok, err = save_project(p)
    return v, ok, err


def make_user(step, ctx):
    """Build the user message for one step from the owner's inputs and the saved versions."""
    proj = ss["project"]
    head = (f"Product area: {ctx['plabel']}\nTarget customer: {ctx['audience']}\n"
            f"Target markets: {ctx['mtxt']}\nCurrency: {ctx['currency']}\n\n")
    if step == "research":
        return (head + f"USER INPUT (research pasted from {ctx['source'] or 'the owner'}; "
                       f"check it, do not treat it as proof):\n{ctx['pasted'].strip()[:24000] or 'none'}\n\n"
                       f"WEB EXTRACTS:\n{ctx['web'][:12000] or 'none'}\n\n"
                       f"SCREENSHOTS: {ctx['shot_note']}")
    spec = sheets.spec_text(proj["product"], proj["currency"], proj["business"])
    if step == "decision":
        rv = latest_in(proj, "research")
        if not rv:
            return None
        return head + f"RESEARCH REPORT (check it, add no new facts):\n{rv['text'][:20000]}"
    if step == "guide":
        dv = latest_in(proj, "decision")
        if not dv:
            return None
        return head + f"DECISION:\n{dv['text'][:6000]}\n\nSHEET SPECIFICATION (use exactly this):\n{spec}"
    if step == "listing":
        dv = latest_in(proj, "decision")
        gv = latest_in(proj, "guide")
        if not dv:
            return None
        guide_part = gv["text"][:3000] if gv else "not made yet"
        return (head + f"DECISION:\n{dv['text'][:6000]}\n\nBUYER GUIDE (summary):\n{guide_part}\n\n"
                       f"SHEET SPECIFICATION:\n{spec[:4000]}")
    if step == "pins":
        lv = latest_in(proj, "listing")
        if not lv:
            return None
        return head + f"LISTING:\n{lv['text'][:6000]}"
    return None


def run_step(step, ctx, feedback, cfg, images=()):
    """Make the next version of one step. The previous version is passed in, so the AI improves it."""
    user = make_user(step, ctx)
    if user is None:
        st.warning(f"Make the previous step first, then {STEP_LABEL[step]}.")
        return False
    prev = latest_in(ss["project"], step)
    if prev:
        user += (f"\n\nPREVIOUS VERSION v{prev['v']} (already delivered). Improve it: keep what is correct, "
                 f"fix every problem in OWNER FEEDBACK, and do not repeat the same wording.\n"
                 f"{prev['text'][:9000]}")
    user += f"\n\nOWNER FEEDBACK: {feedback.strip() or 'none'}"
    job = STEP_JOB[step]
    try:
        with st.spinner(f"{STEP_LABEL[step]}..."):
            text, by = run_ai(job, SYS[job], user, list(images), cfg)
    except Exception as e:
        st.error(f"{STEP_LABEL[step]} did not finish. Earlier versions are kept. " + str(e)[:300])
        return False
    v, ok, err = add_version(step, text, by, feedback)
    st.success(f"{STEP_LABEL[step]} version {v['v']} is ready (answered by {by}).")
    if not ok:
        st.warning("Could not save to disk (" + err + "). Download the text now.")
    return True


def show_latest(step, label):
    v = latest_in(ss["project"], step)
    if not v:
        st.info("Not made yet.")
        return
    st.caption(f"{label}: version {v['v']} • {v['at']} • answered by {v['by']}")
    st.markdown(v["text"])
    st.download_button(f"Download {label} (.txt)", v["text"].encode("utf-8"),
                       file_name=f"{safe(label)}_v{v['v']}.txt", mime="text/plain",
                       key=f"dl_{step}_{v['v']}")


def history_expander(step, label):
    vers = ss["project"]["steps"].get(step, [])
    if len(vers) > 1:
        with st.expander(f"Earlier versions of {label} ({len(vers) - 1})"):
            for v in vers[:-1][::-1]:
                st.caption(f"v{v['v']} • {v['at']} • {v['by']} • feedback: {v['feedback'] or 'none'}")
                st.text(v["text"][:1500] + ("..." if len(v["text"]) > 1500 else ""))


# ============================ CHECKS AND PACKAGE ============================
def workbook_facts(xlsx):
    with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
        names = re.findall(r'<sheet [^>]*name="([^"]+)"', z.read("xl/workbook.xml").decode("utf-8"))
        formulas = sum(z.read(n).decode("utf-8").count("<f>") for n in z.namelist()
                       if n.startswith("xl/worksheets/sheet"))
    return names, formulas


def quality_checks(xl_laptop, xl_phone, proj, spec):
    out = []
    laptop = None
    try:
        laptop = workbook_facts(xl_laptop)
        names, formulas = laptop
        out.append(("Laptop file opens (.xlsx)", "PASS", f"{len(names)} tabs: " + ", ".join(names)))
        out.append(("Laptop file has formulas", "PASS" if formulas > 100 else "FAIL", f"{formulas} formula cells"))
        out.append(("Specification lists every tab", "PASS" if all(n in spec for n in names) else "FAIL",
                    "checked against the file"))
    except Exception as e:
        out.append(("Laptop file opens (.xlsx)", "FAIL", str(e)[:120]))
    try:
        phone = workbook_facts(xl_phone)
        same = laptop is not None and phone == laptop
        out.append(("Phone file opens and matches the laptop file", "PASS" if same else "FAIL",
                    f"{len(phone[0])} tabs, {phone[1]} formula cells"))
    except Exception as e:
        out.append(("Phone file opens (.xlsx)", "FAIL", str(e)[:120]))
    for label, step in (("Decision", "decision"), ("Buyer guide", "guide"),
                        ("Gumroad listing", "listing"), ("Pins", "pins")):
        v = latest_in(proj, step)
        if not v:
            out.append((f"{label} written", "WARNING", "not made yet"))
            continue
        hits = sorted({m.group(0).lower() for m in RISKY.finditer(v["text"])})
        out.append((f"{label}: no risky claims", "WARNING" if hits else "PASS", ", ".join(hits) or "none found"))
    lv = latest_in(proj, "listing")
    if lv:
        out.append(("Listing does not call the file free",
                    "WARNING" if re.search(r"\bfree\b", lv["text"], re.I) else "PASS",
                    "check the word FREE in the listing"))
    gv = latest_in(proj, "guide")
    if gv:
        out.append(("Guide says the file opens in Google Sheets",
                    "PASS" if "google sheets" in gv["text"].lower() else "WARNING", "buyers need this"))
    return out


def checks_text(checks):
    lines = ["QUALITY CHECK (automatic, from the latest build)", ""]
    lines += [f"- {n}: {s}. {d}" for n, s, d in checks]
    lines += ["", "MANUAL CHECKS (tick before you publish):"] + [f"[ ] {i}" for i in QC_ITEMS]
    return "\n".join(lines)


def build_zip(laptop, phone, base, spec, checks, proj):
    files = {f"{base}_laptop.xlsx": laptop, f"{base}_phone.xlsx": phone}
    for fname, step, label in DOC_FILES:
        if fname.startswith("03"):
            text = spec
        elif fname.startswith("07"):
            text = checks_text(checks)
        elif fname.startswith("08"):
            text = HOW_TO_UPLOAD
        else:
            v = latest_in(proj, step)
            text = (f"{label} - version {v['v']} ({v['at']}, answered by {v['by']})\n\n{v['text']}"
                    if v else f"{label}: not made yet.")
        files[fname] = text
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data.encode("utf-8") if isinstance(data, str) else data)
    return buf.getvalue()


def build_outputs(proj):
    """Make both workbooks, the checks and the ZIP package, and count it as a build."""
    pk, cur, biz = proj["product"], proj["currency"], proj["business"]
    laptop = sheets.build_workbook(pk, cur, biz, "laptop")
    phone = sheets.build_workbook(pk, cur, biz, "phone")
    spec = sheets.spec_text(pk, cur, biz)
    checks = quality_checks(laptop, phone, proj, spec)
    v = len(proj["builds"]) + 1
    proj["builds"].append({"v": v, "at": now(), "checks": checks})
    base = f"{safe(biz)}_{pk}_v{v}"
    pkg = build_zip(laptop, phone, base, spec, checks, proj)
    ok, err = save_project(proj)
    return {"v": v, "laptop": laptop, "phone": phone, "pkg": pkg, "base": base,
            "checks": checks, "saved": ok, "err": err}


# ============================ CHAT CONTEXT ============================
def chat_context(proj):
    def t(step, n):
        v = latest_in(proj, step)
        return v["text"][:n] if v else "not made yet"
    spec = sheets.spec_text(proj["product"], proj["currency"], proj["business"])[:3000]
    return (f"PRODUCT: {PRODUCT_LABEL[proj['product']]}\nCUSTOMER: {proj['audience']}\n"
            f"MARKETS: {', '.join(proj['markets'])}\nCURRENCY: {proj['currency']}\n\n"
            f"RESEARCH:\n{t('research', 2500)}\n\nDECISION:\n{t('decision', 2000)}\n\n"
            f"LISTING:\n{t('listing', 1500)}\n\nSHEET SPECIFICATION (from the workbook code):\n{spec}")


# ============================ CALLBACKS ============================
def cb_new():
    p = ss["prod_sel"]
    ss["project"] = new_project(f"{p} · {datetime.now():%d %b %H:%M}", PRODUCTS[p], ss["aud_sel"],
                                list(MARKETS), ss["cur_sel"], ss["biz_sel"])
    ss["out"] = None
    ok, err = save_project(ss["project"])
    ss["flash"] = ("success", "New project started.") if ok else ("warning", "Started, but not saved: " + err)


def cb_open(pid):
    try:
        with open(os.path.join(SAVE_DIR, pid + ".json"), encoding="utf-8") as f:
            apply_project(json.load(f))
        ss["flash"] = ("success", "Project opened. Every earlier version is still there.")
    except Exception as e:
        ss["flash"] = ("error", "Could not open: " + str(e)[:150])


def cb_open_upload():
    up = ss.get("proj_up")
    if up is None:
        ss["flash"] = ("warning", "Choose a backup file first.")
        return
    try:
        apply_project(json.loads(up.getvalue().decode("utf-8")))
        save_project(ss["project"])
        ss["flash"] = ("success", "Backup opened and saved on this server.")
    except Exception as e:
        ss["flash"] = ("error", "Could not open the backup: " + str(e)[:150])


# ============================ PAGE ============================
if ss["pending_sel"]:  # values set by 'Open project' are applied before the widgets are drawn
    for _k, _v in ss["pending_sel"].items():
        ss[_k] = _v
    ss["pending_sel"] = None

st.title("🧰 Business Factory 3")
st.caption("Contractor workbooks for Google Sheets: research, decision, guide, listing, workbook (laptop and phone), "
           "chat. You download and upload yourself. No sales or income guarantee.")
if ss["flash"]:
    kind, msg = ss["flash"]
    ss["flash"] = None
    getattr(st, kind)(msg)

c1, c2 = st.columns(2)
prod_label = c1.selectbox("Product", list(PRODUCTS), key="prod_sel")
aud_pick = c2.selectbox("Target customer", AUDIENCES, key="aud_sel")
audience = aud_pick
if aud_pick == "Other service businesses":
    audience = st.text_input("Describe the customer", "Small trade and service businesses", key="aud_other")
c3, c4 = st.columns(2)
currency = c3.selectbox("Currency", CURRENCIES, key="cur_sel")
business = c4.text_input("Your business name", secret("BRAND_NAME", "Contractor Business Toolkit"),
                         key="biz_sel").strip() or "Contractor Business Toolkit"
mkts = st.multiselect("Target markets", MARKETS, default=MARKETS, key="mk_sel")
mtxt = ", ".join(mkts) or "not chosen"

if ss["project"] is None:
    ss["project"] = new_project("My first project", PRODUCTS[prod_label], audience, mkts, currency, business)
proj = ss["project"]
proj.update(audience=audience, markets=list(mkts), currency=currency, business=business)
plabel = PRODUCT_LABEL[proj["product"]]
pkey = proj["product"]
if pkey != PRODUCTS[prod_label]:
    st.warning(f"This project is for: {plabel}. To work on the selected product, press 'New project' in the Projects tab.")
base_ctx = {"plabel": plabel, "audience": audience, "mtxt": mtxt, "currency": currency, "business": business}

# ---- keys, duties and routing (defines cfg for every tab below)
with st.expander("🔑 Keys, AI duties and routing (open once; keys stay in this browser session)"):
    st.caption("Each AI slot has a 'Used for' list. A job goes first to the slots that have that duty ticked. "
               "Other slots with keys are backups. You do not need every slot.")
    m1, m2 = st.columns(2)
    gem_model = m1.text_input("Gemini text model (used by Gemini 1 to 3)",
                              secret("GEMINI_MODEL", "gemini-2.5-flash"), key="gem_model").strip()
    img_model = m2.text_input("Gemini image model (optional)",
                              secret("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"), key="img_model").strip()
    slot_list = []
    for s in SLOTS:
        sid = s["id"]
        with st.container(border=True):
            st.markdown(f"**{s['label']}**")
            if s["kind"] == "gemini":
                key = st.text_input("API key", secret(f"GEMINI_KEY_{sid[-1]}"), type="password",
                                    key=f"k_{sid}").strip()
                name, base, model = s["label"], "", gem_model
            else:
                prefix = SECRET_PREFIX[sid]
                c1s, c2s = st.columns(2)
                if sid.startswith("cus"):
                    name = c1s.text_input("Name", secret(f"{prefix}_NAME", s["label"]), key=f"n_{sid}").strip() or s["label"]
                else:
                    name = s["label"]
                    c1s.text_input("Name", name, disabled=True, key=f"n_{sid}")
                key = c2s.text_input("API key", secret(f"{prefix}_KEY"), type="password", key=f"k_{sid}").strip()
                base = st.text_input("Base URL (OpenAI style)", secret(f"{prefix}_BASE", s["base"]),
                                     key=f"b_{sid}").strip()
                model = st.text_input("Model name", secret(f"{prefix}_MODEL", SLOT_MODEL_DEFAULT.get(sid, "")),
                                      key=f"m_{sid}").strip()
            duties = st.multiselect("Used for (duties)", DUTIES, default=s["default"], key=f"d_{sid}")
            slot_list.append({"id": sid, "name": name, "kind": s["kind"], "key": key,
                              "model": model, "base": base, "duties": duties})
    tav_key = st.text_input("Tavily key (web search for research, optional)", secret("TAVILY_KEY"),
                            type="password", key="tav_key").strip()
    cfg = {"slots": slot_list, "tavily": tav_key, "img_model": img_model}
    cfg["all"] = [x["key"] for x in slot_list if x["key"]] + ([tav_key] if tav_key else [])

    b1, b2, b3 = st.columns(3)
    if b1.button("Test all AI slots"):
        with st.spinner("Testing each slot..."):
            test_all(cfg)
    if b2.button("List Gemini models"):
        gk = next((x["key"] for x in slot_list if x["kind"] == "gemini" and x["key"]), "")
        if not gk:
            st.warning("Enter a Gemini key first.")
        else:
            try:
                st.code("\n".join(gemini_model_names(gk)) or "none")
            except Exception as e:
                st.error(scrub(e, cfg["all"]))
    if b3.button("Test Tavily (web search)"):
        if not tav_key:
            st.warning("Enter a Tavily key first.")
        else:
            try:
                tavily_search(tav_key, "printable spreadsheet test")
                ss["keystat"]["Tavily"] = "Works"
            except Exception as e:
                ss["keystat"]["Tavily"] = "Failed: " + scrub(e, cfg["all"])[:120]

    st.markdown("**Slot status** (keys are never shown)")
    rows = []
    for x in slot_list:
        status = ss["keystat"].get(x["name"])
        if not status:
            status = "Entered, not tested" if (x["key"] and x["model"]) else "Not ready (key or model missing)"
        rows.append({"Slot": x["name"], "Used for": ", ".join(x["duties"]) or "backup only", "Status": status})
    rows.append({"Slot": "Tavily", "Used for": "Web search for research",
                 "Status": ss["keystat"].get("Tavily") or ("Entered, not tested" if tav_key else "Not entered")})
    st.table(rows)
    st.markdown("**AI log (latest 30 calls: which slot did which job, and the result)**")
    log_rows = list(reversed(ss["ailog"][-30:]))
    st.table(log_rows or [{"time": "-", "job": "-", "provider": "-", "result": "-", "note": "no calls yet"}])

# ---- progress
parts = []
for key, label, _ in STEPS:
    v = latest_in(proj, key)
    parts.append(("✅ " if v else "⬜ ") + label + (f" v{v['v']}" if v else ""))
if proj["builds"]:
    parts.append(f"📦 package v{proj['builds'][-1]['v']}")
st.info(" | ".join(parts))

t_auto, t_res, t_dec, t_gui, t_lis, t_pin, t_bld, t_chat, t_proj = st.tabs(
    ["Auto", "1 Research", "2 Decision", "3 Guide", "4 Listing", "5 Pins", "6 Build & download", "7 Chat", "8 Projects"])

# ---- Auto: one button for the whole chain
with t_auto:
    st.subheader("Auto: one button makes everything")
    st.write("Order: research, decision, buyer guide, listing, pins, then both workbooks and the ZIP. "
             "Each step saves a new version. If a step fails, the steps before it are kept.")
    st.caption("Research uses the text you pasted in tab 1 (and screenshots, if attached). If you paste nothing and "
               "tick no web search, the latest saved research is used.")
    auto_web = st.checkbox("Also search the web with Tavily", value=False, key="auto_web")
    auto_q = st.text_input("Web search phrase", f"{plabel} printable spreadsheet template for contractors", key="auto_q")
    if st.button("Make everything now", type="primary", key="btn_auto"):
        ctx = dict(base_ctx, pasted=ss.get("pasted", "") or "", source=ss.get("src_name", "") or "",
                   web="", shot_note="none")
        imgs = [(f.type or "image/png", f.getvalue()) for f in (ss.get("shots") or [])[:10]]
        ctx["shot_note"] = f"{len(imgs)} attached (layout only)" if imgs else "none"
        has_new_research = bool(ctx["pasted"].strip()) or auto_web or bool(imgs)
        if not has_new_research and not latest_in(proj, "research"):
            st.warning("Paste research in tab 1 first, or tick web search, or attach a screenshot.")
        else:
            if auto_web:
                ctx["web"] = web_for(cfg, auto_q)
            bar = st.progress(0.0)
            steps_run = ["research", "decision", "guide", "listing", "pins"]
            stopped = False
            for i, step in enumerate(steps_run, 1):
                if step == "research" and not has_new_research:
                    bar.progress(i / (len(steps_run) + 1))
                    continue
                ok = run_step(step, ctx, "", cfg, imgs if step == "research" else ())
                bar.progress(i / (len(steps_run) + 1))
                if not ok:
                    st.error(f"Stopped at {STEP_LABEL[step]}. The earlier steps are saved.")
                    stopped = True
                    break
            if not stopped:
                ss["out"] = build_outputs(proj)
                bar.progress(1.0)
                st.success("Everything is ready. Download the files in tab 6 (laptop file, phone file, ZIP).")

# ---- 1 research
with t_res:
    st.subheader("1. Research")
    st.write("Research in Perplexity or any other tool, then paste the result here. Screenshots are optional.")
    pasted = st.text_area("Paste research here (Perplexity, another tool, or your own notes)", height=200, key="pasted")
    src_name = st.text_input("Which tool or source did this come from?", "Perplexity", key="src_name")
    shots = st.file_uploader("Optional screenshots (layout only, not proof of sales)",
                             type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="shots")
    use_web = st.checkbox("Also search the web with Tavily", value=False, key="use_web")
    query = st.text_input("Web search phrase", f"{plabel} printable spreadsheet template for contractors", key="q_web")
    fb_res = st.text_area("What was missing or wrong last time? (optional)", key="fb_research")
    if st.button("Make research version", type="primary", key="btn_res"):
        imgs = [(f.type or "image/png", f.getvalue()) for f in (shots or [])[:10]]
        ctx = dict(base_ctx, pasted=pasted, source=src_name, web="",
                   shot_note=f"{len(imgs)} attached (layout only)" if imgs else "none")
        if use_web:
            ctx["web"] = web_for(cfg, query)
        if not (pasted.strip() or ctx["web"] or imgs or latest_in(proj, "research")):
            st.warning("Paste your research first (or tick web search, or add a screenshot).")
        else:
            run_step("research", ctx, fb_res, cfg, imgs)
    show_latest("research", "Research")
    history_expander("research", "research")

# ---- 2 decision
with t_dec:
    st.subheader("2. Decision and price test")
    fb_dec = st.text_area("What should change in the decision? (optional)", key="fb_decision")
    if st.button("Make decision version", type="primary", key="btn_dec"):
        run_step("decision", base_ctx, fb_dec, cfg)
    show_latest("decision", "Decision and price test")
    history_expander("decision", "decision")

# ---- 3 buyer guide
with t_gui:
    st.subheader("3. Buyer guide (for the person who buys the file)")
    fb_gui = st.text_area("What should change in the guide? (optional)", key="fb_guide")
    if st.button("Make buyer guide version", type="primary", key="btn_gui"):
        run_step("guide", base_ctx, fb_gui, cfg)
    show_latest("guide", "Buyer guide")
    history_expander("guide", "buyer guide")

# ---- 4 listing
with t_lis:
    st.subheader("4. Gumroad listing and FAQ")
    fb_lis = st.text_area("What should change in the listing? (optional)", key="fb_listing")
    if st.button("Make listing version", type="primary", key="btn_lis"):
        run_step("listing", base_ctx, fb_lis, cfg)
    show_latest("listing", "Gumroad listing")
    history_expander("listing", "listing")

# ---- 5 pins (optional) and picture
with t_pin:
    st.subheader("5. Pinterest pins (optional)")
    st.caption("You can also make pins with any other AI tool. Text on pictures can be wrong, so add words in Canva or your own tool.")
    fb_pin = st.text_area("What should change in the pins? (optional)", key="fb_pins")
    if st.button("Make pins version", type="primary", key="btn_pin"):
        run_step("pins", base_ctx, fb_pin, cfg)
    show_latest("pins", "Pinterest pins")
    history_expander("pins", "pins")
    with st.expander("Optional picture (Gemini image model)"):
        idea = st.text_input("What to draw", "simple flat illustration of a clipboard and a tool bag, plain light background",
                             key="pic_idea")
        if st.button("Make picture", key="btn_pic"):
            gk = next((x["key"] for x in slot_list if x["kind"] == "gemini" and x["key"]), "")
            if not gk or not img_model:
                st.warning("Enter a Gemini key and an image model name in 'Keys, AI duties and routing'.")
            else:
                try:
                    with st.spinner("Drawing..."):
                        ss["picture"] = gemini_image(gk, img_model, idea + ". Original art only. No text, no letters, "
                                                     "no numbers, no logo, no watermark.")
                except Exception as e:
                    st.error("Picture failed: " + scrub(e, cfg["all"]))
        if ss["picture"]:
            st.image(ss["picture"])
            st.download_button("Download picture", ss["picture"],
                               file_name="pinterest_picture." + ("png" if img_mime(ss["picture"]) == "image/png" else "jpg"),
                               mime=img_mime(ss["picture"]), key="dl_pic")

# ---- 6 build and download (laptop file, phone file, ZIP)
with t_bld:
    st.subheader("6. Build the workbooks and the package")
    st.write("This makes two Google Sheets files with the same formulas: a laptop file and a phone file. "
             "It also makes a ZIP with both files and 8 documents: research, decision, specification, buyer guide, "
             "listing, pins, quality check and upload steps.")
    for tab_name, headers in sheets.outline(pkey).items():
        with st.expander(f"Tab: {tab_name} ({len(headers)} columns)"):
            st.write(" | ".join(headers))
    missing = [label for key, label, _ in STEPS[:4] if not latest_in(proj, key)]
    if missing:
        st.warning("Still missing for a complete package: " + ", ".join(missing) + ". You can still build the files now.")
    if st.button("Build laptop and phone files and package", type="primary", key="btn_build"):
        try:
            with st.spinner("Building..."):
                ss["out"] = build_outputs(proj)
            msg = f"Build v{ss['out']['v']} is ready."
            st.success(msg if ss["out"]["saved"] else msg + " Not saved to disk: " + ss["out"]["err"])
        except Exception as e:
            st.error("Build failed. Earlier versions are kept. " + str(e)[:300])
    out = ss["out"]
    if out:
        st.download_button("💻 Download the laptop file (.xlsx)", out["laptop"],
                           file_name=out["base"] + "_laptop.xlsx", mime=XLSX_MIME, key="dl_laptop")
        st.download_button("📱 Download the phone file (.xlsx)", out["phone"],
                           file_name=out["base"] + "_phone.xlsx", mime=XLSX_MIME, key="dl_phone")
        st.download_button("📦 Download everything (.zip)", out["pkg"],
                           file_name=out["base"] + ".zip", mime="application/zip", key="dl_zip")
        st.markdown("**Automatic checks (this build)**")
        for n, s, d in out["checks"]:
            st.write(f"- {n}: **{s}**. {d}")
    st.markdown("**Manual checks (tick before you publish)**")
    for i, item in enumerate(QC_ITEMS):
        st.checkbox(item, key=f"qc{i}")

# ---- 7 chat
with t_chat:
    st.subheader("7. Chat")
    st.caption("Write in Urdu or English, or use the microphone on your keyboard. The assistant knows your research, "
               "decision, listing and the sheet specification.")
    for m in proj["chat"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    msg = st.chat_input("Type your question or instruction...")
    if msg:
        proj["chat"].append({"role": "user", "content": msg})
        hist = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in proj["chat"][-10:])
        try:
            with st.spinner("Thinking..."):
                out_text, by = run_ai("Chat", SYS["Chat"] + "\n\nCONTEXT:\n" + chat_context(proj),
                                      hist + "\n\nAnswer the last USER message.", [], cfg)
            proj["chat"].append({"role": "assistant", "content": f"{out_text}\n\n*(answered by {by})*"})
        except Exception as e:
            proj["chat"].append({"role": "assistant", "content": "The chat did not finish: " + str(e)[:300]})
        proj["chat"] = proj["chat"][-60:]
        save_project(proj)
        st.rerun()
    if proj["chat"] and st.button("Clear this chat", key="btn_clear_chat"):
        proj["chat"] = []
        save_project(proj)
        st.rerun()

# ---- 8 projects
with t_proj:
    st.subheader("8. Saved projects")
    st.caption("Every project keeps all its versions. A new version is improved from the last one. "
               "Old versions are never deleted.")
    st.button("New project for the selected product", on_click=cb_new, key="btn_new")
    saved = list_saved()
    if not saved:
        st.info("No saved projects yet.")
    for upd, pid, name, plab in saved:
        a, b = st.columns([3, 1])
        a.write(f"**{name}** · {plab} · saved {upd}")
        b.button("Open", key=f"open_{pid}", ok=cb_open, args=(pid,))
    st.divider()
    st.download_button("⬇️ Download this project as a backup file (.json)",
                       json.dumps(proj, ensure_ascii=False, indent=2).encode("utf-8"),
                       file_name=f"{safe(proj['name'])}_backup.json", mime="application/json", key="dl_backup")
    st.file_uploader("Open a backup file", type=["json"], key="proj_up")
    st.button("Open the uploaded backup", on_click=cb_open_upload, key="btn_open_up")
