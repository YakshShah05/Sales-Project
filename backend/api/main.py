import os
import uuid
import asyncio
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from models.schemas import (
    ProspectEvent, ProspectScore, FeedbackPayload,
    TaskStatus, HumanReviewDecision
)
from tasks.signal_tasks import (
    collect_firmographic_signals,
    collect_intent_signals,
    collect_engagement_signals,
    collect_social_signals,
    collect_historical_signals,
)
from graph.scoring_graph import run_scoring_graph
from rag.pipeline import ingest_document, seed_knowledge_base
from api.store import (
    save_prospect, get_prospect, list_prospects,
    save_feedback, list_feedback,
    add_to_review_queue, get_review_queue, resolve_review
)

UPLOAD_PATH = os.getenv("UPLOAD_PATH", "/app/data/uploads")
Path(UPLOAD_PATH).mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Sales MAS API",
    description="Multi-Agent System for Sales & Marketing Prospect Scoring",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    """Seed knowledge base on startup."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, seed_knowledge_base)


@app.get("/")
async def root():
    return {"status": "running", "service": "Sales MAS API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/prospects/ingest", response_model=dict, tags=["Prospects"])
async def ingest_prospect(event: ProspectEvent, background_tasks: BackgroundTasks):
    """
    Receive a prospect event and trigger the full parallel scoring pipeline.
    Returns immediately with task IDs — non-blocking.
    """
    prospect_data = event.model_dump()
    prospect_data["timestamp"] = prospect_data["timestamp"].isoformat()

    background_tasks.add_task(_run_pipeline_background, prospect_data)

    return {
        "prospect_id": event.prospect_id,
        "status": "pipeline_started",
        "message": "Parallel signal collection triggered",
    }


async def _run_pipeline_background(prospect_data: dict):
    """Run the full pipeline in a background thread to avoid blocking."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_pipeline_sync, prospect_data)


def _run_pipeline_sync(prospect_data: dict):
    """Synchronous pipeline: parallel Celery tasks → LangGraph → store result."""
    from celery import group

    try:
        task_group = group(
            collect_firmographic_signals.s(prospect_data),
            collect_intent_signals.s(prospect_data),
            collect_engagement_signals.s(prospect_data),
            collect_social_signals.s(prospect_data),
            collect_historical_signals.s(prospect_data),
        )

        result = task_group.apply()
        results = result.get(timeout=30, propagate=False)

        keys = ["firmographic", "intent", "engagement", "social", "historical"]
        signals = {}
        for i, r in enumerate(results):
            if r and not isinstance(r, Exception):
                signals[keys[i]] = r
            else:
                signals[keys[i]] = {"signal_strength": 0, "note": "agent_unavailable"}

        strengths = [v.get("signal_strength", 0) for v in signals.values()]
        signals["composite_signal_score"] = sum(strengths) / len(strengths) if strengths else 0

        final_state = run_scoring_graph(prospect_data, signals)

        score_data = {
            "prospect_id": prospect_data["prospect_id"],
            "company_name": prospect_data["company_name"],
            "contact_name": prospect_data["contact_name"],
            "email": prospect_data["email"],
            "score": final_state.get("score", 0),
            "grade": final_state.get("grade", "D"),
            "rationale": final_state.get("rationale", ""),
            "recommended_action": final_state.get("recommended_action", ""),
            "signals": signals,
            "rag_context": final_state.get("rag_context", ""),
            "requires_human_review": final_state.get("requires_human_review", False),
            "routing_decision": final_state.get("routing_decision", ""),
            "created_at": datetime.utcnow().isoformat(),
        }

        save_prospect(prospect_data["prospect_id"], score_data)

        if score_data["requires_human_review"]:
            add_to_review_queue(prospect_data["prospect_id"], score_data)

    except Exception as e:
        error_data = {
            "prospect_id": prospect_data.get("prospect_id"),
            "company_name": prospect_data.get("company_name"),
            "contact_name": prospect_data.get("contact_name"),
            "email": prospect_data.get("email"),
            "score": 0,
            "grade": "D",
            "rationale": f"Pipeline error: {str(e)}",
            "recommended_action": "Manual review required",
            "signals": {},
            "requires_human_review": True,
            "routing_decision": "human_review",
            "created_at": datetime.utcnow().isoformat(),
        }
        save_prospect(prospect_data["prospect_id"], error_data)


@app.get("/prospects", response_model=list, tags=["Prospects"])
async def get_prospects(limit: int = 50):
    """Get all scored prospects, ranked by score descending."""
    return list_prospects(limit=limit)


@app.get("/prospects/{prospect_id}", tags=["Prospects"])
async def get_prospect_detail(prospect_id: str):
    """Get a single prospect's full scoring detail."""
    data = get_prospect(prospect_id)
    if not data:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return data


@app.post("/prospects/score/sync", tags=["Prospects"])
async def score_prospect_sync(event: ProspectEvent):
    """
    Synchronous scoring endpoint — runs full pipeline and returns result immediately.
    Slower than /ingest but returns complete score in one call.
    """
    prospect_data = event.model_dump()
    prospect_data["timestamp"] = prospect_data["timestamp"].isoformat()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_pipeline_sync, prospect_data)

    result = get_prospect(prospect_data["prospect_id"])
    if not result:
        raise HTTPException(status_code=500, detail="Pipeline failed")
    return result


@app.post("/documents/upload", tags=["Documents"])
async def upload_document(
    file: UploadFile = File(...),
    prospect_id: str = Form(...),
):
    """
    Upload a document for RAG ingestion.
    Automatically routes to text or OCR pipeline based on file type.
    Both pipelines can process simultaneously.
    """
    dest = os.path.join(UPLOAD_PATH, f"{prospect_id}_{file.filename}")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        ingest_document,
        dest,
        {"prospect_id": prospect_id, "filename": file.filename},
    )

    return {
        "status": "indexed",
        "filename": file.filename,
        "pipeline": result.get("modality"),
        "chunks_indexed": result.get("chunks_indexed"),
        "ocr_preview": result.get("ocr_text_preview"),
    }


@app.post("/feedback", tags=["Feedback"])
async def record_feedback(payload: FeedbackPayload):
    """Record deal outcome to improve future scoring."""
    save_feedback(payload.model_dump())
    prospect = get_prospect(payload.prospect_id)
    if prospect:
        prospect["outcome"] = payload.outcome
        prospect["outcome_notes"] = payload.notes
        save_prospect(payload.prospect_id, prospect)
    return {"status": "feedback_recorded", "outcome": payload.outcome}


@app.get("/feedback", tags=["Feedback"])
async def get_feedback():
    """List all recorded feedback for analysis."""
    return list_feedback()


@app.get("/review/queue", tags=["Human Review"])
async def get_review_queue_endpoint():
    """Get all prospects pending human review (borderline scores)."""
    return get_review_queue()


@app.post("/review/decide", tags=["Human Review"])
async def human_review_decision(decision: HumanReviewDecision):
    """Submit a human review decision for a borderline prospect."""
    prospect = get_prospect(decision.prospect_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    prospect["human_reviewed"] = True
    prospect["reviewer_approved"] = decision.approved
    prospect["reviewer_notes"] = decision.reviewer_notes
    prospect["requires_human_review"] = False

    if decision.approved:
        prospect["routing_decision"] = "rep_notify"
        prospect["recommended_action"] = decision.override_action or prospect["recommended_action"]
    else:
        prospect["routing_decision"] = "nurture"

    save_prospect(decision.prospect_id, prospect)
    resolve_review(decision.prospect_id)

    return {"status": "review_complete", "routing": prospect["routing_decision"]}


@app.get("/stats", tags=["Analytics"])
async def get_stats():
    """Pipeline statistics and score distribution."""
    prospects = list_prospects(limit=1000)
    if not prospects:
        return {"total": 0}

    scores = [p.get("score", 0) for p in prospects]
    grades = [p.get("grade", "D") for p in prospects]

    return {
        "total_prospects": len(prospects),
        "avg_score": round(sum(scores) / len(scores), 1),
        "grade_distribution": {
            g: grades.count(g) for g in ["A", "B", "C", "D"]
        },
        "pending_review": len(get_review_queue()),
        "high_priority": sum(1 for s in scores if s >= 70),
    }
