"""Configuration endpoints — Bring Your Own LLM, Power Automate schemas, Robin mapping.
Stored in the `config` table so the converter, the model router and the UI share one source of truth.
API keys are stored server-side and returned masked (••••1234)."""
import copy
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..services.defaults import DEFAULT_CONFIG
from ..services import llm as llm_svc

router = APIRouter(prefix="/api/config", tags=["config"])
MASK = "••••"


def load_config(db: Session) -> dict:
    rows = {r.key: r.value for r in db.query(models.Config).all()}
    if not rows:
        for k, v in DEFAULT_CONFIG.items():
            db.add(models.Config(key=k, value=v))
        db.commit()
        rows = copy.deepcopy(DEFAULT_CONFIG)
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(rows)
    # Normalise the LLM block to the single-active-profile shape. Legacy routing / params /
    # governance / prompt keys are dropped — prompt, generation parameters and governance now
    # live in the backend (services.llm) and are not user-editable.
    src = cfg.get("llm")
    if not isinstance(src, dict) or not isinstance(src.get("profiles"), list):
        src = copy.deepcopy(DEFAULT_CONFIG["llm"])
    cfg["llm"] = {
        "profiles": src.get("profiles") or copy.deepcopy(DEFAULT_CONFIG["llm"]["profiles"]),
        "activeProfile": src.get("activeProfile") or "",
        "projectBots": src.get("projectBots", 200),
    }
    return cfg


def _mask(cfg: dict) -> dict:
    out = copy.deepcopy(cfg)
    for p in out["llm"]["profiles"]:
        if p.get("apiKey"):
            p["apiKey"] = MASK + p["apiKey"][-4:]
    return out


def _save(db: Session, data: dict):
    for k, v in data.items():
        row = db.get(models.Config, k)
        if row:
            row.value = v
        else:
            db.add(models.Config(key=k, value=v))
    db.commit()


@router.get("")
def get_config(db: Session = Depends(get_db)):
    return _mask(load_config(db))


@router.put("")
def put_config(body: schemas.ConfigIn, db: Session = Depends(get_db)):
    current = load_config(db)
    stored_keys = {p["id"]: p.get("apiKey", "") for p in current["llm"]["profiles"]}
    data = body.model_dump()
    for p in data["llm"]["profiles"]:
        if (p.get("apiKey") or "").startswith(MASK):        # UI sent the mask back → keep the stored key
            p["apiKey"] = stored_keys.get(p["id"], "")
    _save(db, data)
    return _mask(load_config(db))


@router.post("/reset")
def reset_config(db: Session = Depends(get_db)):
    db.query(models.Config).delete()
    db.commit()
    return _mask(load_config(db))


@router.post("/llm/test/{profile_id}")
async def test_llm(profile_id: str, db: Session = Depends(get_db)):
    """Live connection test with a tiny prompt. Saves the result as the profile's status."""
    cfg = load_config(db)
    profile = next((p for p in cfg["llm"]["profiles"] if p["id"] == profile_id), None)
    if not profile:
        raise HTTPException(404, "Profile not found — save the configuration first")
    result = await llm_svc.test_profile(profile, llm_svc.LLM_PARAMS)
    profile["status"] = "ready" if result["ok"] else "failed"
    _save(db, {"llm": cfg["llm"]})
    db.add(models.LLMCall(task="test", profile_id=profile["id"], profile_label=profile["label"], provider=profile["provider"],
                          model=profile.get("model", ""), status="ok" if result["ok"] else "error", error=result.get("error"),
                          latency_ms=result["latency_ms"]))
    db.commit()
    return result


@router.get("/llm/calls")
def llm_calls(limit: int = 50, db: Session = Depends(get_db)):
    """Recent model calls (audit trail)."""
    rows = db.query(models.LLMCall).order_by(models.LLMCall.id.desc()).limit(limit).all()
    return [{"id": r.id, "task": r.task, "profile": r.profile_label, "model": r.model, "status": r.status, "error": r.error,
             "latency_ms": r.latency_ms, "bot_id": r.bot_id, "project_id": r.project_id, "created_at": r.created_at} for r in rows]
