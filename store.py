"""Business Factory 5 - saving layer.

Projects keep every approved version (never deleted). The daily log records each approved product.
Files are written atomically (temp file, then replace), so a crash cannot leave half a file.
"""
import hashlib
import json
import os
import uuid
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "bf5_data")
PROJECTS = os.path.join(DATA, "projects")
DAILY = os.path.join(DATA, "daily_log.json")
SCHEMA = 5
DAILY_LIMIT = 1  # one approved product per day; the owner may allow a second one


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def sha256(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def new_project(name, audience, currency, business, markets):
    return {"schema": SCHEMA, "id": uuid.uuid4().hex[:12], "name": name, "audience": audience,
            "currency": currency, "business": business, "markets": list(markets),
            "created": now(), "updated": now(), "complaints": [], "versions": [],
            "run": None, "chat": []}


def save_project(p):
    p["updated"] = now()
    write_json(os.path.join(PROJECTS, p["id"] + ".json"), p)
    return True


def list_projects():
    os.makedirs(PROJECTS, exist_ok=True)
    out = []
    for fn in os.listdir(PROJECTS):
        if not fn.endswith(".json"):
            continue
        d = read_json(os.path.join(PROJECTS, fn), None)
        if isinstance(d, dict) and d.get("schema") == SCHEMA:
            out.append((d.get("updated", ""), d["id"], d.get("name", "?"), len(d.get("versions", []))))
    return sorted(out, reverse=True)


def load_project(pid):
    d = read_json(os.path.join(PROJECTS, pid + ".json"), None)
    if not isinstance(d, dict) or d.get("schema") != SCHEMA:
        raise ValueError("project not found, or saved by another version")
    return d


def export_bytes(p):
    return json.dumps(p, ensure_ascii=False, indent=2).encode("utf-8")


def import_bytes(raw):
    if len(raw) > 5_000_000:
        raise ValueError("file too large")
    d = json.loads(raw.decode("utf-8"))
    if not isinstance(d, dict) or d.get("schema") != SCHEMA:
        raise ValueError("not a Business Factory 5 project file")
    return d


def daily_log():
    return read_json(DAILY, [])


def record_daily(entry):
    log = daily_log()
    log.append(entry)
    write_json(DAILY, log)


def approved_today(day=None):
    day = day or today()
    return [e for e in daily_log() if e.get("date") == day and e.get("approved")]


def last_versions(p, n=7):
    """Daily-log style entries for the brain that chooses the product (avoid repeats)."""
    out = []
    for v in p["versions"][-n:]:
        out.append({"date": v.get("date", ""), "product": v.get("product", ""), "theme": v.get("theme", ""),
                    "types": v.get("types", [])})
    return out
