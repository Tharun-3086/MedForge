"""Language evaluation (PRD 8.5, FR-27). Runs the configured understanding pipeline over the versioned
synthetic corpus and stores per-item results. Numbers shown in the UI come only from these stored runs."""
from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import pipeline
from app.ai.dates import DAY_AFTER, TOMORROW, resolve_day_expression
from app.db import utcnow
from app.jobs import defer
from app.models import EvalResult, EvalRun

CORPUS_PATH = Path(__file__).resolve().parents[2] / "eval" / "corpus_v1.json"


@lru_cache
def load_corpus() -> dict[str, Any]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def start_run(db: Session, provider: str, triggered_by: str) -> EvalRun:
    provider = provider.lower()
    if provider != "rules" and pipeline.get_llm(provider) is None:
        raise HTTPException(422, f"{provider} is not configured. Add its API key in backend/.env first.")
    llm = pipeline.get_llm(provider) if provider != "rules" else None
    corpus = load_corpus()
    run = EvalRun(corpus_version=corpus["version"], provider=provider, model=llm.model if llm else "rules-v1",
                  status="RUNNING", item_count=len(corpus["items"]), triggered_by=triggered_by)
    db.add(run)
    db.flush()
    defer(db, "run_eval", run.id)
    return run


def _day_label(day_text: str | None, ref: date) -> str | None:
    if not day_text:
        return None
    res = resolve_day_expression(day_text, ref)
    if res.kind == "WEEKDAY" and res.candidate:
        return res.candidate.strftime("%A").lower()
    if res.kind == "RELATIVE":
        return "tomorrow" if res.matched in TOMORROW else ("day_after_tomorrow" if res.matched in DAY_AFTER else None)
    if res.kind == "EXPLICIT" and res.candidate:
        return res.candidate.isoformat()
    return None


def execute_run(db: Session, run_id: uuid.UUID) -> None:
    run = db.get(EvalRun, run_id)
    if run is None or run.status != "RUNNING":
        return
    corpus = load_corpus()
    ref = date.fromisoformat(corpus["reference_date"])
    exact = errors = 0
    for item in corpus["items"]:
        started = time.monotonic()
        res = pipeline.understand_reply(item["text"], today=ref, preferred_language=item["lang"][:2],
                                        provider=run.provider)
        latency = int((time.monotonic() - started) * 1000)
        u = res.understanding
        predicted = sorted(i.value for i in u.intents)
        expected = sorted(item["intents"])
        fell_back = run.provider != "rules" and res.source == "RULES"
        pf: dict[str, Any] = {"day": _day_label(u.requested_day_text or (u.requested_date.isoformat() if u.requested_date else None), ref),
                              "barrier": u.barrier_category, "needs_clarification": u.needs_clarification,
                              "confidence": u.confidence, "source": res.source}
        exp_f = item.get("fields", {})
        fields_ok = all(pf.get(k) == v for k, v in exp_f.items()) if exp_f else None
        is_exact = predicted == expected and not fell_back
        exact += int(is_exact)
        errors += int(fell_back)
        db.add(EvalResult(run_id=run.id, item_id=item["id"], language_pair=item["lang"], text=item["text"],
                          expected_intents=expected, predicted_intents=predicted, exact_match=is_exact,
                          expected_fields=exp_f, predicted_fields=pf, fields_match=fields_ok, latency_ms=latency,
                          error="; ".join(res.notes)[:200] if fell_back else "", tags=item.get("tags", [])))
    run.exact_match_count, run.error_count = exact, errors
    run.status, run.finished_at = "DONE", utcnow()


def summary(db: Session, run: EvalRun) -> dict[str, Any]:
    results = db.scalars(select(EvalResult).where(EvalResult.run_id == run.id).order_by(EvalResult.item_id)).all()
    by_lang: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "exact": 0, "fields_n": 0, "fields_ok": 0})
    by_intent: dict[str, dict[str, int]] = defaultdict(lambda: {"support": 0, "tp": 0, "fp": 0})
    latencies = []
    for r in results:
        lang = by_lang[r.language_pair]
        lang["n"] += 1
        lang["exact"] += int(r.exact_match)
        if r.fields_match is not None:
            lang["fields_n"] += 1
            lang["fields_ok"] += int(r.fields_match)
        exp, pred = set(r.expected_intents), set(r.predicted_intents)
        for i in exp:
            by_intent[i]["support"] += 1
            by_intent[i]["tp"] += int(i in pred)
        for i in pred - exp:
            by_intent[i]["fp"] += 1
        latencies.append(r.latency_ms)
    latencies.sort()
    return {
        "run": {"id": str(run.id), "provider": run.provider, "model": run.model, "corpus_version": run.corpus_version,
                "status": run.status, "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "items": len(results), "exact_match": run.exact_match_count, "fallbacks": run.error_count},
        "by_language": [{"language_pair": k, **v,
                         "exact_rate": round(v["exact"] / v["n"], 3) if v["n"] else None,
                         "fields_rate": round(v["fields_ok"] / v["fields_n"], 3) if v["fields_n"] else None}
                        for k, v in sorted(by_lang.items())],
        "by_intent": [{"intent": k, **v, "recall": round(v["tp"] / v["support"], 3) if v["support"] else None,
                       "precision": round(v["tp"] / (v["tp"] + v["fp"]), 3) if (v["tp"] + v["fp"]) else None}
                      for k, v in sorted(by_intent.items())],
        "latency_ms": {"median": latencies[len(latencies) // 2] if latencies else None,
                       "p90": latencies[int(0.9 * (len(latencies) - 1))] if latencies else None},
        "items": [{"id": r.item_id, "lang": r.language_pair, "text": r.text, "expected": r.expected_intents,
                   "predicted": r.predicted_intents, "exact": r.exact_match, "fields_match": r.fields_match,
                   "expected_fields": r.expected_fields, "predicted_fields": r.predicted_fields,
                   "error": r.error, "tags": r.tags, "latency_ms": r.latency_ms} for r in results],
    }
