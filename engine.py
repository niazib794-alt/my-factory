"""Business Factory 5 - AI engine.

Each API slot has duties (what it is used for). A job goes first to the ready slots whose duties
include it; the other ready slots are backups in slot order. Every call is logged (slot, job, result,
time). Keys are removed from every message before it is stored or shown.
"""
import base64
import json
import random
import re
import time
from datetime import datetime

import requests

GEMINI = "https://generativelanguage.googleapis.com/v1beta"
TAVILY_URL = "https://api.tavily.com/search"
DUTIES = ["Research", "Decide", "Guide", "Listing", "Pins", "Chat", "Critic"]

SLOT_DEFS = [
    {"id": "gem1", "label": "Gemini 1", "kind": "gemini", "base": "", "default": ["Research"]},
    {"id": "gem2", "label": "Gemini 2", "kind": "gemini", "base": "", "default": ["Guide"]},
    {"id": "gem3", "label": "Gemini 3", "kind": "gemini", "base": "", "default": ["Decide", "Critic"]},
    {"id": "groq", "label": "Groq 1", "kind": "openai", "base": "https://api.groq.com/openai/v1", "default": ["Listing", "Pins"]},
    {"id": "groq2", "label": "Groq 2", "kind": "openai", "base": "https://api.groq.com/openai/v1", "default": ["Research"]},
    {"id": "openrouter", "label": "OpenRouter 1", "kind": "openai", "base": "https://openrouter.ai/api/v1", "default": []},
    {"id": "openrouter2", "label": "OpenRouter 2", "kind": "openai", "base": "https://openrouter.ai/api/v1", "default": []},
    {"id": "cohere", "label": "Cohere", "kind": "openai", "base": "https://api.cohere.ai/compatibility/v1", "default": ["Research"]},
    {"id": "cus1", "label": "Custom AI 1", "kind": "openai", "base": "", "default": ["Chat", "Decide"]},
    {"id": "cus2", "label": "Custom AI 2", "kind": "openai", "base": "", "default": []},
    {"id": "cus3", "label": "Custom AI 3", "kind": "openai", "base": "", "default": []},
    {"id": "cus4", "label": "Custom AI 4", "kind": "openai", "base": "", "default": []},
    {"id": "cus5", "label": "Custom AI 5", "kind": "openai", "base": "", "default": []},
    {"id": "cus6", "label": "Custom AI 6", "kind": "openai", "base": "", "default": []},
]
SECRET_PREFIX = {"groq": "GROQ", "mistral": "MISTRAL", "openrouter": "OPENROUTER",
                 "cus1": "CUSTOM1", "cus2": "CUSTOM2", "cus3": "CUSTOM3",
                 "cus4": "CUSTOM4", "cus5": "CUSTOM5", "cus6": "CUSTOM6"}
MODEL_DEFAULT = {"groq": "llama-3.3-70b-versatile", "openrouter": "deepseek/deepseek-chat"}


class EngineError(Exception):
    pass


KEY_SHAPES = [re.compile(p) for p in (
    r"AIza[0-9A-Za-z_\-]{20,}", r"gsk_[0-9A-Za-z]{20,}", r"sk-[0-9A-Za-z_\-]{16,}", r"tvly-[0-9A-Za-z_\-]{16,}",
    r"(?i)(bearer\s+)[0-9A-Za-z._\-]{12,}", r"(?i)(x-goog-api-key[\"':=\s]+)[0-9A-Za-z_\-]{12,}")]


def scrub(text, keys):
    """Remove every known key, and anything shaped like a provider key, before a message is stored or shown."""
    s = str(text)
    for k in keys:
        if k:
            s = s.replace(k, "***")
    for rx in KEY_SHAPES:
        s = rx.sub(lambda m: (m.group(1) + "***") if m.lastindex else "***", s)
    return s[:300]


def now_hms():
    return datetime.now().strftime("%H:%M:%S")


def ready_entries(slots):
    """Slots that have a key and a model (and a base URL when the kind needs one)."""
    out = []
    for s in slots:
        if not s.get("on", True) or not s.get("key") or not s.get("model"):
            continue
        if s["kind"] == "openai" and not s.get("base"):
            continue
        out.append(s)
    return out


def ordered_for(job, entries, rotate=0):
    """Slots with this duty first, then the other ready slots as backups.
    rotate starts the duty list at a different slot, so repeated calls spread over the free keys."""
    primary = [e for e in entries if job in e.get("duties", [])]
    rest = [e for e in entries if job not in e.get("duties", [])]
    if primary and rotate:
        k = rotate % len(primary)
        primary = primary[k:] + primary[:k]
    return primary + rest


def _post(url, headers, body, timeout=120):
    for attempt in range(3):
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
        if r.status_code in (429, 500, 502, 503) and attempt < 2:
            time.sleep(2 ** attempt + random.random())
            continue
        if r.status_code != 200:
            raise EngineError(f"HTTP {r.status_code}: {r.text[:160]}")
        return r.json()
    raise EngineError("no reply after retries")


def call_slot(entry, system, user, images=(), grounding=False, sources=None, timeout=120):
    """One call to one slot. Returns the text of the reply."""
    if entry["kind"] == "gemini":
        parts = [{"text": user}]
        for mime, raw in images:
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode("ascii")}})
        body = {"system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192}}
        if grounding:
            body["tools"] = [{"google_search": {}}]
        data = _post(f"{GEMINI}/models/{entry['model']}:generateContent",
                     {"Content-Type": "application/json", "x-goog-api-key": entry["key"]}, body, timeout=timeout)
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise EngineError("blocked or empty reply")
        if sources is not None:
            for ch in data["candidates"][0].get("groundingMetadata", {}).get("groundingChunks", []):
                w = ch.get("web", {})
                if w.get("uri"):
                    sources.append({"title": w.get("title", ""), "url": w["uri"]})
    else:
        if images:
            raise EngineError("this slot cannot read images")
        data = _post(entry["base"].rstrip("/") + "/chat/completions",
                     {"Authorization": f"Bearer {entry['key']}", "Content-Type": "application/json"},
                     {"model": entry["model"], "temperature": 0.3,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=timeout)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise EngineError("unexpected reply format")
    if not str(text or "").strip():
        raise EngineError("empty reply")
    return text


def record(log, job, slot, ok, ms, note, keys):
    log.append({"time": now_hms(), "job": job, "slot": slot, "ok": bool(ok), "ms": int(ms),
                "note": scrub(note, keys)[:160]})
    del log[:-500]


DEAD = {}  # slot name -> the refusal, for keys that answered 401, 403 or 404 this session


def revive_all():
    """Called by the Test button: every key gets another chance after a test."""
    DEAD.clear()


def run_job(job, system, user, slots, log, keys, images=(), grounding=False, sources=None, rotate=0):
    """Ask the slots for this job in order. Returns (text, slot name)."""
    entries = ordered_for(job, ready_entries(slots), rotate)
    if not entries:
        raise EngineError("No AI slot is ready. Enter a key and a model name in the sidebar.")
    errs = []
    skipped = []
    for e in entries:
        if images and e["kind"] != "gemini":
            continue
        if e["name"] in DEAD:
            skipped.append(e["name"])
            continue
        t0 = time.time()
        try:
            text = call_slot(e, system, user, images, grounding, sources)
            record(log, job, e["name"], True, (time.time() - t0) * 1000, "ok", keys)
            return text, e["name"]
        except Exception as ex:
            msg = scrub(ex, keys)
            if re.search(r"HTTP (401|403|404)", msg):
                DEAD[e["name"]] = msg[:120]
            record(log, job, e["name"], False, (time.time() - t0) * 1000, msg, keys)
            errs.append(f"{e['name']}: {msg[:140]}")
    if images:
        raise EngineError("Screenshots need a Gemini slot with a key. " + "; ".join(errs))
    if not errs and skipped:
        raise EngineError("These AI keys were refused earlier and are skipped: " + ", ".join(skipped) + ". Fix them, then press Test all keys now.")
    raise EngineError("; ".join(errs) or "No slot answered.")


def extract_json(text):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text).strip())
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in the reply")
    return json.loads(t[a:b + 1])


def json_job(job, system, user, slots, log, keys, check, images=(), attempts=2, grounding=False, sources=None,
             rotate=0):
    """Ask for JSON and check it. check(data) returns a list of problems (empty means fine)."""
    problem = ""
    for _ in range(attempts):
        extra = (f"\n\nYOUR PREVIOUS REPLY WAS REJECTED: {problem}. "
                 "Reply again with ONLY valid JSON in the required shape.") if problem else ""
        text, slot = run_job(job, system, user + extra, slots, log, keys, images, grounding, sources, rotate)
        try:
            problems = check(extract_json(text))
        except Exception as ex:
            problems = [f"invalid JSON: {ex}"]
        if not problems:
            return json.loads(json.dumps(extract_json(text), ensure_ascii=False)), slot
        problem = "; ".join(problems)[:300]
    raise EngineError(f"{job}: the reply was not valid after {attempts} tries: {problem}")


def test_slot(entry, log, keys, timeout=40):
    t0 = time.time()
    try:
        call_slot(entry, "Reply with the single word OK.", "Say OK.", timeout=timeout)
        record(log, "Test", entry["name"], True, (time.time() - t0) * 1000, "test ok", keys)
        return True, "works"
    except Exception as ex:
        msg = scrub(ex, keys)
        record(log, "Test", entry["name"], False, (time.time() - t0) * 1000, msg, keys)
        return False, msg


def list_models(entry):
    if entry["kind"] == "gemini":
        r = requests.get(f"{GEMINI}/models?pageSize=200", headers={"x-goog-api-key": entry["key"]}, timeout=30)
        if r.status_code != 200:
            raise EngineError(f"HTTP {r.status_code}")
        return sorted(m["name"].split("/")[-1] for m in r.json().get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", []))
    r = requests.get(entry["base"].rstrip("/") + "/models",
                     headers={"Authorization": f"Bearer {entry['key']}"}, timeout=30)
    if r.status_code != 200:
        raise EngineError(f"HTTP {r.status_code}")
    return sorted(m.get("id", "") for m in r.json().get("data", []) if m.get("id"))


def tavily(key, query, items=None):
    data = _post(TAVILY_URL, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                 {"query": query[:300], "search_depth": "basic", "max_results": 6, "include_answer": True}, timeout=60)
    out = []
    if data.get("answer"):
        out.append("SUMMARY (open the links yourself): " + str(data["answer"]))
    for i, r in enumerate(data.get("results", []), 1):
        if items is not None:
            items.append({"title": r.get("title", ""), "url": r.get("url", "")})
        out.append(f"[{i}] {r.get('title', '')} | {r.get('url', '')} | "
                   f"{r.get('published_date') or 'date not given'}\n{str(r.get('content', ''))[:700]}")
    return "\n\n".join(out)


def score_table(log):
    """Per slot: calls, success rate, average time, last error (real calls only)."""
    rows = {}
    for r in log:
        if r["job"] == "Test":
            continue
        s = rows.setdefault(r["slot"], {"calls": 0, "ok": 0, "ms": 0, "last": ""})
        s["calls"] += 1
        if r["ok"]:
            s["ok"] += 1
            s["ms"] += r["ms"]
        else:
            s["last"] = r["note"]
    out = []
    for name, s in rows.items():
        out.append({"slot": name, "calls": s["calls"],
                    "success %": round(100 * s["ok"] / s["calls"]) if s["calls"] else 0,
                    "avg ms": round(s["ms"] / s["ok"]) if s["ok"] else 0,
                    "last error": s["last"]})
    return sorted(out, key=lambda x: (-x["success %"], x["avg ms"]))


# secret names read for each slot (the first filled name wins)
SLOT_SECRETS = {
    "gem1": ["GEMINI_KEY_1"], "gem2": ["GEMINI_KEY_2"], "gem3": ["GEMINI_KEY_3"],
    "groq": ["GROQ_KEY", "GROQ_KEY_1"], "groq2": ["GROQ_KEY_2", "GROQ_2_KEY"],
    "openrouter": ["OPENROUTER_KEY", "OPENROUTER_KEY_1"], "openrouter2": ["OPENROUTER_KEY_2", "OPENROUTER_2_KEY"],
    "cohere": ["COHERE_KEY", "COHERE_API_KEY", "COHERE_KEY_1"],
}
SLOT_SECRETS.update({f"cus{n}": [f"CUSTOM{n}_KEY"] for n in range(1, 7)})
SLOT_MODEL_SECRETS = {
    "gem1": ["GEMINI_MODEL"], "gem2": ["GEMINI_MODEL"], "gem3": ["GEMINI_MODEL"],
    "groq": ["GROQ_MODEL"], "groq2": ["GROQ_MODEL_2", "GROQ_MODEL"],
    "openrouter": ["OPENROUTER_MODEL"], "openrouter2": ["OPENROUTER_MODEL_2"],
    "cohere": ["COHERE_MODEL"],
}
SLOT_MODEL_SECRETS.update({f"cus{n}": [f"CUSTOM{n}_MODEL"] for n in range(1, 7)})
SLOT_BASE_SECRETS = {"cohere": ["COHERE_BASE"], }
SLOT_BASE_SECRETS.update({f"cus{n}": [f"CUSTOM{n}_BASE"] for n in range(1, 7)})
MODEL_DEFAULT.update({"groq2": "llama-3.3-70b-versatile", "cohere": "command-r-plus-08-2024"})


# ---------------- key discovery from the secret names (version 6.2)
def pool_secrets(values, token):
    """Every filled secret value whose name contains the service word and KEY, in name order.
    MODEL, BASE and NAME secrets are skipped."""
    out = []
    for name in sorted(values):
        up = str(name).upper()
        if token in up and "KEY" in up and not any(x in up for x in ("MODEL", "BASE", "NAME")):
            v = str(values[name] or "").strip()
            if v:
                out.append(v)
    return out


def assign_keys(values):
    """Map the keys found in the secrets to the slots. A custom slot whose name is a provider name
    (for example CUSTOM1_NAME = Mistral) is used when no key with the provider word exists.
    Returns (slot id -> key, list of Tavily keys)."""
    out = {}
    for i, k in enumerate(pool_secrets(values, "GEMINI")[:3], 1):
        out[f"gem{i}"] = k
    customs = {n: str(values.get(f"CUSTOM{n}_NAME", "")).lower() for n in range(1, 7)}
    custom_keys = {n: str(values.get(f"CUSTOM{n}_KEY", "")).strip() for n in range(1, 7)}
    for sid, token, word in (("groq", "GROQ", "groq"), ("openrouter", "OPENROUTER", "openrouter")):
        keys = pool_secrets(values, token)
        if not keys:
            keys = [custom_keys[n] for n in range(1, 7) if word in customs[n] and custom_keys[n]]
        if keys:
            out[sid] = keys[0]
        if len(keys) > 1:
            out[sid + "2"] = keys[1]
    cohere = pool_secrets(values, "COHERE")
    if not cohere:
        cohere = [custom_keys[n] for n in range(1, 7) if "cohere" in customs[n] and custom_keys[n]]
    if cohere:
        out["cohere"] = cohere[0]
    taken = set(out.values())
    for n in range(1, 7):
        if custom_keys[n] and custom_keys[n] not in taken:
            out[f"cus{n}"] = custom_keys[n]
    return out, pool_secrets(values, "TAVILY")[:2]
