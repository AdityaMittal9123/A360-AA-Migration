"""
a360_parser.py — deterministic parser for Automation Anywhere A360 bot exports.
No LLM. Reads an exported .zip (or a folder / single bot JSON) and produces:
  - per-task-bot: active actions, disabled actions, variables, packages used,
    calls (which sub-task bots it runs) and called_by (reverse index)
  - estate-level nesting tree
  - complexity score per bot (LOC bands + action-type weights) → Low / Medium / High

Usage:
  python a360_parser.py AR_CashApplication_Main.zip  > parsed.json
  python a360_parser.py ./exported_folder            > parsed.json

The JSON it emits is exactly what the migration UI (index.html) expects on upload.
"""
import sys, json, zipfile, io, os, re
from collections import defaultdict

# ---------------------------------------------------------------------------
# Complexity model (edit these weights — they are deliberately visible)
# ---------------------------------------------------------------------------
LOC_BANDS = [            # (max_active_actions, score)
    (100, 1), (200, 2), (400, 3), (700, 4), (10**9, 5)
]
PACKAGE_WEIGHT = {       # per action, by package family
    "variable": 0.2, "string": 0.2, "number": 0.2, "datetime": 0.2, "boolean": 0.2,
    "if": 0.4, "loop": 0.6, "errorhandler": 0.5, "step": 0.1, "comment": 0.0,
    "taskbot": 0.5, "dictionary": 0.4, "list": 0.4, "datatable": 0.6,
    "email": 1.0, "rest": 1.2, "database": 1.2, "http": 1.2, "soap": 1.2,
    "excel": 1.0, "csv": 0.8, "file": 0.6, "folder": 0.6, "pdf": 1.0,
    "recorder": 2.5, "objectcloning": 2.5, "sap": 2.5, "browser": 2.0,
    "terminal": 2.5, "image": 3.0, "ocr": 2.0, "citrix": 3.0, "window": 1.5,
    "iqbot": 2.0, "documentautomation": 2.0,
    "dll": 3.0, "python": 3.0, "vbscript": 3.0, "powershell": 2.5, "javascript": 2.5,
    "wlm": 1.5, "workload": 1.5, "credential": 0.8, "system": 0.8, "clipboard": 0.6,
}
DEFAULT_WEIGHT = 1.0
COMPLEXITY_THRESHOLDS = [("Low", 5.0), ("Medium", 10.0), ("High", 10**9)]

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _load_bot_files(path):
    """Yield (relative_name, json_obj) for every bot definition found."""
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for f in files:
                if f.lower().endswith((".json", ".abot")):
                    with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as fh:
                        obj = _try_json(fh.read())
                        if obj is not None:
                            yield os.path.relpath(os.path.join(root, f), path), obj
    elif path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith((".json", ".abot")) and not name.endswith("/"):
                    obj = _try_json(z.read(name).decode("utf-8", errors="ignore"))
                    if obj is not None:
                        yield name, obj
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            obj = _try_json(fh.read())
            if obj is not None:
                yield os.path.basename(path), obj

def _try_json(text):
    try:
        return json.loads(text)
    except Exception:
        return None

def _is_bot(obj):
    return isinstance(obj, dict) and isinstance(obj.get("nodes"), list)

# ---------------------------------------------------------------------------
# Walking a bot
# ---------------------------------------------------------------------------
def _walk(nodes, depth, out, disabled_parent=False):
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        pkg = (n.get("packageName") or n.get("package") or "").strip()
        cmd = (n.get("commandName") or n.get("command") or "").strip()
        disabled = bool(n.get("disabled", False)) or disabled_parent
        attrs = {}
        for a in n.get("attributes", []) or []:
            if isinstance(a, dict) and "name" in a:
                v = a.get("value")
                if isinstance(v, dict):          # A360 wraps values: {"type":"STRING","string":"..."}
                    v = v.get("string") or v.get("number") or v.get("expression") or json.dumps(v)
                attrs[a["name"]] = v
        out.append({
            "uid": n.get("uid"), "package": pkg, "command": cmd,
            "disabled": disabled, "depth": depth, "attributes": attrs,
        })
        # children live under different keys depending on the command
        for key in ("children", "branches", "nodes"):
            if isinstance(n.get(key), list):
                for child in n[key]:
                    if isinstance(child, dict) and isinstance(child.get("nodes"), list):
                        _walk(child["nodes"], depth + 1, out, disabled)   # If/Else branches
                    else:
                        _walk([child], depth + 1, out, disabled)

def _sub_task_path(action):
    a = action["attributes"]
    for k in ("botPath", "path", "fileId", "botName", "taskbot"):
        if k in a and a[k]:
            return str(a[k])
    return None

def parse_bot(name, obj):
    actions = []
    _walk(obj.get("nodes", []), 0, actions)
    active = [a for a in actions if not a["disabled"]]
    disabled = [a for a in actions if a["disabled"]]

    packages = defaultdict(int)
    for a in active:
        packages[a["package"] or "unknown"] += 1

    calls = []
    for a in active:
        if a["package"].lower() == "taskbot" and a["command"].lower() in ("run", "runtask", "run_task"):
            p = _sub_task_path(a)
            if p:
                calls.append(p)

    variables = []
    for v in obj.get("variables", []) or []:
        if isinstance(v, dict):
            variables.append({"name": v.get("name"), "type": v.get("type"),
                              "input": bool(v.get("input")), "output": bool(v.get("output"))})

    vault_refs = sorted({m for a in actions for val in a["attributes"].values()
                         for m in re.findall(r"\$Vault\.[A-Za-z0-9_\.]+\$", str(val))})
    global_refs = sorted({m for a in actions for val in a["attributes"].values()
                          for m in re.findall(r"\$Global\.[A-Za-z0-9_]+\$", str(val))})
    max_depth = max((a["depth"] for a in actions), default=0)

    score = _score(len(active), packages, max_depth)
    return {
        "name": _bot_name(name, obj),
        "file": name,
        "active_actions": len(active),
        "disabled_actions": len(disabled),
        "total_actions": len(actions),
        "max_nesting_depth": max_depth,
        "variables": variables,
        "packages": dict(sorted(packages.items(), key=lambda kv: -kv[1])),
        "calls": calls,
        "called_by": [],
        "vault_references": vault_refs,
        "global_value_references": global_refs,
        "complexity_score": round(score, 1),
        "complexity": _band(score),
        "actions": actions,      # full normalised action list — the UI passes this to the LLM in chunks
    }

def _bot_name(fname, obj):
    for k in ("name", "botName", "displayName"):
        if obj.get(k):
            return str(obj[k])
    return os.path.splitext(os.path.basename(fname))[0]

def _score(active_count, packages, depth):
    loc = next(s for mx, s in LOC_BANDS if active_count <= mx)
    weighted = 0.0
    for pkg, cnt in packages.items():
        key = pkg.lower().replace(" ", "")
        w = next((v for k, v in PACKAGE_WEIGHT.items() if k in key), DEFAULT_WEIGHT)
        weighted += w * cnt
    # normalise the weighted action score to a 0–10 band, add LOC and nesting
    return loc + min(weighted / 8.0, 10.0) + min(depth * 0.5, 3.0)

def _band(score):
    return next(label for label, mx in COMPLEXITY_THRESHOLDS if score <= mx)

# ---------------------------------------------------------------------------
# Estate
# ---------------------------------------------------------------------------
def parse_export(path):
    bots = []
    for name, obj in _load_bot_files(path):
        if _is_bot(obj):
            bots.append(parse_bot(name, obj))
    # resolve calls → called_by (match on file path tail or bot name)
    by_key = {}
    for b in bots:
        by_key[b["name"].lower()] = b
        by_key[os.path.splitext(os.path.basename(b["file"]))[0].lower()] = b
    for b in bots:
        resolved = []
        for c in b["calls"]:
            tail = os.path.splitext(os.path.basename(c.replace("\\", "/")))[0].lower()
            target = by_key.get(tail) or by_key.get(c.lower())
            resolved.append(target["name"] if target else c)
            if target:
                target["called_by"].append(b["name"])
        b["calls"] = resolved
    roots = [b["name"] for b in bots if not b["called_by"]]
    return {
        "source": os.path.basename(path),
        "task_bots": len(bots),
        "active_actions": sum(b["active_actions"] for b in bots),
        "disabled_actions": sum(b["disabled_actions"] for b in bots),
        "roots": roots,
        "bots": bots,
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    print(json.dumps(parse_export(sys.argv[1]), indent=2))
