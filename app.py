"""Business Factory 5 - one app for phone and laptop.

Files: app.py (this file), brains.py (the ten brains), engine.py (AI slots and duties),
sheets.py (workbooks), store.py (saving), requirements.txt.
API keys: the left sidebar (the >> button at the top left on a phone).
"""
import io
import zipfile

import streamlit as st

import brains
import engine
import sheets
import store

st.set_page_config(page_title="Business Factory 5", page_icon="🧰", layout="centered")
st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 3rem; max-width: 980px;}
.stButton > button, .stDownloadButton > button {min-height: 48px; border-radius: 12px; font-weight: 700;}
div[data-testid="stTabs"] button {font-weight: 700;}
h1 {font-size: 1.7rem !important;}
@media (max-width: 700px) {
  .block-container {padding-left: .6rem; padding-right: .6rem;}
  h1 {font-size: 1.4rem !important;}
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
                    name = st.text_input("Name", secret(f"{pre}_NAME", d["label"]), key=f"name_{sid}").strip() \
                        or d["label"]
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


def cb_new():
    p = store.new_project(f"New project {store.now()}", ss.get("aud", ""), ss.get("cur", "USD"),
                          ss.get("biz", "Contractor Business Toolkit"), ss.get("mk", ["USA"]))
    ss["proj"] = p
    store.save_project(p)
    ss["flash"] = ("success", "New project started. Earlier projects stay saved.")


def cb_open(pid):
    try:
        p = store.load_project(pid)
    except Exception as e:
        ss["flash"] = ("error", "Could not open: " + str(e)[:150])
        return
    ss["proj"] = p
    ss["aud"], ss["cur"], ss["biz"] = p["audience"], p["currency"], p["business"]
    ss["mk"] = [m for m in p["markets"] if m in MARKETS] or ["USA"]
    ss["compl"] = "\n".join(p["complaints"])
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
    ss["aud"], ss["cur"], ss["biz"] = p["audience"], p["currency"], p["business"]
    ss["mk"] = [m for m in p["markets"] if m in MARKETS] or ["USA"]
    ss["compl"] = "\n".join(p["complaints"])
    ss["flash"] = ("success", "Backup restored and saved on this server.")


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


# ---------------- header and messages
st.title("🧰 Business Factory 5")
st.caption("One button makes today's product: research, decision, workbook (laptop and phone), listing, guide, "
           "pins, checks and a ZIP. You approve it, then upload it yourself. No sales or income guarantee.")
if ss["flash"]:
    kind, msg = ss["flash"]
    ss["flash"] = None
    getattr(st, kind)(msg)

tab_make, tab_projects, tab_chat, tab_api, tab_log = st.tabs(
    ["Make today's product", "Projects", "Chat", "API testing", "Daily log"])

# ================= TAB: make today's product
with tab_make:
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

    with st.expander("1. Your research and buyer complaints", expanded=True):
        mode = st.radio("Research", ["I will paste my own research", "AI researches on its own"],
                        horizontal=True, key="rmode")
        pasted = st.text_area("Paste research (Perplexity, another tool, or your notes)", height=140,
                              key="pasted") if mode.startswith("I") else ""
        source = st.text_input("Which tool or source did it come from?", "Perplexity", key="src")
        use_web = st.checkbox("Also search the web (Tavily)", value=bool(tav_key), key="webon")
        shots = st.file_uploader("Screenshots (optional, layout only, not proof of sales)",
                                 type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="shots")
        complaints_text = st.text_area("Buyer complaints or wishes (one per line, optional)",
                                       "\n".join(proj["complaints"]), key="compl")
        complaints = [x.strip() for x in complaints_text.splitlines() if x.strip()]
        proj["complaints"] = complaints
        owner_notes = st.text_input("Notes for this run (optional)", key="notes")
        pins_on = st.checkbox("Make Pinterest pins too", value=True, key="pins_on")
        allow_second = st.checkbox("Allow a second approved product today", value=False, key="second")

    b1, b2 = st.columns(2)
    run_clicked = b1.button("Make today's product", type="primary", key="btn_run")
    resume_clicked = b2.button("Continue from where it stopped", key="btn_resume")

    if run_clicked:
        if len(store.approved_today()) >= store.DAILY_LIMIT and not allow_second:
            st.warning("One product is already approved today. Tick 'allow a second product today' to make another.")
        else:
            state = brains.new_state(fixed_key)
            state["product_fixed"] = fixed_key is not None
            state["pins_on"] = pins_on
            proj["run"] = state
            resume_clicked = True
    if resume_clicked and proj.get("run") is None:
        st.info("Nothing to continue. Press 'Make today's product'.")
    elif resume_clicked:
        state = proj["run"]
        if state["status"] in ("waiting_approval", "approved"):
            st.info("This product is waiting for your approval below.")
        else:
            notes = owner_notes or proj.get("pending_notes", "")
            proj["pending_notes"] = ""
            prev = proj["versions"][-1] if proj["versions"] else None
            ctx = {
                "product": state["product"] if state.get("product_fixed") else None,
                "product_fixed": bool(state.get("product_fixed")),
                "product_title": brains.PRODUCT_TITLES.get(state["product"], "one of the four products (the brain chooses)")
                if state.get("product_fixed") else "one of the four products (the brain chooses)",
                "audience": audience, "currency": currency, "business": business,
                "markets": ", ".join(markets) or "not chosen",
                "research_text": pasted or "", "source": source,
                "web_text": "", "shot_note": "none", "images": [],
                "complaints": complaints, "prev": prev,
                "prev_theme": prev["theme"] if prev else None,
                "recent": store.last_versions(proj),
                "slots": slots, "log": ss["log"], "keys": keys_all,
                "owner_notes": notes, "fix_notes": [],
            }
            imgs = [(f.type or "image/png", f.getvalue()) for f in (shots or [])[:10]]
            ctx["images"] = imgs
            ctx["shot_note"] = f"{len(imgs)} attached (layout only)" if imgs else "none"
            if use_web and tav_key and not state["brains"]:
                try:
                    ctx["web_text"] = engine.tavily(tav_key, f"{audience} spreadsheet template {currency} contractors")
                except Exception as e:
                    st.warning("Web search failed; continuing without it: " + engine.scrub(e, keys_all))
            with st.spinner("The brains are working. This can take several minutes; each step is saved."):
                status = brains.run_pipeline(state, ctx, lambda s: store.save_project(proj), pins_on=pins_on)
            store.save_project(proj)
            if status == "error":
                st.error("A brain stopped. Press 'Continue from where it stopped' after you check the message below.")
            elif status == "waiting_approval":
                st.success("The gate passed. Read the checks below, then approve.")
            elif status == "blocked":
                st.error("The gate blocked this product. Read the reasons below, then send it back with notes.")

    state = proj.get("run")
    if state:
        st.subheader("Brains")
        rows = []
        for n in range(1, 9):
            if n == 8 and not (state.get("pins_on", True) or "8" in state["brains"]):
                continue
            b = state["brains"].get(str(n))
            rows.append({"brain": n, "name": brains.BRAIN_NAMES[n], "status": "done" if b else "waiting",
                         "answered by": b["slot"] if b else state["slots"].get(str(n), "")})
        rows.append({"brain": 9, "name": "Critic and gate",
                     "status": state.get("gate", "waiting") if state.get("checks") else "waiting", "answered by": "code"})
        rows.append({"brain": 10, "name": "Package", "status": "after approval", "answered by": "code"})
        st.table(rows)
        for e in state.get("errors", []):
            st.error(f"Brain {e['brain']} ({e['name']}) at {e['at']}: {e['msg']}")
        if state.get("product"):
            st.caption(f"Product: {brains.PRODUCT_TITLES.get(state['product'], state['product'])} | "
                       f"Status: {state['status']} | Fix rounds: {state.get('fix_round', 0)}")

        if state["status"] in ("waiting_approval", "blocked"):
            plan = state["brains"]["3"]["data"]
            theme = plan["theme"]
            st.markdown(f"**Theme:** <span style='color:{THEME_COLOURS.get(theme, '#173B75')}'>"
                        f"{theme}</span> &nbsp;|&nbsp; **Plan:** {plan['summary']}", unsafe_allow_html=True)
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
                    ctx_pkg = {"currency": currency, "business": business}
                    version_no = len(proj["versions"]) + 1
                    zip_bytes, manifest = brains.build_package(ctx_pkg, state, version_no)
                    types = sorted({c["type"] for c in plan["changes"]})
                    proj["versions"].append({
                        "v": version_no, "date": store.today(), "at": store.now(), "product": state["product"],
                        "theme": theme, "types": types, "summary": plan["summary"],
                        "brains": state["brains"], "checks": state["checks"], "manifest": manifest,
                        "approved": True})
                    store.record_daily({"date": store.today(), "project": proj["id"], "v": version_no,
                                        "product": state["product"], "theme": theme, "types": types,
                                        "approved": True})
                    proj["run"] = None
                    store.save_project(proj)
                    ss["pkg"], ss["pkg_name"] = zip_bytes, f"{store.today()}_{state['product']}_v{version_no}"
                    ss["flash"] = ("success", f"Version {version_no} approved and saved.")
                    st.rerun()
            notes = st.text_input("Send back with notes (the brains redo the plan and the text)", key="sendback")
            if st.button("Send back with these notes", key="btn_sendback") and notes.strip():
                for n in range(3, 9):
                    state["brains"].pop(str(n), None)
                state["status"] = "idle"
                state["fix_round"] = 0
                proj["pending_notes"] = notes.strip()
                store.save_project(proj)
                st.info("Sent back. Press 'Continue from where it stopped'.")

    if ss.get("pkg") and ss.get("pkg_name"):
        st.subheader("Downloads")
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
        st.subheader("Approved versions of this project")
        for v in reversed(proj["versions"]):
            st.write(f"v{v['v']} · {v['date']} · {v['product']} · theme {v['theme']} · {', '.join(v['types'])}")

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

# ================= TAB: chat
with tab_chat:
    st.subheader("Chat")
    st.caption("Write in Urdu or English, or use the microphone on your keyboard. The chat knows this project.")
    for m in proj["chat"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    msg = st.chat_input("Ask about the product, the research, the workbook, or the next step")
    if msg:
        proj["chat"].append({"role": "user", "content": msg})
        last = proj["versions"][-1] if proj["versions"] else None
        context = (f"PRODUCT TITLES: {', '.join(brains.PRODUCT_TITLES.values())}\n"
                   f"AUDIENCE: {proj['audience']} | CURRENCY: {proj['currency']} | MARKETS: {', '.join(proj['markets'])}\n"
                   f"BUYER COMPLAINTS: {'; '.join(proj['complaints']) or 'none'}\n"
                   f"LAST APPROVED VERSION: {last['summary'] if last else 'none yet'}\n"
                   f"APPROVED VERSIONS: {len(proj['versions'])}")
        system = (brains.SHARED + "\n\nROLE: business assistant for the owner. Answer in simple Urdu, "
                  "short and direct. Use the CONTEXT. If something is not in the context, say so. Never invent data.\n"
                  "CONTEXT:\n" + context)
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
    st.caption("Test each ready slot, list the models a key can use, and see how well each slot works. "
               "Keys are never shown.")
    ready = engine.ready_entries(slots)
    rows = []
    for s in slots:
        status = "ready" if (s["key"] and s["model"] and (s["kind"] == "gemini" or s["base"])) else "not ready"
        rows.append({"slot": s["name"], "used for": ", ".join(s["duties"]) or "backup only", "status": status})
    rows.append({"slot": "Tavily", "used for": "web search", "status": "ready" if tav_key else "not ready"})
    st.table(rows)
    if st.button("Test all ready slots", type="primary", key="btn_test_all"):
        if not ready:
            st.warning("No slot is ready. Enter a key and a model name in the sidebar.")
        else:
            res = []
            with st.spinner("Testing..."):
                for e in ready:
                    ok, msg = engine.test_slot(e, ss["log"], keys_all)
                    res.append({"slot": e["name"], "result": "works" if ok else "failed", "detail": msg[:120]})
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
    st.table(scores or [{"slot": "-", "calls": 0, "success %": 0, "avg ms": 0, "last error": "no real calls yet"}])
    st.subheader("Call log (latest 30)")
    st.table(list(reversed(ss["log"][-30:])) or [{"time": "-", "job": "-", "slot": "-", "ok": "-", "ms": 0, "note": "no calls yet"}])

# ================= TAB: daily log
with tab_log:
    st.subheader("Daily log")
    st.caption("One line per approved product. The brains read the last seven lines to avoid repeats.")
    entries = store.daily_log()
    st.table(entries[-60:][::-1] or [{"date": "-", "product": "-", "theme": "-", "approved": "-"}])
