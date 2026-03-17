"""Stage 1 단독 실행 테스트 스크립트.

컨테이너 안에서 실행:
    python -m analyzer.scripts.test_stage1

필요 조건:
    - analyzer/models/yolo26n.onnx 존재
    - /data/test-data/data-1.mov 존재 (docker-compose.dev.yml 볼륨 마운트)
"""

from __future__ import annotations

import logging
import os
import time

from analyzer.clipper.clipper import ClipperStage
from analyzer.pipeline.context import PipelineContext, RawVideoInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_stage1")

VIDEO_PATH = os.environ.get("TEST_VIDEO", "/data/test-data/data-1.mov")
STORAGE_ROOT = os.environ.get("STORAGE_ROOT", "/data/storage")
SESSION_ID = "test-stage1-" + str(int(time.time()))


def main() -> None:
    logger.info("=== Stage 1 (Clipper) Test ===")
    logger.info("Video   : %s", VIDEO_PATH)
    logger.info("Storage : %s", STORAGE_ROOT)
    logger.info("Session : %s", SESSION_ID)

    # video duration via ffprobe
    import subprocess
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", VIDEO_PATH],
        capture_output=True, text=True,
    )
    duration = float(probe.stdout.strip()) if probe.returncode == 0 else 0.0
    logger.info("Duration: %.1fs", duration)

    context = PipelineContext(
        session_id=SESSION_ID,
        gym_id="gym_test",
        color_map={"mapping": {}},
        raw_videos=[
            RawVideoInfo(
                raw_video_id="rv-test-001",
                file_path=VIDEO_PATH,
                duration_sec=duration,
            )
        ],
        storage_root=STORAGE_ROOT,
    )

    logger.info("Loading ClipperStage (ONNX session init)...")
    stage = ClipperStage(config={})

    logger.info("Running Stage 1...")
    t0 = time.perf_counter()
    context = stage.process(context)
    elapsed = time.perf_counter() - t0

    # ---- Results ----
    print("\n" + "=" * 60)
    print(f"  Stage 1 완료  —  {elapsed:.1f}초 소요")
    print("=" * 60)
    print(f"  추출된 클립 수: {len(context.clips)}")
    print()
    for i, clip in enumerate(context.clips, 1):
        print(f"  [{i}] clip_id   : {clip.clip_id}")
        print(f"       구간      : {clip.start_time:.1f}s – {clip.end_time:.1f}s  ({clip.duration_sec:.1f}s)")
        print(f"       파일      : {clip.clip_path}")
        exists = clip.clip_path and os.path.exists(clip.clip_path)
        size_kb = os.path.getsize(clip.clip_path) // 1024 if exists else 0
        print(f"       파일 존재 : {'✓' if exists else '✗'}  ({size_kb} KB)")
        print()

    if not context.clips:
        print("  (클립 없음 — 등반 구간 미검출 또는 필터링됨)\n")
    print("=" * 60)


if __name__ == "__main__":
    main()
