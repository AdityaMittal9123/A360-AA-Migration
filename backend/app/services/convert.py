"""Converters: parsed bot + approved targets + config → Power Automate artefacts.
- cloud_flow_json: workflow-definition JSON (Logic Apps schema) for solution import
- robin_script: PAD desktop-flow script for copy/paste into the designer
Unmapped commands are emitted as '# GAP' lines, never dropped."""
import json
import re
from .classify import rule_target

TYPE_MAP = {"STRING": "string", "NUMBER": "float", "BOOLEAN": "boolean", "DATETIME": "string", "TABLE": "array",
            "LIST": "array", "DICTIONARY": "object", "RECORD": "object", "FILE": "string"}


def safe(s) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", str(s))


def _v(name) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", str(name).replace("$", ""))


def cloud_gap_count(wf: dict) -> int:
    """Count GAP_* action keys across the workflow definition (top level and nested in Scope/If/Foreach)."""
    def walk(actions):
        if not isinstance(actions, dict):
            return 0
        n = sum(1 for k in actions if isinstance(k, str) and k.startswith("GAP_"))
        for v in actions.values():
            if isinstance(v, dict):
                n += walk(v.get("actions"))
        return n
    definition = (wf.get("properties", wf) or {}).get("definition") or {}
    return walk(definition.get("actions"))


# ---------------------------------------------------------------- cloud flow
def cloud_flow_json(bot: dict, groups: list[dict], cfg: dict) -> dict:
    conn = cfg["connection_refs"]
    prefix = cfg.get("env_prefix", "pwc")
    actions, try_actions = {}, {}
    prev = {"top": None, "try": None}

    def add(where, name, definition):
        definition["runAfter"] = {prev[where]: ["Succeeded"]} if prev[where] else {}
        (actions if where == "top" else try_actions)[name] = definition
        prev[where] = name

    desktop_inputs = {safe(v["name"]): f"@triggerBody()?['{safe(v['name'])}']" for v in bot["variables"] if v.get("input")}
    for v in bot["variables"]:
        add("top", "Initialize_" + safe(v["name"]), {"type": "InitializeVariable",
            "inputs": {"variables": [{"name": safe(v["name"]), "type": TYPE_MAP.get(v.get("type"), "string")}]}})

    for g in groups:
        n, k, t = safe(g["package"]) + "_steps", g["package"].lower(), g["target"]
        if t == "Cloud flow":
            if "email" in k:
                add("try", n, {"type": "OpenApiConnection", "inputs": {"host": {"connectionName": conn["office365"], "operationId": "GetEmailsV3",
                    "apiId": "/providers/Microsoft.PowerApps/apis/shared_office365"}, "parameters": {"folderPath": "Inbox", "fetchOnlyUnread": True}}})
            elif re.search(r"rest|http", k):
                add("try", n, {"type": "Http", "inputs": {"method": "GET", "uri": f"@parameters('{prefix}_ApiBaseUrl')", "headers": {"Content-Type": "application/json"}}})
            elif "database" in k:
                add("try", n, {"type": "OpenApiConnection", "inputs": {"host": {"connectionName": conn["sql"], "operationId": "ExecuteQuery", "apiId": "/providers/Microsoft.PowerApps/apis/shared_sql"}}})
            elif "taskbot" in k:
                for c in bot["calls"]:
                    add("try", "Run_child_" + safe(c), {"type": "Workflow", "inputs": {"host": {"workflowReferenceName": safe(c)}, "body": desktop_inputs}})
            elif k.startswith("loop"):
                add("try", n, {"type": "Foreach", "foreach": "@variables('Lines')", "actions": {"Compose_row": {"type": "Compose", "inputs": f"@items('{n}')", "runAfter": {}}}})
            elif k.startswith("if"):
                add("try", n, {"type": "If", "expression": {"and": [{"not": {"equals": ["@variables('DocNo')", ""]}}]}, "actions": {}, "else": {"actions": {}}})
            else:
                add("try", n, {"type": "Compose", "inputs": f"/* {g['count']} {g['package']} action(s): {g['commands']} — implement as expressions */"})
        elif t == "Desktop flow":
            name = "Run_desktop_" + safe(bot["name"])
            if name not in try_actions:
                add("try", name, {"type": "OpenApiConnection", "inputs": {"host": {"connectionName": conn["uiflow"], "operationId": "RunUIFlow_V2",
                    "apiId": "/providers/Microsoft.PowerApps/apis/shared_uiflow"}, "parameters": {"uiFlowType": "desktopFlow", "runMode": "unattended",
                    "workflowId": f"@parameters('{prefix}_pad_{safe(bot['name'])}')", "body": desktop_inputs}}})
        elif t == "AI Builder":
            add("try", "Extract_document", {"type": "OpenApiConnection", "inputs": {"host": {"connectionName": conn["aibuilder"], "operationId": "PredictV2",
                "apiId": "/providers/Microsoft.PowerApps/apis/shared_aibuilder"}, "parameters": {"modelId": f"@parameters('{prefix}_DocumentModelId')"}}})
        else:
            add("try", "GAP_" + safe(g["package"]), {"type": "Compose", "inputs": f"GAP: {g['package']} ({g['count']} actions: {g['commands']}) — {g['reason']}. Developer to implement."})

    add("top", "Scope_Try", {"type": "Scope", "actions": try_actions})
    actions["Scope_Catch"] = {"type": "Scope", "runAfter": {"Scope_Try": ["Failed", "TimedOut"]}, "actions": {
        "Run_ErrorHandler": {"type": "Workflow", "runAfter": {}, "inputs": {"host": {"workflowReferenceName": "Child_ErrorHandler"}, "body": {"flow": bot["name"], "error": "@result('Scope_Try')"}}}}}
    actions["Run_Logger"] = {"type": "Workflow", "runAfter": {"Scope_Catch": ["Succeeded", "Skipped"]}, "inputs": {"host": {"workflowReferenceName": "Child_Logger"},
        "body": {"flow": bot["name"], "status": "@if(equals(result('Scope_Try')[0]['status'],'Succeeded'),'Success','Failed')"}}}

    return {"properties": {"displayName": safe(bot["name"]), "definition": {
                "$schema": cfg["cloud_schema"], "contentVersion": "1.0.0.0",
                "parameters": {"$connections": {"defaultValue": {}, "type": "Object"}, "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
                "triggers": {"manual": {"type": "Request", "kind": "Http", "inputs": {"schema": {"type": "object",
                    "properties": {safe(v["name"]): {"type": "string"} for v in bot["variables"] if v.get("input")}}}}},
                "actions": actions},
            "connectionReferences": {v: {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": v}, "api": {"name": "shared_" + k}} for k, v in conn.items()}},
            "schemaVersion": "1.0.0.0", "_generatedBy": "A360 Migration Studio", "_source": bot["file"]}


# ---------------------------------------------------------------- robin script
def robin_script(bot: dict, groups: list[dict], cfg: dict) -> tuple[str, int]:
    """Returns (script, gap_count)."""
    mapping = {k.lower(): v for k, v in cfg["robin_map"].items()}
    overrides = {g["package"]: g["target"] for g in groups}
    L, gaps = [], 0
    inputs = [_v(v["name"]) for v in bot["variables"] if v.get("input")]
    outputs = [_v(v["name"]) for v in bot["variables"] if v.get("output")]
    vaults = [r.replace("$", "").replace("Vault.", "").replace(".", "_") for r in bot["vault_references"]]
    L += [f"# {bot['name']} — generated desktop flow (Robin)",
          f"# INPUT VARIABLES : {', '.join(inputs + vaults) or 'none'}   ← create in PAD: Variables > Input/output",
          f"# OUTPUT VARIABLES: {', '.join(outputs + ['Status', 'ErrorMessage'])}",
          "# UI ELEMENTS     : re-capture each appmask[] element below in PAD before first run",
          "", "SET Status TO $'''Started'''", "BLOCK"]

    def lit(val, raw):
        s = str(val)
        if raw:
            return s
        return _v(s) if s.startswith("$") else f"$'''{s}'''"

    for a in bot["actions"]:
        if a.get("disabled"):
            continue
        pkg, cmd, t = a["package"], a["command"], a["attributes"]
        key = f"{pkg}:{cmd}".lower()
        target = overrides.get(pkg) or rule_target(pkg)[0]
        if not re.search(r"variable|if|loop|string|number|datetime|error|delay", pkg, re.I):
            if target == "Redesign":
                L.append(f"    # GAP (redesign): {pkg}:{cmd} {json.dumps(t)} — {rule_target(pkg)[1]}"); gaps += 1; continue
            if target != "Desktop flow":
                L.append(f"    # {target.upper()}: {pkg}:{cmd} handled outside this desktop flow"); continue
        m = next((v for k, v in mapping.items() if key.startswith(k)), None)
        if m:
            line = re.sub(r"\{(\w+)(!?)\}", lambda mo: lit(t[mo.group(1)], mo.group(2)) if mo.group(1) in t else (f"<{mo.group(1)}>" if mo.group(2) else f"$'''<{mo.group(1)}>'''"), m)
            L.append("    " + line); continue
        if re.match(r"variable", pkg, re.I) and "assign" in cmd.lower():
            L.append(f"    SET {_v(t.get('name', 'Var'))} TO {lit(t['value'], False) if 'value' in t else chr(36) + chr(39)*3 + '<value>' + chr(39)*3}"); continue
        if re.match(r"if", pkg, re.I):
            L += [f"    IF {str(t.get('condition', '<condition>')).replace('$', '')} THEN", "        # ... nested actions ...", "    END"]; continue
        if re.match(r"loop", pkg, re.I):
            L += [f"    LOOP FOREACH CurrentItem IN {_v(t.get('table', 'Rows'))}", "        # ... nested actions ...", "    END"]; continue
        if re.match(r"error handler", pkg, re.I):
            L.append("    # error handling → ON BLOCK ERROR below"); continue
        if re.match(r"delay", pkg, re.I):
            L.append(f"    WAIT {t.get('seconds', 1)}   # replace with UIAutomation.WaitForWindow where this synchronised UI"); continue
        L.append(f"    # GAP: {pkg}:{cmd} {json.dumps(t)} — paste the equivalent PAD action(s) here"); gaps += 1

    L += ["    SET Status TO $'''Success'''", "ON BLOCK ERROR", "    SET Status TO $'''Failed'''",
          f"    SET ErrorMessage TO $'''Error in {bot['name']}'''", "END"]
    return "\n".join(L), gaps
