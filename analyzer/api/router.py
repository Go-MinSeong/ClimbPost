from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from analyzer.api.jobs import AnalyzeRequest, job_queue

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/jobs", status_code=202)
async def create_job(req: AnalyzeRequest) -> dict:
    state = await job_queue.submit(req)
    return {
        "job_id": state.job_id,
        "status": state.status,
        "created_at": state.created_at.isoformat() + "Z",
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    state = job_queue.get_status(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": state.job_id,
        "session_id": state.session_id,
        "status": state.status,
        "progress_pct": state.progress_pct,
        "current_stage": state.current_stage,
        "stages_completed": state.stages_completed,
        "created_at": state.created_at.isoformat() + "Z",
        "started_at": state.started_at.isoformat() + "Z" if state.started_at else None,
        "error": state.error,
    }


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str) -> dict:
    state = job_queue.get_status(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if state.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={"detail": "Job not completed yet", "status": state.status},
        )
    result = state.result
    return {
        "job_id": state.job_id,
        "session_id": state.session_id,
        "clips": [clip.model_dump() for clip in result.clips],
        "elapsed_sec": result.elapsed_sec,
    }


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict:
    state = job_queue.get_status(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job not found")
    cancelled = await job_queue.cancel(job_id)
    return {"cancelled": cancelled}
