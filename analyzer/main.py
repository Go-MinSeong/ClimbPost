from __future__ import annotations

from fastapi import FastAPI
from analyzer.api.router import router
from analyzer.api.jobs import job_queue


def _check_gpu() -> tuple[bool, str]:
    try:
        import torch
        if torch.cuda.is_available():
            return True, torch.cuda.get_device_name(0)
    except ImportError:
        pass
    try:
        import subprocess
        result = subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
        if result.returncode == 0:
            return True, "unknown"
    except Exception:
        pass
    return False, ""


app = FastAPI(title="ClimbPost Analyzer")
app.include_router(router)


@app.on_event("startup")
async def startup() -> None:
    await job_queue.start()


@app.get("/health")
async def health() -> dict:
    gpu_available, gpu_name = _check_gpu()

    # Find active job
    active_job = None
    for job_id, state in job_queue._jobs.items():
        if state.status == "processing":
            active_job = job_id
            break

    return {
        "status": "ok",
        "gpu": gpu_available,
        "gpu_name": gpu_name if gpu_available else None,
        "queue_size": job_queue._queue.qsize(),
        "active_job": active_job,
    }
