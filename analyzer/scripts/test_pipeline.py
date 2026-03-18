"""Stages 1–4 파이프라인 전체 테스트 — 모든 영상을 단일 Context로 통합 처리.

Stage 2 (Identifier)가 모든 영상의 클립을 한꺼번에 보고 '나'를 식별해야
올바른 클러스터링이 가능. 영상별 별도 Context는 성능 저하의 원인임.

컨테이너 안에서 실행:
    python -m analyzer.scripts.test_pipeline

결과:
    /data/storage/test-pipeline-<ts>/stage{1,2,3,4}_result.json
    /data/storage/test-pipeline-<ts>/report.html   (브라우저 열람 가능)
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
SESSION_ID = f"test-pipeline-{int(time.time())}"

TEST_VIDEOS = [
    "/data/test-data/data-1.mov",
    "/data/test-data/data-2.MOV",
    "/data/test-data/data-3.MOV",
]

COLOR_MAP = {
    "mapping": {
        "노랑": "V0-V1", "초록": "V2-V3", "파랑": "V4-V5",
        "빨강": "V6-V7", "검정": "V8+",
    }
}


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


def save_stage_result(
    session_dir: str, stage: int, context: PipelineContext, elapsed: float
) -> None:
    data = {
        "stage": stage,
        "elapsed_sec": round(elapsed, 2),
        "clip_count": len(context.clips),
        "me_count": sum(1 for c in context.clips if c.is_me),
        "clips": clips_to_dict(context),
    }
    path = os.path.join(session_dir, f"stage{stage}_result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Saved stage %d → %s", stage, path)


def print_stage(stage: int, context: PipelineContext, elapsed: float) -> None:
    me = sum(1 for c in context.clips if c.is_me)
    print(f"\n  [Stage {stage}]  {len(context.clips)} clips  ({me} is_me)  {elapsed:.1f}s")
    for c in context.clips:
        me_mark = "✓" if c.is_me else "✗"
        thumb = "📷" if c.thumbnail_path and os.path.exists(c.thumbnail_path) else "  "
        src = c.raw_video_id.replace("rv-", "")[:10]
        print(
            f"    {thumb} [{src}] {c.clip_id[:8]}  me={me_mark}"
            f"  {c.start_time:.0f}–{c.end_time:.0f}s"
            f"  result={c.result or '-':<7}"
            f"  tape={c.tape_color or '-':<4}"
            f"  diff={c.difficulty or '-'}"
        )


def generate_html_report(
    context: PipelineContext,
    session_dir: str,
    timings: dict[int, float],
) -> str:
    clips = context.clips
    me_clips = [c for c in clips if c.is_me]

    rows = []
    for c in clips:
        thumb_rel = ""
        if c.thumbnail_path and os.path.exists(c.thumbnail_path):
            thumb_rel = os.path.relpath(c.thumbnail_path, session_dir)

        me_cls = "is-me" if c.is_me else "not-me"
        me_badge = '<span class="badge me">나</span>' if c.is_me else '<span class="badge other">타인</span>'
        result_cls = c.result or ""
        result_label = {"success": "성공 ✓", "fail": "실패 ✗"}.get(c.result or "", "—")

        thumb_html = (
            f'<img src="{thumb_rel}" alt="thumb">'
            if thumb_rel else
            '<div class="no-thumb">썸네일 없음</div>'
        )

        src = c.raw_video_id.replace("rv-", "")
        rows.append(f"""
        <div class="clip {me_cls}">
          {thumb_html}
          <div class="meta">
            {me_badge}
            <div class="src">{src}</div>
            <div class="time">{c.start_time:.1f}s – {c.end_time:.1f}s &nbsp;({c.duration_sec:.0f}s)</div>
            <div class="result {result_cls}">{result_label}</div>
            <div class="tape">테이프: {c.tape_color or '—'} &nbsp; 난이도: {c.difficulty or '—'}</div>
            <div class="id">{c.clip_id[:12]}</div>
          </div>
        </div>""")

    timing_rows = "".join(
        f"<tr><td>Stage {s}</td><td>{t:.1f}s</td></tr>"
        for s, t in sorted(timings.items())
    )

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>ClimbPost Pipeline Report — {SESSION_ID}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; margin: 0; padding: 16px; }}
  h1 {{ color: #FF6B35; margin-bottom: 4px; }}
  h2 {{ color: #aaa; font-size: 14px; font-weight: normal; margin-top: 0; }}
  .summary {{ display: flex; gap: 24px; margin: 16px 0; flex-wrap: wrap; }}
  .stat {{ background: #252540; border-radius: 8px; padding: 12px 20px; }}
  .stat .n {{ font-size: 28px; font-weight: bold; color: #FF6B35; }}
  .stat .lbl {{ font-size: 12px; color: #888; }}
  table {{ border-collapse: collapse; background: #252540; border-radius: 8px; overflow: hidden; margin: 8px 0; }}
  td, th {{ padding: 6px 14px; font-size: 13px; border-bottom: 1px solid #333; }}
  th {{ color: #888; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 14px; padding: 8px 0; }}
  .clip {{ width: 190px; border-radius: 10px; overflow: hidden; border: 3px solid; }}
  .clip.is-me {{ border-color: #4CAF50; box-shadow: 0 0 10px rgba(76,175,80,0.4); }}
  .clip.not-me {{ border-color: #444; opacity: 0.65; }}
  .clip img {{ width: 100%; display: block; object-fit: cover; height: 140px; }}
  .no-thumb {{ width: 100%; height: 140px; background: #333; display: flex; align-items: center;
               justify-content: center; font-size: 12px; color: #666; }}
  .meta {{ background: #1e1e35; padding: 8px 10px; font-size: 11px; line-height: 1.7; }}
  .badge {{ display: inline-block; border-radius: 4px; padding: 1px 7px; font-size: 11px; font-weight: bold; margin-bottom: 4px; }}
  .badge.me {{ background: #4CAF50; color: #fff; }}
  .badge.other {{ background: #555; color: #bbb; }}
  .src {{ color: #888; font-size: 10px; }}
  .time {{ color: #ccc; }}
  .result.success {{ color: #4CAF50; font-weight: bold; }}
  .result.fail {{ color: #F44336; font-weight: bold; }}
  .tape {{ color: #aaa; }}
  .id {{ color: #555; font-size: 10px; font-family: monospace; }}
  .section-title {{ margin-top: 24px; color: #FF6B35; font-size: 16px; font-weight: bold; }}
</style>
</head>
<body>
<h1>ClimbPost Pipeline Report</h1>
<h2>{SESSION_ID}</h2>

<div class="summary">
  <div class="stat"><div class="n">{len(TEST_VIDEOS)}</div><div class="lbl">입력 영상</div></div>
  <div class="stat"><div class="n">{len(clips)}</div><div class="lbl">전체 클립</div></div>
  <div class="stat"><div class="n">{len(me_clips)}</div><div class="lbl">나의 클립</div></div>
  <div class="stat"><div class="n">{sum(1 for c in me_clips if c.result=='success')}</div><div class="lbl">성공</div></div>
  <div class="stat"><div class="n">{sum(1 for c in me_clips if c.result=='fail')}</div><div class="lbl">실패</div></div>
</div>

<table>
  <tr><th>Stage</th><th>소요 시간</th></tr>
  {timing_rows}
</table>

<div class="section-title">전체 클립 (초록 테두리 = 나, 흐린 = 타인)</div>
<div class="grid">{''.join(rows)}</div>

</body></html>"""

    report_path = os.path.join(session_dir, "report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("HTML report → %s", report_path)
    return report_path


def main() -> None:
    print("\n" + "=" * 70)
    print(f"  ClimbPost Pipeline Test  —  Stages 1–4  —  {len(TEST_VIDEOS)} videos")
    print("  ※ 모든 영상을 단일 Context로 통합 처리 (Stage2 전체 집계)")
    print("=" * 70)

    session_dir = os.path.join(STORAGE_ROOT, SESSION_ID)
    os.makedirs(session_dir, exist_ok=True)
    logger.info("Session dir: %s", session_dir)

    # --- Build single unified context with ALL videos ---
    raw_videos = []
    for vp in TEST_VIDEOS:
        if not os.path.exists(vp):
            logger.warning("Video not found, skipping: %s", vp)
            continue
        dur = probe_duration(vp)
        name = os.path.basename(vp)
        logger.info("Video: %s  %.1fs", name, dur)
        raw_videos.append(RawVideoInfo(
            raw_video_id=f"rv-{name}",
            file_path=vp,
            duration_sec=dur,
        ))

    context = PipelineContext(
        session_id=SESSION_ID,
        gym_id="gym_test",
        color_map=COLOR_MAP,
        raw_videos=raw_videos,
        storage_root=STORAGE_ROOT,
    )

    # --- Load ONNX sessions once ---
    logger.info("Loading ONNX sessions...")
    stages = {
        "clipper":    ClipperStage({}),
        "identifier": IdentifierStage({}),
        "classifier": ClassifierStage({}),
        "detector":   DetectorStage({}),
    }
    logger.info("All sessions ready.")

    timings: dict[int, float] = {}

    # Stage 1
    t0 = time.perf_counter()
    context = stages["clipper"].process(context)
    timings[1] = time.perf_counter() - t0
    save_stage_result(session_dir, 1, context, timings[1])
    print_stage(1, context, timings[1])

    if not context.clips:
        logger.warning("No clips extracted — aborting.")
        return

    # Stage 2
    t0 = time.perf_counter()
    context = stages["identifier"].process(context)
    timings[2] = time.perf_counter() - t0
    save_stage_result(session_dir, 2, context, timings[2])
    print_stage(2, context, timings[2])

    # Stage 3
    t0 = time.perf_counter()
    context = stages["classifier"].process(context)
    timings[3] = time.perf_counter() - t0
    save_stage_result(session_dir, 3, context, timings[3])
    print_stage(3, context, timings[3])

    # Stage 4
    t0 = time.perf_counter()
    context = stages["detector"].process(context)
    timings[4] = time.perf_counter() - t0
    save_stage_result(session_dir, 4, context, timings[4])
    print_stage(4, context, timings[4])

    # HTML report
    report = generate_html_report(context, session_dir, timings)

    total = sum(timings.values())
    print(f"\n{'=' * 70}")
    print(f"  완료  —  총 {total:.0f}s")
    print(f"  결과 디렉토리: {session_dir}")
    print(f"  HTML 리포트  : {report}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
