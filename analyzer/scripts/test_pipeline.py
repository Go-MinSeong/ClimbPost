"""Stages 1–4 파이프라인 전체 테스트 — 3개 영상 동시 처리.

컨테이너 안에서 실행:
    python -m analyzer.scripts.test_pipeline

각 영상에 대해 stage별 결과를 JSON으로 저장:
    /data/storage/test-pipeline-<ts>/<video>/stage{1,2,3,4}_result.json
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time

from analyzer.clipper.clipper import ClipperStage
from analyzer.classifier.classifier import ClassifierStage
from analyzer.detector.detector import DetectorStage
from analyzer.identifier.identifier import IdentifierStage
from analyzer.pipeline.context import PipelineContext, RawVideoInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_pipeline")

STORAGE_ROOT = os.environ.get("STORAGE_ROOT", "/data/storage")
SESSION_BASE = f"test-pipeline-{int(time.time())}"

TEST_VIDEOS = [
    "/data/test-data/data-1.mov",
    "/data/test-data/data-2.MOV",
    "/data/test-data/data-3.MOV",
]

COLOR_MAP = {"mapping": {"노랑": "V0-V1", "초록": "V2-V3", "파랑": "V4-V5", "빨강": "V6-V7", "검정": "V8+"}}


def probe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip()) if r.returncode == 0 else 0.0


def clips_to_dict(context: PipelineContext) -> list[dict]:
    return [
        {
            "clip_id": c.clip_id,
            "raw_video_id": c.raw_video_id,
            "start_time": round(c.start_time, 2),
            "end_time": round(c.end_time, 2),
            "duration_sec": round(c.duration_sec, 2),
            "clip_path": c.clip_path,
            "thumbnail_path": c.thumbnail_path,
            "is_me": c.is_me,
            "result": c.result,
            "tape_color": c.tape_color,
            "difficulty": c.difficulty,
        }
        for c in context.clips
    ]


def save_stage_result(session_dir: str, stage: int, context: PipelineContext, elapsed: float) -> None:
    data = {
        "stage": stage,
        "elapsed_sec": round(elapsed, 2),
        "clip_count": len(context.clips),
        "clips": clips_to_dict(context),
    }
    path = os.path.join(session_dir, f"stage{stage}_result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Saved stage %d result → %s", stage, path)


def print_summary(video_name: str, stage: int, context: PipelineContext, elapsed: float) -> None:
    clips = context.clips
    print(f"\n  [Stage {stage}] {video_name}  ({elapsed:.1f}s)")
    for c in clips:
        me = "✓" if c.is_me else "✗"
        thumb = "📷" if c.thumbnail_path and os.path.exists(c.thumbnail_path) else "  "
        print(
            f"    {thumb} clip={c.clip_id[:8]}  is_me={me}"
            f"  {c.start_time:.1f}–{c.end_time:.1f}s"
            f"  result={c.result or '-'}"
            f"  tape={c.tape_color or '-'}"
            f"  diff={c.difficulty or '-'}"
        )


def run_video(video_path: str, stages: dict, session_dir: str) -> None:
    video_name = os.path.basename(video_path)
    vid_dir = os.path.join(session_dir, video_name)
    os.makedirs(vid_dir, exist_ok=True)

    duration = probe_duration(video_path)
    logger.info("=== %s  (%.1fs) ===", video_name, duration)

    context = PipelineContext(
        session_id=f"{SESSION_BASE}-{video_name.split('.')[0]}",
        gym_id="gym_test",
        color_map=COLOR_MAP,
        raw_videos=[RawVideoInfo(
            raw_video_id=f"rv-{video_name}",
            file_path=video_path,
            duration_sec=duration,
        )],
        storage_root=STORAGE_ROOT,
    )

    # Stage 1: Clipper
    t0 = time.perf_counter()
    context = stages["clipper"].process(context)
    e1 = time.perf_counter() - t0
    save_stage_result(vid_dir, 1, context, e1)
    print_summary(video_name, 1, context, e1)

    if not context.clips:
        logger.warning("No clips found for %s, skipping remaining stages", video_name)
        return

    # Stage 2: Identifier
    t0 = time.perf_counter()
    context = stages["identifier"].process(context)
    e2 = time.perf_counter() - t0
    save_stage_result(vid_dir, 2, context, e2)
    print_summary(video_name, 2, context, e2)

    # Stage 3: Classifier
    t0 = time.perf_counter()
    context = stages["classifier"].process(context)
    e3 = time.perf_counter() - t0
    save_stage_result(vid_dir, 3, context, e3)
    print_summary(video_name, 3, context, e3)

    # Stage 4: Detector
    t0 = time.perf_counter()
    context = stages["detector"].process(context)
    e4 = time.perf_counter() - t0
    save_stage_result(vid_dir, 4, context, e4)
    print_summary(video_name, 4, context, e4)

    logger.info("Total for %s: Stage1=%.1fs Stage2=%.1fs Stage3=%.1fs Stage4=%.1fs",
                video_name, e1, e2, e3, e4)


def main() -> None:
    print("\n" + "=" * 70)
    print(f"  ClimbPost Pipeline Test  —  Stages 1–4  —  {len(TEST_VIDEOS)} videos")
    print("=" * 70)

    session_dir = os.path.join(STORAGE_ROOT, SESSION_BASE)
    os.makedirs(session_dir, exist_ok=True)
    logger.info("Session dir: %s", session_dir)

    # Load all stages once (ONNX sessions initialised here)
    logger.info("Loading ONNX sessions...")
    stages = {
        "clipper":    ClipperStage({}),
        "identifier": IdentifierStage({}),
        "classifier": ClassifierStage({}),
        "detector":   DetectorStage({}),
    }
    logger.info("All sessions ready.")

    t_total = time.perf_counter()
    for vp in TEST_VIDEOS:
        if not os.path.exists(vp):
            logger.warning("Video not found: %s", vp)
            continue
        run_video(vp, stages, session_dir)

    total = time.perf_counter() - t_total
    print(f"\n{'=' * 70}")
    print(f"  All done  —  {total:.1f}s total")
    print(f"  Results: {session_dir}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
