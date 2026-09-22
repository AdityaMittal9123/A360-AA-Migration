"""Bring Your Own LLM.

Model profiles (any number, any provider) are stored in config["llm"]["profiles"].
A SINGLE profile is selected via config["llm"]["activeProfile"] and is used for every LLM task:
    understand  – structured functional narrative + recommended target (Understand stage)
    classify    – re-check the rule-based target per group (Understand stage)
    convert     – generate cloud-flow JSON / Robin script (Convert stage)
    gapfill     – propose PAD actions for '# GAP' lines   (Convert stage)
One model, all tasks. If none is selected, or a call fails after its retries, the rule set answers
so the pipeline never blocks.

Prompt, generation parameters and governance are backend-owned (LLM_PROMPT / LLM_PARAMS /
LLM_GOVERNANCE below) and are NOT exposed to the configuration UI. Before anything is sent, the
governance rules mask business data (literal values, vault references, paths/URLs/emails). Every
call is written to the llm_calls audit table; prompt/response bodies are stored only if
governance.logPrompts is on.

Providers: azure · openai · anthropic · gemini (OpenAI-compatible endpoint) ·
           copilot (Copilot Studio agent via Direct Line) · local (Ollama/vLLM/LM Studio,
           OpenAI-compatible) · custom (any HTTP gateway via body template + response path)
"""
import asyncio
import json
import re
import time
from typing import Callable, Optional

import httpx

from .classify import TARGETS
from . import classify as classify_svc, convert as convert_svc

# ---------------------------------------------------------------- masking
STRUCTURAL_KEYS = {"botpath", "tcode", "id", "learninginstance", "queue", "sheet", "table", "name", "condition",
                   "output", "title", "control", "template", "seconds", "priority"}
PUBLIC_PROVIDERS = {"openai", "anthropic", "gemini"}

# Backend-owned LLM settings — deliberately NOT exposed in the configuration UI.
LLM_PARAMS = {"temperature": 0.2, "maxTokens": 4000, "chunkSize": 150, "timeout": 120, "retries": 2}
LLM_GOVERNANCE = {"maskValues": True, "stripVault": True, "stripPaths": True, "logPrompts": True, "residency": "uk-eu"}
LLM_PROMPT = (
    "You are a migration engineer. You receive the parsed actions of ONE Automation Anywhere A360 task bot as JSON (bot {{bot}}, part {{part}}).\n"
    'Reply with JSON ONLY — exactly this shape:\n'
    '{"narrative": "<5-8 sentence functional narrative: trigger + inputs, what the bot does step by step, external systems touched, '
    'error handling present, outputs, anything that will not convert cleanly to Power Automate (macros, DLLs, IQ Bot, vault references)>", '
    '"target": "<ONE of: Cloud flow | Desktop flow | Hybrid (cloud + desktop) | AI Builder | Redesign>", '
    '"reason": "<<=20 words explaining the recommended target>"}\n'
    "Plain English narrative, no markdown. Values shown as <masked>, <path>, <url>, <email> or <vault-ref> were redacted by policy — do not guess them."
)
RECOMMENDED_TARGETS = TARGETS + ["Hybrid (cloud + desktop)"]
UNDERSTAND_CONTRACT = (
    '\nReply with JSON ONLY in exactly this shape: '
    '{"narrative": "<5-8 sentence functional narrative>", '
    '"target": "<ONE of: Cloud flow | Desktop flow | Hybrid (cloud + desktop) | AI Builder | Redesign>", '
    '"reason": "<reason for the target, <=20 words>"} '
    'Do not add anything outside the JSON object.'
)
MAX_CONVERT_ACTIONS = 400
CONVERT_PARAMS = {**LLM_PARAMS, "maxTokens": 6000, "temperature": 0.0}


def mask_value(v, gov: dict, key: str = ""):
    s = str(v)
    if gov.get("stripVault") and "$Vault." in s:
        return "<vault-ref>"
    if re.fullmatch(r"\$[^$]+\$", s):
        return s
    if gov.get("stripPaths"):
        if re.match(r"https?://", s, re.I):
            return "<url>"
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", s):
            return "<email>"
        if re.match(r"^[a-z]:\\|^\\\\|^/", s, re.I):
            return "<path>"
    if gov.get("maskValues") and s and s.lower() not in ("true", "false"):
        if key.lower() in STRUCTURAL_KEYS or re.search(r"\$[^$\s]+\$", s):
            s = re.sub(r"(['\"])[^'\"]*\1", r"\1<masked>\1", s)
            return re.sub(r"\b\d{4,}\b", "<n>", s)
        return "<masked>"
    return s


def build_payload(bot: dict, part: int = 0) -> dict:
    gov, n = LLM_GOVERNANCE, int(LLM_PARAMS["chunkSize"])
    acts = [a for a in bot["actions"] if not a.get("disabled")]
    chunks = max(1, -(-len(acts) // n))
    return {
        "bot": bot["name"], "part": f"{part + 1}/{chunks}",
        "vault_references": ["<vault-ref>"] * len(bot["vault_references"]) if gov.get("stripVault") else bot["vault_references"],
        "actions": [{"package": a["package"], "command": a["command"], "depth": a["depth"],
                     "attributes": {k: mask_value(v, gov, k) for k, v in a["attributes"].items()}}
                    for a in acts[part * n:(part + 1) * n]],
        "variables": bot["variables"], "calls": bot["calls"],
    }


def chunk_count(bot: dict) -> int:
    n = int(LLM_PARAMS["chunkSize"])
    return max(1, -(-sum(1 for a in bot["actions"] if not a.get("disabled")) // n))


# ---------------------------------------------------------------- provider adapters
class LLMError(Exception):
    pass


async def call_profile(profile: dict, system: str, user: str, params: dict) -> str:
    prov = profile["provider"]
    timeout = float(params.get("timeout", 90))
    temp, max_tokens = float(params.get("temperature", 0.2)), int(params.get("maxTokens", 1200))
    ep = (profile.get("endpoint") or "").rstrip("/")
    key = profile.get("apiKey") or ""
    async with httpx.AsyncClient(timeout=timeout) as c:
        if prov == "anthropic":
            r = await c.post(ep + "/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                             json={"model": profile["model"], "max_tokens": max_tokens, "temperature": temp, "system": system,
                                   "messages": [{"role": "user", "content": user}]})
            _raise(r)
            return "".join(b.get("text", "") for b in r.json().get("content", []))

        if prov == "azure":
            url = f"{_azure_base(ep)}/openai/deployments/{profile['model']}/chat/completions?api-version={profile.get('apiVersion', '2024-10-21')}"
            r = await c.post(url, headers={"api-key": key}, json={"temperature": temp, "max_tokens": max_tokens,
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
            _raise(r)
            return r.json()["choices"][0]["message"]["content"]

        if prov in ("openai", "gemini", "local"):
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            r = await c.post(ep + "/chat/completions", headers=headers, json={"model": profile["model"], "temperature": temp, "max_tokens": max_tokens,
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
            _raise(r)
            return r.json()["choices"][0]["message"]["content"]

        if prov == "copilot":
            return await _direct_line(c, ep, key, system + "\n\n" + user, timeout)

        if prov == "custom":
            esc = lambda s: json.dumps(str(s))[1:-1]
            subs = {"system": system, "user": user, "model": profile.get("model", ""), "apiKey": key,
                    "temperature": temp, "maxTokens": max_tokens}
            fill = lambda t: re.sub(r"\{\{(\w+)\}\}", lambda m: esc(subs.get(m.group(1), "")), t or "")
            headers = json.loads(fill(profile.get("headers") or "{}"))
            body = json.loads(fill(profile.get("bodyTemplate") or "{}"))
            r = await c.post(ep, headers=headers, json=body)
            _raise(r)
            return _dig(r.json(), profile.get("responsePath") or "text")

    raise LLMError(f"Unknown provider '{prov}'")


async def _direct_line(c: httpx.AsyncClient, ep: str, secret: str, text: str, timeout: float) -> str:
    """Copilot Studio agent over the Direct Line 3.0 channel."""
    h = {"Authorization": f"Bearer {secret}"}
    r = await c.post(f"{ep}/conversations", headers=h); _raise(r)
    conv = r.json()
    cid = conv["conversationId"]
    if conv.get("token"):
        h = {"Authorization": f"Bearer {conv['token']}"}
    r = await c.post(f"{ep}/conversations/{cid}/activities", headers=h,
                     json={"type": "message", "from": {"id": "migration-studio"}, "text": text}); _raise(r)
    deadline, watermark = time.monotonic() + timeout, None
    while time.monotonic() < deadline:
        await asyncio.sleep(1.5)
        url = f"{ep}/conversations/{cid}/activities" + (f"?watermark={watermark}" if watermark else "")
        r = await c.get(url, headers=h); _raise(r)
        data = r.json(); watermark = data.get("watermark")
        replies = [a.get("text", "") for a in data.get("activities", [])
                   if a.get("type") == "message" and a.get("from", {}).get("id") != "migration-studio" and a.get("text")]
        if replies:
            return "\n".join(replies)
    raise LLMError("Copilot Studio agent did not reply before the timeout")


def _dig(obj, path: str):
    for part in path.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj if isinstance(obj, str) else json.dumps(obj)


def _raise(r: httpx.Response):
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")


def _azure_base(endpoint: str) -> str:
    """Azure OpenAI endpoint may be the resource base or a full deployment URL
    pasted from the portal — always reduce it to the resource base before adding the path."""
    base = endpoint.split("?", 1)[0]
    i = base.find("/openai/deployments/")
    if i != -1:
        base = base[:i]
    return base.rstrip("/")


# ---------------------------------------------------------------- routing with fallback
Audit = Callable[..., None]


async def run_task(task: str, system: str, user: str, cfg: dict, audit: Audit, bot_id: Optional[int] = None,
                   params_override: Optional[dict] = None):
    """Runs `task` through the single active model. Returns (text or None, profile label or None).
    No model selected or any failure → (None, None) so the caller falls back to the rule set."""
    llm = cfg["llm"]
    pid = llm.get("activeProfile") or ""
    if not pid or pid == "rules":
        return None, None
    profile = next((p for p in llm["profiles"] if p["id"] == pid), None)
    if not profile:
        return None, None
    if LLM_GOVERNANCE.get("residency") == "tenant" and profile["provider"] in PUBLIC_PROVIDERS:
        audit(task=task, bot_id=bot_id, profile=profile, status="blocked", error="Residency policy: client tenant only", request=user, response=None, latency_ms=0)
        return None, None
    params = {**LLM_PARAMS, **(params_override or {})}
    retries = int(LLM_PARAMS.get("retries", 2))
    for attempt in range(retries + 1):
        t0 = time.monotonic()
        try:
            text = await call_profile(profile, system, user, params)
            audit(task=task, bot_id=bot_id, profile=profile, status="ok", error=None, request=user, response=text, latency_ms=int((time.monotonic() - t0) * 1000))
            return text.strip(), profile["label"]
        except Exception as e:
            audit(task=task, bot_id=bot_id, profile=profile, status="error", error=f"{type(e).__name__}: {e}"[:500], request=user, response=None, latency_ms=int((time.monotonic() - t0) * 1000))
            if attempt < retries:
                await asyncio.sleep(min(2 ** attempt, 8))
    return None, None


# ---------------------------------------------------------------- tasks
def rule_narrative(bot: dict) -> str:
    p = [k.lower() for k in bot["packages"].keys()]
    parts = []
    if any("email" in x for x in p): parts.append("polls a mailbox for incoming emails and attachments")
    if any("iq bot" in x or "iqbot" in x for x in p): parts.append("extracts fields from documents using an IQ Bot learning instance")
    if any("excel" in x for x in p): parts.append("reads and writes Excel workbooks for lookups and rules")
    if any("workload" in x or "wlm" in x for x in p): parts.append("creates work items in a WLM queue")
    if any("sap" in x for x in p): parts.append("drives SAP GUI transactions via scripting and reads results from the status bar")
    if any("rest" in x or "http" in x for x in p): parts.append("calls REST APIs")
    if any("database" in x for x in p): parts.append("queries a database")
    if any("recorder" in x or "browser" in x for x in p): parts.append("performs UI automation on desktop or web applications")
    if bot.get("calls"): parts.append(f"orchestrates {len(bot['calls'])} sub-task bot(s): {', '.join(bot['calls'])}")
    if not parts: parts.append("applies variable, string and conditional logic on its inputs")
    ins = ", ".join(v["name"] for v in bot["variables"] if v.get("input")) or "none"
    outs = ", ".join(v["name"] for v in bot["variables"] if v.get("output")) or "none"
    eh = "try/catch present" if any("error" in x for x in p) else "none — standard error pattern will be injected"
    extra = []
    if bot.get("vault_references"): extra.append(f"{len(bot['vault_references'])} Credential Vault reference(s) must move to Key Vault")
    if bot.get("disabled_actions"): extra.append(f"{bot['disabled_actions']} disabled action(s) will be dropped")
    return f"{bot['name']} {'; '.join(parts)}. Inputs: {ins}. Outputs: {outs}. Error handling: {eh}. {'. '.join(extra)}".strip()


def _rule_understanding(bot: dict) -> tuple[str, str]:
    """Deterministic fallback: narrative + bot-level target from the rule groups."""
    groups = classify_svc.group_actions(bot["actions"])
    return rule_narrative(bot), classify_svc.bot_target(groups)


def _parse_understanding(text: str, bot: dict) -> tuple[str, str | None]:
    """Extract (narrative, recommended_target) from the model's JSON. Unparseable → keep raw text, target=None."""
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            narrative = str(d.get("narrative") or "").strip()
            target = d.get("target")
            if target not in RECOMMENDED_TARGETS:
                target = None
            if narrative:
                return narrative, target
        except Exception:
            pass
    return text.strip() or _rule_understanding(bot)[0], None


async def understand(bot: dict, cfg: dict, audit: Audit, bot_id=None):
    """Structured functional understanding → (narrative, recommended_target, source).
    recommended_target is the model's cloud/desktop/hybrid call (or None); the caller falls back to the rule target."""
    n = chunk_count(bot)
    parts, label = [], None
    for i in range(n):
        system = LLM_PROMPT.replace("{{bot}}", bot["name"]).replace("{{part}}", f"{i + 1}/{n}") + UNDERSTAND_CONTRACT
        text, label = await run_task("understand", system, json.dumps(build_payload(bot, i)), cfg, audit, bot_id)
        if text is None:
            narrative, target = _rule_understanding(bot)
            return narrative, target, "rules"
        parts.append(text)
    if n == 1:
        narrative, target = _parse_understanding(parts[0], bot)
        return narrative, target, label
    merged, label2 = await run_task("understand",
        "Merge these partial narratives of ONE A360 bot into a single coherent narrative." + UNDERSTAND_CONTRACT,
        "\n\n---\n\n".join(parts), cfg, audit, bot_id)
    narrative, target = _parse_understanding(merged or " ".join(parts), bot)
    return narrative, target, (label2 or label)


async def classify(bot: dict, groups: list[dict], narrative: str, cfg: dict, audit: Audit, bot_id=None) -> str:
    """Model re-checks the rule-based target per action group. Mutates groups in place. Returns source."""
    system = ("You classify Automation Anywhere action groups for migration to Microsoft Power Platform. "
              f"Allowed targets: {', '.join(TARGETS)}. Reply with JSON only: "
              '[{"package": "...", "target": "...", "reason": "<= 20 words"}]')
    user = json.dumps({"bot": bot["name"], "narrative": narrative,
                       "groups": [{"package": g["package"], "count": g["count"], "commands": g["commands"], "rule_target": g["suggested_target"]} for g in groups]})
    text, label = await run_task("classify", system, user, cfg, audit, bot_id)
    if not text:
        return "rules"
    try:
        data = json.loads(re.search(r"\[.*\]", text, re.S).group(0))
        by_pkg = {d["package"]: d for d in data if d.get("target") in TARGETS}
        for g in groups:
            d = by_pkg.get(g["package"])
            if d:
                g["suggested_target"] = g["target"] = d["target"]
                g["reason"] = f"{label}: {d.get('reason', '')}"[:300]
        return label
    except Exception:
        return "rules"


# ---------------------------------------------------------------- conversion tasks
def _convert_payload(bot: dict) -> dict:
    """Masked bot actions for the conversion prompts (capped so the request stays bounded)."""
    gov = LLM_GOVERNANCE
    active = [a for a in bot["actions"] if not a.get("disabled")]
    truncated = len(active) > MAX_CONVERT_ACTIONS
    return {
        "bot": bot["name"],
        "variables": bot["variables"],
        "calls": bot["calls"],
        "actions": [{"package": a["package"], "command": a["command"], "depth": a["depth"],
                     "attributes": {k: mask_value(v, gov, k) for k, v in a["attributes"].items()}}
                    for a in active[:MAX_CONVERT_ACTIONS]],
        "truncated": f"showing first {MAX_CONVERT_ACTIONS} of {len(active)} active actions" if truncated else None,
    }


async def convert_cloud(bot: dict, groups: list[dict], cfg: dict, audit: Audit, bot_id=None):
    """Model generates the full cloud-flow workflow definition. Returns (workflow dict, label) or (None, None) → template fallback."""
    scaffold = convert_svc.cloud_flow_json(bot, groups, cfg)
    system = (
        "You are a Power Platform migration engineer converting an Automation Anywhere A360 task bot into a Power Automate cloud flow.\n"
        "You receive: the parsed bot actions (literal values redacted — never invent data), the FINALIZED target per action group "
        "(approved by a solution architect), and a REFERENCE workflow-definition JSON produced by the existing template.\n"
        "Produce a complete cloud flow definition driven by the targets: Cloud flow / AI Builder groups become connector/HTTP steps and "
        "expression, If, Foreach and Scope logic inside the workflow; Desktop flow / Redesign groups become a single placeholder action "
        "that runs a desktop flow or marks a gap for the developer.\n"
        "Keep the REFERENCE structure exactly: properties.definition with $schema, contentVersion, parameters, triggers and actions; "
        "and connectionReferences using the same logical names.\n"
        "Where you cannot express an action safely, keep a Compose action named GAP_<package> with a one-line note for the developer.\n"
        "Reply with the workflow JSON ONLY — no markdown fences, no commentary. It must parse as JSON."
    )
    user = json.dumps({"bot": _convert_payload(bot),
                       "groups": [{"package": g["package"], "count": g["count"], "commands": g["commands"],
                                   "target": g["target"], "reason": g["reason"]} for g in groups],
                       "reference_workflow": scaffold})
    text, label = await run_task("convert", system, user, cfg, audit, bot_id, params_override=CONVERT_PARAMS)
    if not text:
        return None, None
    try:
        m = re.search(r"\{.*\}", text, re.S)
        doc = json.loads(m.group(0)) if m else None
        if doc is None:
            return None, label
        wf = doc.get("properties", doc)
        definition = wf.get("definition")
        if not isinstance(definition, dict) or not isinstance(definition.get("actions"), dict):
            return None, label
        definition["_convertedBy"] = f"LLM · {label}"
        doc["_generatedBy"] = f"A360 Migration Studio · {label}"
        return doc, label
    except Exception:
        return None, label


async def convert_robin(bot: dict, groups: list[dict], cfg: dict, audit: Audit, bot_id=None):
    """Model generates the full PAD (Robin) desktop-flow script. Returns (script, label) or (None, None) → template fallback."""
    template, _ = convert_svc.robin_script(bot, groups, cfg)
    system = (
        "You are a Power Platform migration engineer converting an Automation Anywhere A360 task bot into a Power Automate for desktop flow "
        "written in Robin script syntax (the text format produced when you copy/paste actions in the PAD designer).\n"
        "You receive: the parsed bot actions (literal values redacted — never invent data), the FINALIZED target per package, a REFERENCE "
        "Robin script from the template, and a PAD SAMPLE that is the authoritative syntax for the target PAD version.\n"
        "Produce the complete Robin script: header comment block (INPUT VARIABLES, OUTPUT VARIABLES, UI ELEMENTS), SET Status TO 'Started' "
        "and a BLOCK, then SET / IF / LOOP / WAIT / action lines using ONLY the PAD SAMPLE syntax. Actions whose package target is not "
        "Desktop flow stay as a short comment (they convert on the cloud side).\n"
        "Where there is no safe PAD equivalent emit '# GAP: <package>:<command> <redacted attrs> — paste the equivalent PAD action(s)'.\n"
        "Finish with 'SET Status TO 'Success'', 'ON BLOCK ERROR' and error handling before 'END'.\n"
        "Output ONLY the Robin script — no markdown fences, no commentary outside comments."
    )
    user = json.dumps({"bot": _convert_payload(bot),
                       "targets": {g["package"]: g["target"] for g in groups},
                       "reference_script": template,
                       "pad_sample": cfg.get("pad_sample", "")})
    text, label = await run_task("convert", system, user, cfg, audit, bot_id, params_override=CONVERT_PARAMS)
    if not text or not text.strip():
        return None, None
    cleaned = text.strip()
    cleaned = re.sub(r"^```[A-Za-z]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return cleaned, label


def _mask_gap_line(line: str, gov: dict) -> str:
    """GAP lines embed the raw A360 attributes as JSON — apply the same governance masking before sending."""
    start = line.find("{")
    if start < 0:
        return line
    try:
        attrs, end = json.JSONDecoder().raw_decode(line[start:])
    except ValueError:
        return line[:start] + "{<attributes withheld>}"
    masked = {k: mask_value(v, gov, k) for k, v in attrs.items()} if isinstance(attrs, dict) else "<attributes withheld>"
    return line[:start] + json.dumps(masked) + line[start + end:]


async def gap_assist(bot_name: str, script: str, cfg: dict, audit: Audit, bot_id=None) -> tuple[str, int]:
    """Model proposes Robin for '# GAP' lines. Suggestions are inserted under each GAP, marked for review."""
    lines = script.split("\n")
    gaps = [(i, l.strip()) for i, l in enumerate(lines) if l.strip().startswith("# GAP")]
    if not gaps:
        return script, 0
    system = ("You write Power Automate for desktop (Robin) actions. Use ONLY syntax consistent with the sample below. "
              "If there is no safe equivalent, return an empty string for that item. Reply with JSON only: "
              '[{"line": <int>, "robin": "<one or more Robin lines separated by \\n>"}]\n\nPAD SAMPLE:\n' + cfg.get("pad_sample", ""))
    gov = LLM_GOVERNANCE
    user = json.dumps({"bot": bot_name, "gaps": [{"line": i, "gap": _mask_gap_line(g, gov)} for i, g in gaps]})
    text, label = await run_task("gapfill", system, user, cfg, audit, bot_id)
    if not text:
        return script, 0
    try:
        sugg = {int(d["line"]): d["robin"] for d in json.loads(re.search(r"\[.*\]", text, re.S).group(0)) if d.get("robin")}
    except Exception:
        return script, 0
    out, n = [], 0
    for i, l in enumerate(lines):
        out.append(l)
        if i in sugg:
            indent = re.match(r"\s*", l).group(0)
            out.append(f"{indent}# SUGGESTED by {label} — review before use:")
            out += [indent + s for s in sugg[i].split("\n")]
            n += 1
    return "\n".join(out), n


async def test_profile(profile: dict, params: dict) -> dict:
    t0 = time.monotonic()
    try:
        text = await call_profile(profile, "Reply with the single word OK.", "ping", {**params, "maxTokens": 10})
        return {"ok": True, "latency_ms": int((time.monotonic() - t0) * 1000), "reply": text.strip()[:80]}
    except Exception as e:
        return {"ok": False, "latency_ms": int((time.monotonic() - t0) * 1000), "error": f"{type(e).__name__}: {e}"[:400]}
