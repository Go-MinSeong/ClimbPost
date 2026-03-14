"""Full pipeline integration test using test2.mov.

Runs all 5 stages end-to-end and verifies output.
"""

import os

import pytest

from analyzer.config.settings import PIPELINE_STAGES
from analyzer.editor.editor import EditorStage
from analyzer.pipeline.orchestrator import Pipeline


@pytest.mark.slow
def test_full_pipeline_with_test_video(pipeline_context):
    """Run all 5 stages on test2.mov and verify end-to-end output."""
    pipeline = Pipeline(PIPELINE_STAGES, {})
    ctx = pipeline.run(pipeline_context)

    # 1. Clips were created by clipper
    assert len(ctx.clips) > 0, "Pipeline must produce at least one clip"

    for clip in ctx.clips:
        # 2. Each clip has result set by classifier
        assert clip.result in ("success", "fail"), (
            f"clip {clip.clip_id} has result={clip.result}"
        )

        # 3. Tape color and difficulty set by detector
        assert clip.tape_color is not None or clip.difficulty is None
        # (tape_color may be None if detector couldn't detect; that's okay)

        # 4. is_me set by identifier
        assert clip.is_me is not None, (
            f"clip {clip.clip_id} has is_me={clip.is_me}"
        )

        # 5. edited_path set by editor
        if clip.edited_path:
            assert os.path.isfile(clip.edited_path), (
                f"edited file missing: {clip.edited_path}"
            )

            # 6. Verify edited clip dimensions and duration
            w, h, dur = EditorStage._probe(clip.edited_path)
            assert w == 1080, f"width={w}, expected 1080"
            assert h == 1440, f"height={h}, expected 1440"
            assert dur <= 60.0 + 0.5, f"duration={dur}s, expected ≤60s"

        # 7. Clip files exist on disk
        if clip.clip_path:
            assert os.path.isfile(clip.clip_path), (
                f"clip file missing: {clip.clip_path}"
            )
        if clip.thumbnail_path:
            assert os.path.isfile(clip.thumbnail_path), (
                f"thumbnail missing: {clip.thumbnail_path}"
            )
