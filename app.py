"""Business Factory 5 - one app for phone and laptop.

Files: app.py (this file), brains.py (the ten brains), engine.py (AI slots and duties),
sheets.py (workbooks), store.py (saving), requirements.txt, README_URDU.txt.
API keys: the left sidebar (the >> button at the top left on a phone).
"""
import io
import zipfile

import streamlit as st

import brains
import engine
import store

st.set_page_config(page_title="Business Factory 5", page_icon="🧰", layout="centered")
st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1000px;}
.bf-hero {background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%); color: #ffffff;
          border-radius: 18px; padding: 18px 20px; margin-bottom: 12px;}
.bf-hero h2 {margin: 0; color: #ffffff; font-size: 1.5rem;}
.bf-hero p {margin: 4px 0 0 0; opacity: .88; font-size: .92rem;}
.bf-chip {display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: .78rem;
          font-weight: 700; margin-right: 6px; color: #ffffff;}
.stButton > button, .stDownloadButton > button {min-height: 46px; border-radius: 12px; font-weight: 700;}
div[data-testid="stMetric"] {border: 1px solid #e2e8f0; border-radius: 14px; padding: 10px 12px;}
@media (max-width: 700px) {
  .block-container {padding-left: .6rem; padding-right: .6rem;}
  .bf-hero h2 {font-size: 1.25rem;}
}
</style>
""", unsafe_allow_html=True)

THEME_COLOURS = {"blue": "#1E3A8A", "green": "#166534", "purple": "#5B21B6",
                 "teal": "#0F766E", "amber": "#92400E", "rose": "#9F1239"}
AUTO = "Auto: the brains choose"
TITLE_TO_KEY = {v: k for k, v in brains.PRODUCT_TITLES.items()}
CURRENCIES = ["USD", "CAD", "GBP", "EUR", "AUD"]
MARKETS = ["USA", "Canada", "United Kingdom", "European Union", "Australia"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

ss = st.session_state
for _k, _v in {"log": [], "pkg": None, "pkg_name": "", "flash": None}.items():
    if _k not in ss:
        ss[_k] = _v


def secret(name, default=""):
    try:
        v = st.secrets.get(name, default)
    except Exception:
        return default
    return str(v).strip() if v not in (None, "") else default


def member(zip_bytes, suffix):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for n in z.namelist():
            if n.endswith(suffix):
                return n, z.read(n)
    return None, None


def google_test_zip(zip_bytes):
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for n in src.namelist():
            if n.startswith("google_test/"):
                dst.writestr(n.split("/", 1)[1], src.read(n))
    return buf.getvalue()


# ---------------- sidebar: API keys and duties (left side)
with st.sidebar:
    st.header("🔑 API keys and duties")
    st.caption("Keys stay in this browser session. For a private app, put them in Streamlit secrets. "
               "Each slot does the jobs ticked under 'Used for'. Other ready slots are backups.")
    slots = []
    for d in engine.SLOT_DEFS:
        sid = d["id"]
        with st.expander(d["label"], expanded=False):
            if d["kind"] == "gemini":
                key = st.text_input("API key", secret(f"GEMINI_KEY_{sid[-1]}"), type="password",
                                    key=f"key_{sid}").strip()
                model = st.text_input("Model", secret("GEMINI_MODEL", "gemini-2.5-flash"),
                                      key=f"model_{sid}").strip()
                base, name = "", d["label"]
            else:
                pre = engine.SECRET_PREFIX.get(sid, "")
                key = st.text_input("API key", secret(f"{pre}_KEY"), type="password", key=f"key_{sid}").strip()
                if sid.startswith("cus"):
                    name = st.text_input("Name (for example: Perplexity)", secret(f"{pre}_NAME", d["label"]),
                                         key=f"name_{sid}").strip() or d["label"]
                else:
                    name = d["label"]
                base = st.text_input("Base URL (OpenAI style)", secret(f"{pre}_BASE", d["base"]),
                                     key=f"base_{sid}").strip()
                model = st.text_input("Model", secret(f"{pre}_MODEL", engine.MODEL_DEFAULT.get(sid, "")),
                                      key=f"model_{sid}").strip()
            duties = st.multiselect("Used for", engine.DUTIES, default=d["default"], key=f"duty_{sid}")
        slots.append({"id": sid, "name": name, "kind": d["kind"], "key": key, "model": model,
                      "base": base, "duties": duties})
    tav_key = st.text_input("Tavily key (web search, optional)", secret("TAVILY_KEY"), type="password",
                            key="tav_key").strip()

keys_all = [s["key"] for s in slots if s["key"]] + ([tav_key] if tav_key else [])

# ---------------- project in memory
if "proj" not in ss:
    ss["proj"] = store.new_project("My first project", "Plumbers and electricians", "USD",
                                   secret("BRAND_NAME", "Contractor Business Toolkit"), ["USA"])
proj = ss["proj"]


def _sync_widgets(p):
    ss["aud"], ss["cur"], ss["biz"] = p["audience"], p["currency"], p["business"]
    ss["mk"] = [m for m in p["markets"] if m in MARKETS] or ["USA"]
    ss["compl"] = "\n".join(p["complaints"])


def cb_new():
    p = store.new_project(f"New project {store.now()}", ss.get("aud", ""), ss.get("cur", "USD"),
                          ss.get("biz", "Contractor Business Toolkit"), ss.get("mk", ["USA"]))
    ss["proj"] = p
    store.save_project(p)
    _sync_widgets(p)
    ss["flash"] = ("success", "New project started. Earlier projects stay saved.")


def cb_open(pid):
    try:
        p = store.load_project(pid)
    except Exception as e:
        ss["flash"] = ("error", "Could not open: " + str(e)[:150])
        return
    ss["proj"] = p
    _sync_widgets(p)
    ss["flash"] = ("success", "Project opened. Every earlier version is still there.")


def cb_restore():
    up = ss.get("restore_up")
    if up is None:
        ss["flash"] = ("warning", "Choose a backup file first.")
        return
    try:
        p = store.import_bytes(up.getvalue())
    except Exception as e:
        ss["flash"] = ("error", "Could not restore: " + str(e)[:150])
        return
    ss["proj"] = p
    store.save_project(p)
    _sync_widgets(p)
    ss["flash"] = ("success", "Backup restored and saved on this server.")


# ---------------- header
answered = len([c for c in proj.get("complaint_log", []) if c.get("status") == "answered"])
st.markdown(
    f"""<div class="bf-hero"><h2>🧰 Business Factory 5</h2>
    <p>Research, decision, two workbooks (laptop and phone), listing, guide, pins, checks and a ZIP.
    You approve, then upload yourself. No sales or income is promised.</p></div>""",
    unsafe_allow_html=True)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Approved versions", len(proj["versions"]))
m2.metric("Today", f"{len(store.approved_today())} of {store.DAILY_LIMIT}")
m3.metric("Open complaints", len(proj["complaints"]))
m4.metric("Complaints answered", answered)
if ss["flash"]:
    kind, msg = ss["flash"]
    ss["flash"] = None
    getattr(st, kind)(msg)

tab_make, tab_results, tab_projects, tab_chat, tab_api, tab_log = st.tabs(
    ["Make today's product", "Results", "Projects", "Chat", "API testing", "Daily log"])

# ================= TAB: make today's product
with tab_make:
    st.markdown("#### 1. Product and customer")
    c1, c2 = st.columns(2)
    prod_choice = c1.selectbox("Product", [AUTO] + list(brains.PRODUCT_TITLES.values()), key="prod_sel")
    audience = c2.text_input("Target customer", proj["audience"], key="aud")
    c3, c4 = st.columns(2)
    currency = c3.selectbox("Currency", CURRENCIES,
                            index=CURRENCIES.index(proj["currency"]) if proj["currency"] in CURRENCIES else 0,
                            key="cur")
    business = c4.text_input("Business name (only in the Settings tab and file names)", proj["business"],
                             key="biz").strip() or "Contractor Business Toolkit"
    markets = st.multiselect("Markets", MARKETS, default=[m for m in proj["markets"] if m in MARKETS] or ["USA"],
                             key="mk")
    proj.update(audience=audience, currency=currency, business=business, markets=list(markets))
    fixed_key = None if prod_choice == AUTO else TITLE_TO_KEY[prod_choice]

    st.markdown("#### 2. Research")
    mode = st.radio("Research source", ["I will paste my own research", "AI researches on its own"],
                    horizontal=True, key="rmode")
    pasted = st.text_area("Paste research (Perplexity, another tool, or your notes)", height=140,
                          key="pasted") if mode.startswith("I") else ""
    source = st.text_input("Which tool or source did it come from?", "Perplexity", key="src")
    c5, c6 = st.columns(2)
    use_web = c5.checkbox("Web search with Tavily", value=bool(tav_key), key="webon")
    use_gem = c6.checkbox("Gemini live Google search (brain 1)", value=False, key="gemweb",
                          help="Gemini searches the web and returns links. Those links are shown as sources.")
    shots = st.file_uploader("Screenshots (optional, layout only, not proof of sales)",
                             type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="shots")

    st.markdown("#### 3. Buyer complaints")
    complaints_text = st.text_area("Open complaints or wishes (one per line)", "\n".join(proj["complaints"]),
                                   key="compl")
    complaints = [x.strip() for x in complaints_text.splitlines() if x.strip()]
    proj["complaints"] = complaints
    st.caption(f"Answered so far: {answered}. Answered complaints move to the log in the Projects tab.")

    st.markdown("#### 4. Options")
    notes = st.text_input("Notes for this run (optional)", key="notes")
    pins_on = st.checkbox("Make Pinterest pins too", value=True, key="pins_on")
    allow_second = st.checkbox("Allow a second approved product today", value=False, key="second")

    b1, b2 = st.columns(2)
    run_clicked = b1.button("Make today's product", type="primary", key="btn_run")
    resume_clicked = b2.button("Continue from where it stopped", key="btn_resume")

    if run_clicked:
        if len(store.approved_today()) >= store.DAILY_LIMIT and not allow_second:
            st.warning("One product is already approved today. Tick 'allow a second product today' to make another.")
        else:
            web_text, web_items = "", []
            if use_web and tav_key:
                try:
                    with st.spinner("Searching the web..."):
                        web_text = engine.tavily(tav_key, f"{audience} {currency} contractor spreadsheet", web_items)
                except Exception as e:
                    st.warning("Web search failed; continuing without it: " + engine.scrub(e, keys_all))
            state = brains.new_state(fixed_key)
            state["product_fixed"] = fixed_key is not None
            state["pins_on"] = pins_on
            state["inputs"] = {"mode": mode, "pasted": pasted or "", "source": source, "web_text": web_text,
                               "web_items": web_items, "gemini_search": bool(use_gem), "gemini_sources": []}
            proj["run"] = state
            resume_clicked = True
    if resume_clicked and proj.get("run") is None:
        st.info("Nothing to continue. Press 'Make today's product'.")
    elif resume_clicked:
        state = proj["run"]
        if state["status"] == "waiting_approval":
            st.info("This product is waiting for your approval below.")
        else:
            inp = state.get("inputs", {})
            imgs = [(f.type or "image/png", f.getvalue()) for f in (shots or [])[:10]]
            prev = proj["versions"][-1] if proj["versions"] else None
            ctx = {
                "product": state["product"] if state.get("product_fixed") else None,
                "product_fixed": bool(state.get("product_fixed")),
                "product_title": brains.PRODUCT_TITLES.get(state["product"], "one of the four products (the brain chooses)")
                if state.get("product_fixed") else "one of the four products (the brain chooses)",
                "audience": audience, "currency": currency, "business": business,
                "markets": ", ".join(markets) or "not chosen",
                "research_text": inp.get("pasted", ""), "source": inp.get("source", ""),
                "web_text": inp.get("web_text", ""),
                "shot_note": f"{len(imgs)} attached (layout only)" if imgs else "none",
                "images": imgs, "complaints": complaints, "prev": prev,
                "prev_theme": prev["theme"] if prev else None,
                "recent": store.last_versions(proj), "results_text": store.results_summary(proj),
                "slots": slots, "log": ss["log"], "keys": keys_all,
                "owner_notes": notes or proj.get("pending_notes", ""), "fix_notes": [],
                "grounding": bool(inp.get("gemini_search")), "sources": list(inp.get("gemini_sources", [])),
            }
            proj["pending_notes"] = ""
            with st.spinner("The brains are working. Each step is saved, so a stop can be continued."):
                status = brains.run_pipeline(state, ctx, lambda s: store.save_project(proj), pins_on=pins_on)
            inp["gemini_sources"] = ctx["sources"]
            state["inputs"] = inp
            store.save_project(proj)
            if status == "error":
                st.error("A brain stopped. Read the message below, then press 'Continue from where it stopped'.")
            elif status == "waiting_approval":
                st.success("The gate passed. Read the checks below, then approve.")
            elif status == "blocked":
                st.error("The gate blocked this product. Read the reasons below, then send it back with notes.")

    state = proj.get("run")
    if state:
        total = 8 if state.get("pins_on", True) else 7
        done = len([k for k in state["brains"] if int(k) <= 8])
        st.progress(min(done / total, 1.0), text=f"{done} of {total} brains done · status: {state['status']}")
        inp = state.get("inputs", {})
        with st.expander("Research used in this run", expanded=bool(inp)):
            st.write(f"- Pasted research: {len(inp.get('pasted', ''))} characters (source: {inp.get('source', '') or 'owner'})")
            st.write(f"- Web search (Tavily): {len(inp.get('web_items', []))} results")
            st.write(f"- Gemini live search: {'on' if inp.get('gemini_search') else 'off'}, sources found: {len(inp.get('gemini_sources', []))}")
            for s_ in inp.get("gemini_sources", [])[:8]:
                st.write(f"  - {s_.get('title', '')} {s_.get('url', '')}")
            for w_ in inp.get("web_items", [])[:8]:
                st.write(f"  - {w_.get('title', '')} {w_.get('url', '')}")
            if "1" in state["brains"]:
                st.caption(f"Brain 1 answered by: {state['brains']['1']['slot']}")

        st.markdown("#### Brains")
        rows = []
        for n in range(1, 9):
            if n == 8 and not state.get("pins_on", True) and "8" not in state["brains"]:
                continue
            b = state["brains"].get(str(n))
            rows.append({"brain": n, "name": brains.BRAIN_NAMES[n], "status": "done" if b else "waiting",
                         "answered by": b["slot"] if b else state["slots"].get(str(n), "")})
        rows.append({"brain": 9, "name": "Critic and gate", "status": "done" if state.get("checks") else "waiting",
                     "answered by": "code (+ AI critic if ready)"})
        rows.append({"brain": 10, "name": "Package", "status": "after approval", "answered by": "code"})
        st.table(rows)
        for e in state.get("errors", []):
            st.error(f"Brain {e['brain']} ({e['name']}) at {e['at']}: {e['msg']}")
        if state.get("product"):
            st.caption(f"Product: {brains.PRODUCT_TITLES.get(state['product'], state['product'])} · "
                       f"Fix rounds used: {state.get('fix_round', 0)}")

        if state["status"] in ("waiting_approval", "blocked") and "3" in state["brains"]:
            plan = state["brains"]["3"]["data"]
            theme = plan["theme"]
            st.markdown(f"<span class='bf-chip' style='background:{THEME_COLOURS.get(theme, '#173B75')}'>"
                        f"theme: {theme}</span> **Plan:** {plan['summary']}", unsafe_allow_html=True)
            if plan.get("results_considered"):
                st.info(f"What past results taught: {plan['results_considered']}")
            st.markdown("**What is different from the last version**")
            for c in plan["changes"]:
                st.write(f"- {c['type']}: {c['what']} ({c['why']})")
            st.markdown("**Gate checks**")
            st.table([{"check": n, "result": s, "detail": d} for n, s, d in state["checks"]])
            for p_ in state.get("problems", []):
                st.warning(p_)
            with st.expander("Read the brain outputs"):
                for n in sorted(state["brains"], key=int):
                    st.markdown(f"**Brain {n}: {brains.BRAIN_NAMES[int(n)]}** (answered by {state['brains'][n]['slot']})")
                    st.json(state["brains"][n]["data"], expanded=False)

            if state["status"] == "waiting_approval":
                if st.button("Approve and save this product", type="primary", key="btn_approve"):
                    version_no = len(proj["versions"]) + 1
                    zip_bytes, manifest = brains.build_package({"currency": currency, "business": business},
                                                               state, version_no)
                    types = sorted({c["type"] for c in plan["changes"]})
                    proj["versions"].append({
                        "v": version_no, "date": store.today(), "at": store.now(), "product": state["product"],
                        "theme": theme, "types": types, "summary": plan["summary"],
                        "results_considered": plan.get("results_considered", ""),
                        "brains": state["brains"], "checks": state["checks"], "manifest": manifest,
                        "results": [], "approved": True})
                    store.archive_complaints(proj, version_no, "complaint_fix" in types)
                    proj["run"] = None
                    store.save_project(proj)
                    backup = store.backup_version(proj, version_no)
                    store.record_daily({"date": store.today(), "project": proj["id"], "v": version_no,
                                        "product": state["product"], "theme": theme, "types": types,
                                        "approved": True})
                    ss["pkg"], ss["pkg_name"] = zip_bytes, f"{store.today()}_{state['product']}_v{version_no}"
                    ss["flash"] = ("success", f"Version {version_no} approved. Backup saved: {backup}")
                    st.rerun()
            notes_back = st.text_input("Send back with notes (the brains redo the plan and the text)",
                                       key="sendback")
            if st.button("Send back with these notes", key="btn_sendback") and notes_back.strip():
                for n in range(3, 9):
                    state["brains"].pop(str(n), None)
                state["status"] = "idle"
                state["fix_round"] = 0
                proj["pending_notes"] = notes_back.strip()
                store.save_project(proj)
                st.info("Sent back. Press 'Continue from where it stopped'.")

    if ss.get("pkg") and ss.get("pkg_name"):
        st.markdown("#### Downloads")
        name, data = member(ss["pkg"], "_laptop.xlsx")
        if data:
            st.download_button("💻 Laptop file (.xlsx)", data, file_name=name.split("/")[-1], mime=XLSX_MIME,
                               key="dl_laptop")
        name, data = member(ss["pkg"], "_phone.xlsx")
        if data:
            st.download_button("📱 Phone file (.xlsx)", data, file_name=name.split("/")[-1], mime=XLSX_MIME,
                               key="dl_phone")
        st.download_button("🧪 Google test files (3 versions, zip)", google_test_zip(ss["pkg"]),
                           file_name=ss["pkg_name"] + "_google_test.zip", mime="application/zip", key="dl_gtest")
        st.download_button("📦 Everything (zip)", ss["pkg"], file_name=ss["pkg_name"] + ".zip",
                           mime="application/zip", key="dl_zip")
        st.caption("Test the three Google files first: upload each to Google Drive and open it with Google Sheets "
                   "(or Excel). Tell me which one opens and which one hangs.")

    if proj["versions"]:
        st.markdown("#### Approved versions of this project")
        for v in reversed(proj["versions"]):
            chip = THEME_COLOURS.get(v["theme"], "#173B75")
            st.markdown(f"<span class='bf-chip' style='background:{chip}'>v{v['v']}</span> "
                        f"{v['date']} · {v['product']} · {v['theme']} · {', '.join(v['types'])}",
                        unsafe_allow_html=True)

# ================= TAB: results
with tab_results:
    st.subheader("Results from your own numbers")
    st.caption(f"Enter the Pinterest and Gumroad numbers for each version. The brains judge a version only after "
               f"{store.MIN_VIEWS} views, and never decide from a tiny sample.")
    if not proj["versions"]:
        st.info("No approved version yet. Results appear after you approve a product.")
    else:
        options = {f"v{v['v']} · {v['product']} · {v['theme']} · {v['date']}": v["v"] for v in proj["versions"]}
        pick = st.selectbox("Version", list(options.keys()), key="res_pick")
        c1, c2 = st.columns(2)
        day = c1.text_input("Date", store.today(), key="res_date")
        views = c2.number_input("Views", min_value=0, step=1, value=0, key="res_views")
        c3, c4, c5 = st.columns(3)
        saves = c3.number_input("Saves", min_value=0, step=1, value=0, key="res_saves")
        clicks = c4.number_input("Clicks", min_value=0, step=1, value=0, key="res_clicks")
        sales = c5.number_input("Sales", min_value=0, step=1, value=0, key="res_sales")
        if st.button("Save these numbers", type="primary", key="btn_res"):
            try:
                store.add_result(proj, options[pick], day, views, saves, clicks, sales)
                store.save_project(proj)
                st.success("Saved. The next run will read these numbers.")
            except Exception as e:
                st.error(str(e))
    rows = store.results_rows(proj)
    if rows:
        st.table(rows)
    st.caption("Rules: under 100 views is not judged. No sale after 100 views means keep testing, not change everything.")

# ================= TAB: projects
with tab_projects:
    st.subheader("Saved projects")
    st.caption("Every project keeps all its approved versions. Nothing is deleted.")
    st.button("New project", on_click=cb_new, key="btn_new")
    saved = store.list_projects()
    if not saved:
        st.info("No saved projects yet.")
    for upd, pid, name, nv in saved:
        a, b = st.columns([3, 1])
        a.write(f"**{name}** · {nv} approved · saved {upd}")
        b.button("Open", key=f"open_{pid}", on_click=cb_open, args=(pid,))
    st.divider()
    st.download_button("⬇️ Backup of this project (.json)", store.export_bytes(proj),
                       file_name=f"{proj['name'][:30].replace(' ', '_')}_backup.json", mime="application/json",
                       key="dl_backup")
    st.file_uploader("Restore from a backup file", type=["json"], key="restore_up")
    st.button("Restore this backup", on_click=cb_restore, key="btn_restore")
    st.subheader("Automatic backups (made on every approval)")
    backups = store.list_backups()
    if not backups:
        st.info("No automatic backups yet.")
    for name in backups[-20:][::-1]:
        st.download_button(f"⬇️ {name}", store.backup_bytes(name), file_name=name, mime="application/json",
                           key=f"bk_{name}")

# ================= TAB: chat
with tab_chat:
    st.subheader("Chat")
    st.caption("Ask in Urdu or English. The chat knows this project: versions, results and open complaints.")
    for m in proj["chat"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    msg = st.chat_input("Ask about the product, the research, the workbook, or the next step")
    if msg:
        proj["chat"].append({"role": "user", "content": msg})
        last = proj["versions"][-1] if proj["versions"] else None
        context = (f"PRODUCT TITLES: {', '.join(brains.PRODUCT_TITLES.values())}\n"
                   f"AUDIENCE: {proj['audience']} | CURRENCY: {proj['currency']} | MARKETS: {', '.join(proj['markets'])}\n"
                   f"OPEN COMPLAINTS: {'; '.join(proj['complaints']) or 'none'}\n"
                   f"ANSWERED COMPLAINTS: {'; '.join(c['text'] for c in proj.get('complaint_log', [])) or 'none'}\n"
                   f"RESULTS:\n{store.results_summary(proj)}\n"
                   f"LAST APPROVED VERSION: {last['summary'] if last else 'none yet'}\n"
                   f"APPROVED VERSIONS: {len(proj['versions'])}")
        system = (brains.SHARED + "\n\nROLE: business assistant for the owner. Answer in simple Urdu, "
                  "short and direct. Use the CONTEXT. If something is not in the context, say so. Never invent data. "
                  "Do not answer with JSON.\nCONTEXT:\n" + context)
        history = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in proj["chat"][-10:])
        try:
            with st.spinner("Thinking..."):
                text, by = engine.run_job("Chat", system, history + "\n\nAnswer the last USER message.",
                                          slots, ss["log"], keys_all)
            proj["chat"].append({"role": "assistant", "content": f"{text}\n\n*(answered by {by})*"})
        except Exception as e:
            proj["chat"].append({"role": "assistant", "content": "The chat did not finish: " + engine.scrub(e, keys_all)})
        proj["chat"] = proj["chat"][-60:]
        store.save_project(proj)
        st.rerun()
    if proj["chat"] and st.button("Clear this chat", key="btn_clear"):
        proj["chat"] = []
        store.save_project(proj)
        st.rerun()

# ================= TAB: API testing
with tab_api:
    st.subheader("API testing")
    st.caption("Test each ready slot and Tavily, list the models a key can use, and see how well each slot works. "
               "Keys are never shown.")
    ready = engine.ready_entries(slots)
    rows = []
    for s in slots:
        status = "ready" if (s["key"] and s["model"] and (s["kind"] == "gemini" or s["base"])) else "not ready"
        rows.append({"slot": s["name"], "used for": ", ".join(s["duties"]) or "backup only", "status": status})
    rows.append({"slot": "Tavily", "used for": "web search", "status": "ready" if tav_key else "not ready"})
    st.table(rows)
    if st.button("Test all ready slots", type="primary", key="btn_test_all"):
        if not ready and not tav_key:
            st.warning("No slot is ready. Enter a key and a model name in the sidebar.")
        else:
            res = []
            with st.spinner("Testing..."):
                for e in ready:
                    ok, msg = engine.test_slot(e, ss["log"], keys_all)
                    res.append({"slot": e["name"], "result": "works" if ok else "failed", "detail": msg[:120]})
                if tav_key:
                    try:
                        engine.tavily(tav_key, "contractor job costing spreadsheet")
                        engine.record(ss["log"], "Test", "Tavily", True, 0, "test ok", keys_all)
                        res.append({"slot": "Tavily", "result": "works", "detail": "web search answered"})
                    except Exception as e:
                        msg = engine.scrub(e, keys_all)
                        engine.record(ss["log"], "Test", "Tavily", False, 0, msg, keys_all)
                        res.append({"slot": "Tavily", "result": "failed", "detail": msg[:120]})
            st.table(res)
    if ready:
        pick = st.selectbox("Slot to list models for", [e["name"] for e in ready], key="pick_models")
        if st.button("List models", key="btn_models"):
            entry = next(e for e in ready if e["name"] == pick)
            try:
                st.code("\n".join(engine.list_models(entry)) or "none")
            except Exception as e:
                st.error(engine.scrub(e, keys_all))
    st.subheader("How well each slot works")
    scores = engine.score_table(ss["log"])
    st.table(scores or [{"slot": "none yet", "calls": 0, "success %": 0, "avg ms": 0, "last error": "no real calls yet"}])
    st.subheader("Call log (latest 30)")
    st.table(list(reversed(ss["log"][-30:])) or [{"time": "none yet", "job": "none yet", "slot": "none yet",
                                                  "ok": "", "ms": 0, "note": "no calls yet"}])

# ================= TAB: daily log
with tab_log:
    st.subheader("Daily log")
    st.caption("One line per approved product. The brains read the last seven lines to avoid repeats.")
    entries = store.daily_log()
    st.table(entries[-60:][::-1] or [{"date": "none yet", "product": "", "theme": "", "approved": ""}])
