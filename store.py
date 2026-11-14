"""Business Factory 5 - saving layer.

Projects keep every approved version (nothing is deleted). Each version can hold the owner's own
results (views, saves, clicks, sales). Complaints move to a log when a version answers them.
Every approval writes a backup file. Files are written atomically (temp file, then replace).
"""
import hashlib
import json
import os
import uuid
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "bf5_data")
PROJECTS = os.path.join(DATA, "projects")
BACKUPS = os.path.join(DATA, "backups")
DAILY = os.path.join(DATA, "daily_log.json")
SCHEMA = 5
DAILY_LIMIT = 1      # one approved product per day; the owner may allow a second one
MIN_VIEWS = 100      # no judgement below this many views


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


# ---------------- projects
def new_project(name, audience, currency, business, markets):
    return {"schema": SCHEMA, "id": uuid.uuid4().hex[:12], "name": name, "audience": audience,
            "currency": currency, "business": business, "markets": list(markets),
            "created": now(), "updated": now(), "complaints": [], "complaint_log": [],
            "versions": [], "run": None, "chat": [], "pending_notes": ""}


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


# ---------------- versions, complaints, backups
def archive_complaints(p, version_no, addressed):
    """Complaints of this run go to the log. If the version answered them, they are marked answered."""
    if addressed:
        for text in p.get("complaints", []):
            p.setdefault("complaint_log", []).append(
                {"text": text, "status": "answered", "version": version_no, "date": today()})
        p["complaints"] = []


def backup_version(p, version_no):
    path = os.path.join(BACKUPS, f"{p['id']}_v{version_no}.json")
    write_json(path, p)
    return os.path.basename(path)


def list_backups():
    if not os.path.isdir(BACKUPS):
        return []
    return sorted(f for f in os.listdir(BACKUPS) if f.endswith(".json"))


def backup_bytes(name):
    with open(os.path.join(BACKUPS, os.path.basename(name)), "rb") as f:
        return f.read()


def last_versions(p, n=7):
    """Short entries for the brain that chooses the product (avoid repeats)."""
    return [{"date": v.get("date", ""), "product": v.get("product", ""), "theme": v.get("theme", ""),
             "types": v.get("types", [])} for v in p["versions"][-n:]]


# ---------------- results (the owner's own numbers)
def add_result(p, version_no, date, views, saves, clicks, sales):
    vals = []
    for x in (views, saves, clicks, sales):
        try:
            v = int(float(str(x).strip() or 0))
        except ValueError:
            raise ValueError("views, saves, clicks and sales must be numbers")
        if v < 0:
            raise ValueError("numbers cannot be negative")
        vals.append(v)
    ver = next((v for v in p["versions"] if v["v"] == version_no), None)
    if ver is None:
        raise ValueError("version not found")
    ver.setdefault("results", []).append({"date": date, "views": vals[0], "saves": vals[1],
                                          "clicks": vals[2], "sales": vals[3]})
    return ver


def rates(r):
    v, c = r["views"], r["clicks"]
    return {"save %": round(100 * r["saves"] / v, 1) if v else 0.0,
            "click %": round(100 * c / v, 1) if v else 0.0,
            "sale per click %": round(100 * r["sales"] / c, 1) if c else 0.0}


def verdict(r):
    if r["views"] < MIN_VIEWS:
        return f"too few views to judge (need {MIN_VIEWS}); keep testing"
    if r["sales"] == 0:
        return "no sale yet: keep the same product and wait for more views; do not change everything"
    return "sales recorded: compare with the other versions"


def results_rows(p):
    rows = []
    for ver in p["versions"]:
        for r in ver.get("results", []):
            row = {"version": ver["v"], "date": r["date"], "product": ver["product"], "theme": ver["theme"],
                   "views": r["views"], "saves": r["saves"], "clicks": r["clicks"], "sales": r["sales"]}
            row.update(rates(r))
            row["verdict"] = verdict(r)
            rows.append(row)
    return rows


def results_summary(p, limit=6):
    """Text for the planning and pricing brains: the owner's numbers with the verdict for each version."""
    lines = [f"v{r['version']} {r['product']} theme {r['theme']}: views {r['views']}, saves {r['saves']}, "
             f"clicks {r['clicks']}, sales {r['sales']}; {r['verdict']}" for r in results_rows(p)[-limit:]]
    return "\n".join(lines) or "none"


# ---------------- daily log
def daily_log():
    return read_json(DAILY, [])


def record_daily(entry):
    log = daily_log()
    log.append(entry)
    write_json(DAILY, log)


def approved_today(day=None):
    day = day or today()
    return [e for e in daily_log() if e.get("date") == day and e.get("approved")]
