"""Language evaluation panel (PRD 8.5). Results shown are only ever read from stored runs."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import Role
from app.models import EvalRun
from app.security import Staff, require_roles
from app.services import evaluation

router = APIRouter(prefix="/v1/evals", tags=["evaluation"])
allowed = require_roles(Role.ADMIN, Role.DOCTOR, Role.NURSE, Role.OPERATOR)


@router.get("/corpus")
def corpus(_: Staff = Depends(allowed)) -> dict:
    c = evaluation.load_corpus()
    langs: dict[str, int] = {}
    for item in c["items"]:
        langs[item["lang"]] = langs.get(item["lang"], 0) + 1
    return {"version": c["version"], "reference_date": c["reference_date"], "description": c.get("description", ""),
            "count": len(c["items"]), "by_language": langs, "items": c["items"]}


class RunIn(BaseModel):
    provider: Literal["rules", "sarvam", "openai"] = "rules"


@router.post("/runs", status_code=201)
def start_run(body: RunIn, staff: Staff = Depends(allowed), db: Session = Depends(get_db)) -> dict:
    running = db.scalar(select(EvalRun).where(EvalRun.status == "RUNNING"))
    if running:
        raise HTTPException(409, "An evaluation is already running. Wait for it to finish.")
    run = evaluation.start_run(db, body.provider, staff.label)
    db.commit()  # the run executes after commit (worker, or inline in eager mode)
    db.refresh(run)
    return {"id": str(run.id), "status": run.status}


@router.get("/runs")
def list_runs(_: Staff = Depends(allowed), db: Session = Depends(get_db)) -> dict:
    runs = db.scalars(select(EvalRun).order_by(EvalRun.started_at.desc()).limit(50)).all()
    return {"runs": [{"id": str(r.id), "provider": r.provider, "model": r.model, "status": r.status,
                      "corpus_version": r.corpus_version, "items": r.item_count, "exact_match": r.exact_match_count,
                      "fallbacks": r.error_count, "started_at": r.started_at.isoformat(),
                      "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                      "triggered_by": r.triggered_by} for r in runs]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, _: Staff = Depends(allowed), db: Session = Depends(get_db)) -> dict:
    from app.services.guards import _uuid

    rid = _uuid(run_id)
    run = db.get(EvalRun, rid) if rid else None
    if run is None:
        raise HTTPException(404, "Run not found.")
    return evaluation.summary(db, run)
