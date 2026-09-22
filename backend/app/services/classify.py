"""Target classification — deterministic rule set per A360 package.
Returns (target, reason). Targets: Cloud flow | Desktop flow | AI Builder | Redesign."""
import re
from collections import OrderedDict

TARGETS = ["Cloud flow", "Desktop flow", "AI Builder", "Redesign"]

RULES = [
    (r"iq ?bot|document ?automation", "AI Builder", "Document extraction model must be retrained in AI Builder"),
    (r"dll|python|vbscript|powershell|javascript|image|citrix", "Redesign", "No safe PAD/cloud equivalent — Azure Function, custom connector or manual"),
    (r"workload|wlm|credential|global", "Redesign", "Replace with standard pattern: Dataverse queue / Key Vault / environment variable"),
    (r"sap|recorder|objectcloning|browser|terminal|window|excel advanced|pdf|clipboard", "Desktop flow", "UI or local-application step → PAD on hosted machine"),
    (r"email|rest|http|database|soap|sharepoint|teams", "Cloud flow", "API / connector step → cloud flow action"),
]


def rule_target(package: str):
    k = (package or "").lower()
    for pattern, target, reason in RULES:
        if re.search(pattern, k):
            return target, reason
    return "Cloud flow", "Orchestration, rules and variables → cloud flow expressions"


def group_actions(actions: list[dict]) -> list[dict]:
    """One row per package (active actions only) with suggested target."""
    merged: "OrderedDict[str, dict]" = OrderedDict()
    for a in actions:
        if a.get("disabled"):
            continue
        pkg = a.get("package") or "unknown"
        g = merged.setdefault(pkg, {"package": pkg, "count": 0, "commands": []})
        g["count"] += 1
        if a.get("command") and a["command"] not in g["commands"]:
            g["commands"].append(a["command"])
    out = []
    for g in merged.values():
        target, reason = rule_target(g["package"])
        out.append({"package": g["package"], "count": g["count"], "commands": ", ".join(g["commands"][:4]),
                    "suggested_target": target, "target": target, "reason": reason})
    return out


def bot_target(groups) -> str:
    c = {}
    for g in groups:
        t = g["target"] if isinstance(g, dict) else g.target
        n = g["count"] if isinstance(g, dict) else g.count
        c[t] = c.get(t, 0) + n
    desk, cloud = c.get("Desktop flow", 0) > 0, c.get("Cloud flow", 0) > 0
    if desk and cloud:
        return "Hybrid (cloud + desktop)"
    if desk:
        return "Desktop flow"
    if c.get("AI Builder") and not cloud:
        return "AI Builder"
    return "Cloud flow"
