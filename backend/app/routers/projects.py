"""Project pipeline endpoints: upload/parse → understand → targets → convert → download."""
import io
import json
import os
import tempfile
import zipfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..services import parser, classify, llm, convert
from .config import load_config

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _log(db: Session, project: models.Project, stage: str, message: str):
    db.add(models.RunLog(project_id=project.id, stage=stage, message=message))


def _auditor(db: Session, project: models.Project, cfg: dict):
    keep = llm.LLM_GOVERNANCE.get("logPrompts", True)
    def audit(task, bot_id, profile, status, error, request, response, latency_ms):
        db.add(models.LLMCall(project_id=project.id, bot_id=bot_id, task=task, profile_id=profile["id"], profile_label=profile["label"],
                              provider=profile["provider"], model=profile.get("model", ""), status=status, error=error, latency_ms=latency_ms,
                              request=request if keep else None, response=response if keep else None))
    return audit


async def _understand_bot(db: Session, bot: models.Bot, cfg: dict):
    audit = _auditor(db, bot.project, cfg)
    bd = _bot_dict(bot)
    bot.narrative, llm_target, bot.narrative_source = await llm.understand(bd, cfg, audit, bot.id)
    groups = classify.group_actions(bot.actions)
    bot.classify_source = await llm.classify(bd, groups, bot.narrative, cfg, audit, bot.id)
    bot.groups.clear()
    for g in groups:
        bot.groups.append(models.ActionGroup(**g))
    bot.recommended_target = llm_target or classify.bot_target(groups)
    _log(db, bot.project, "understand", f"{bot.name}: {bot.active_actions} actions → {bot.recommended_target} "
                                        f"(narrative: {bot.narrative_source}; targets: {bot.classify_source})")


def _bot_dict(b: models.Bot) -> dict:
    return {"name": b.name, "file": b.file, "variables": b.variables, "packages": b.packages, "calls": b.calls,
            "vault_references": b.vault_references, "disabled_actions": b.disabled_actions, "actions": b.actions}


# ------------------------------------------------------------------ list / get
@router.get("", response_model=list[schemas.ProjectSummary])
def list_projects(db: Session = Depends(get_db)):
    return db.query(models.Project).order_by(models.Project.id.desc()).all()


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(models.Project, project_id)
    if p:
        db.delete(p); db.commit()


# ------------------------------------------------------------------ 1+2. upload & parse
@router.post("", response_model=schemas.ProjectOut, status_code=201)
async def upload_and_parse(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Accepts a Control Room export (.zip) or a single task-bot .json. Parsing is deterministic (no LLM)."""
    data = await file.read()
    suffix = ".zip" if file.filename.lower().endswith(".zip") else ".json"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data); path = tmp.name
    try:
        parsed = parser.parse_export(path)
    finally:
        os.unlink(path)
    if not parsed["bots"]:
        raise HTTPException(400, "No task-bot JSON (objects with a 'nodes' array) found in the upload.")

    project = models.Project(name=os.path.splitext(file.filename)[0], source_file=file.filename, task_bots=parsed["task_bots"],
                             active_actions=parsed["active_actions"], disabled_actions=parsed["disabled_actions"], roots=parsed["roots"])
    db.add(project); db.flush()
    for b in parsed["bots"]:
        bot = models.Bot(project_id=project.id, name=b["name"], file=b["file"], active_actions=b["active_actions"],
                         disabled_actions=b["disabled_actions"], max_nesting_depth=b["max_nesting_depth"],
                         complexity_score=b["complexity_score"], complexity=b["complexity"], variables=b["variables"],
                         packages=b["packages"], calls=b["calls"], called_by=b["called_by"], vault_references=b["vault_references"],
                         global_value_references=b["global_value_references"], actions=b["actions"])
        db.add(bot)
    _log(db, project, "parse", f"Parsed {file.filename}: {parsed['task_bots']} task bots, {parsed['active_actions']} active / {parsed['disabled_actions']} disabled actions")
    db.commit(); db.refresh(project)
    return project


# ------------------------------------------------------------------ 3. understand (one bot per call)
@router.post("/{project_id}/understand", response_model=schemas.ProjectOut)
async def understand(project_id: int, db: Session = Depends(get_db)):
    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    cfg = load_config(db)
    for bot in p.bots:
        await _understand_bot(db, bot, cfg)
        db.commit()          # commit per bot so progress is visible if the client polls
    p.status = "understood"; db.commit(); db.refresh(p)
    return p


@router.post("/{project_id}/bots/{bot_id}/understand", response_model=schemas.BotOut)
async def understand_one(project_id: int, bot_id: int, db: Session = Depends(get_db)):
    """Per-bot variant — lets the UI show progress bot by bot and stay under model input limits."""
    bot = db.get(models.Bot, bot_id)
    if not bot or bot.project_id != project_id:
        raise HTTPException(404, "Bot not found")
    await _understand_bot(db, bot, load_config(db))
    if all(b.narrative for b in bot.project.bots):
        bot.project.status = "understood"
    db.commit(); db.refresh(bot)
    return bot


# ------------------------------------------------------------------ SA override of a target
@router.patch("/{project_id}/groups/{group_id}", response_model=schemas.BotOut)
def set_target(project_id: int, group_id: int, body: schemas.TargetUpdate, db: Session = Depends(get_db)):
    g = db.get(models.ActionGroup, group_id)
    if not g or g.bot.project_id != project_id:
        raise HTTPException(404, "Group not found")
    if body.target not in classify.TARGETS:
        raise HTTPException(400, f"target must be one of {classify.TARGETS}")
    g.target = body.target
    g.bot.recommended_target = classify.bot_target(g.bot.groups)
    _log(db, g.bot.project, "review", f"{g.bot.name} / {g.package}: target set to {body.target}")
    db.commit(); db.refresh(g.bot)
    return g.bot


# ------------------------------------------------------------------ 4. convert
@router.post("/{project_id}/convert", response_model=schemas.ProjectOut)
async def convert_all(project_id: int, db: Session = Depends(get_db)):
    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    cfg = load_config(db)
    for bot in p.bots:
        await _convert_bot(db, bot, cfg)
    p.status = "converted"; db.commit(); db.refresh(p)
    return p


@router.post("/{project_id}/bots/{bot_id}/convert", response_model=schemas.BotOut)
async def convert_one(project_id: int, bot_id: int, db: Session = Depends(get_db)):
    bot = db.get(models.Bot, bot_id)
    if not bot or bot.project_id != project_id:
        raise HTTPException(404, "Bot not found")
    await _convert_bot(db, bot, load_config(db))
    if all(b.artifacts for b in bot.project.bots):
        bot.project.status = "converted"
    db.commit(); db.refresh(bot)
    return bot


async def _convert_bot(db: Session, bot: models.Bot, cfg: dict):
    groups = [{"package": g.package, "count": g.count, "commands": g.commands, "target": g.target, "reason": g.reason} for g in bot.groups] \
        or classify.group_actions(bot.actions)
    bd = _bot_dict(bot)
    auditor = _auditor(db, bot.project, cfg)
    bot.artifacts.clear()

    cloud, clabel = await llm.convert_cloud(bd, groups, cfg, auditor, bot.id)
    if cloud is None:
        cloud = convert.cloud_flow_json(bd, groups, cfg)
        clabel = "template"
    bot.artifacts.append(models.Artifact(kind="cloud", filename=f"{convert.safe(bot.name)}.json", content=json.dumps(cloud, indent=2),
                                         gap_count=convert.cloud_gap_count(cloud)))
    msg = f"cloud flow ({clabel})"
    if any(g["target"] == "Desktop flow" for g in groups):
        script, rlabel = await llm.convert_robin(bd, groups, cfg, auditor, bot.id)
        if script is None:
            script, gaps = convert.robin_script(bd, groups, cfg)
            rlabel = "template"
        else:
            gaps = script.count("# GAP")
        script, suggested = await llm.gap_assist(bot.name, script, cfg, auditor, bot.id)
        bot.artifacts.append(models.Artifact(kind="robin", filename=f"{convert.safe(bot.name)}.robin", content=script, gap_count=gaps))
        msg += f" + desktop flow (Robin, {rlabel}, {gaps} GAP lines" + (f", {suggested} with model suggestions" if suggested else "") + ")"
    _log(db, bot.project, "convert", f"{bot.name}: {msg}")
    db.commit()


# ------------------------------------------------------------------ download artefacts
@router.get("/{project_id}/artifacts/{artifact_id}")
def get_artifact(project_id: int, artifact_id: int, db: Session = Depends(get_db)):
    a = db.get(models.Artifact, artifact_id)
    if not a or a.bot.project_id != project_id:
        raise HTTPException(404, "Artifact not found")
    media = "application/json" if a.kind == "cloud" else "text/plain"
    return PlainTextResponse(a.content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{a.filename}"'})


@router.get("/{project_id}/export.zip")
def export_zip(project_id: int, db: Session = Depends(get_db)):
    """All generated artefacts for the project as one zip (cloud/*.json, desktop/*.robin, README)."""
    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        readme = [f"# {p.name} — generated by A360 Migration Studio", "", "cloud/   workflow-definition JSON per bot (wrap in a solution or paste via Logic Apps code view)",
                  "desktop/ Robin scripts — open PAD, new flow, click canvas, Ctrl+V; create variables listed in the header; re-capture appmask[] elements", ""]
        for b in p.bots:
            for a in b.artifacts:
                z.writestr(f"{'cloud' if a.kind == 'cloud' else 'desktop'}/{a.filename}", a.content)
                readme.append(f"- {b.name}: {a.filename} ({a.gap_count} GAP)")
        z.writestr("README.md", "\n".join(readme))
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{convert.safe(p.name)}_artifacts.zip"'})


# ------------------------------------------------------------------ BYO LLM: what would be sent, and what it would cost
@router.get("/{project_id}/llm-preview")
def llm_preview(project_id: int, bot_id: int | None = None, db: Session = Depends(get_db)):
    """The exact first request body for a bot after the governance rules are applied — nothing is sent."""
    p = db.get(models.Project, project_id)
    if not p or not p.bots:
        raise HTTPException(404, "Project not found")
    bot = next((b for b in p.bots if b.id == bot_id), None) or next((b for b in p.bots if b.active_actions), p.bots[0])
    return {"bot_id": bot.id, "bot": bot.name, "requests": llm.chunk_count(_bot_dict(bot)),
            "payload": llm.build_payload(_bot_dict(bot))}


@router.get("/{project_id}/llm-estimate")
def llm_estimate(project_id: int, db: Session = Depends(get_db)):
    """Token estimate for functional understanding across the project (prices come from each profile)."""
    p = db.get(models.Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    t_in = t_out = calls = 0
    for b in p.bots:
        n = llm.chunk_count(_bot_dict(b))
        calls += n + (1 if n > 1 else 0)
        t_in += n * (len(llm.LLM_PROMPT) / 4 + 120 + len(b.variables) * 18) + b.active_actions * 34 + (n * 320 if n > 1 else 0)
        t_out += n * 320 + (380 if n > 1 else 0)
    return {"bots": len(p.bots), "requests": calls, "input_tokens": round(t_in), "output_tokens": round(t_out)}
