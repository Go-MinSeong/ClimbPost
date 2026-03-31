"""Stage 2 — Identifier: multi-frame OSNet re-ID based clip identification.

Strategy
--------
1. Split each clip into 3 temporal segments (0-33%, 33-66%, 66-100%).
2. Open VideoCapture ONCE per clip and seek between segments.
3. In each segment find the best frame (argmax conf×area, center_y < threshold)
   using cap.grab() to skip non-sample frames without decoding.
4. Crop the person bbox from each best frame, save 3 thumbnails.
5. Run OSNet re-ID on all 3 crops in a SINGLE batch call → [3, D] embeddings.
6. L2-normalise and average → single representative per clip.
7. Cluster representatives with DBSCAN (cosine distance).
8. Largest cluster = 'me'; those clips get is_me=True.
9. Annotate primary thumbnails with ME/other border.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import cv2
import numpy as np
from sklearn.cluster import DBSCAN

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import PipelineContext
from analyzer.pipeline.onnx_infer import (
    load_session,
    preprocess,
    preprocess_batch,
    preprocess_reid,
    postprocess_det,
)

logger = logging.getLogger(__name__)

_DET_MODEL_PATH = os.environ.get(
    "YOLO26N_ONNX",
    str(Path(__file__).resolve().parent.parent / "models" / "yolo26n.onnx"),
)
_REID_MODEL_PATH = os.environ.get(
    "OSNET_ONNX",
    str(Path(__file__).resolve().parent.parent / "models" / "osnet_x0_25.onnx"),
)

_DEFAULTS = {
    "sample_fps": 2,           # frames per second to sample within each segment
    "climb_threshold": 0.65,   # center_y < this → person in climbing zone
    "conf_threshold": 0.3,     # minimum detection confidence
    "min_area_frac": 0.005,    # bbox must be ≥ 0.5% of frame area
    "dbscan_eps": 0.35,        # cosine distance threshold
    "dbscan_min_samples": 1,
    "thumbnail_pad": 0.05,     # relative bbox expansion for crop
    "n_segments": 3,           # temporal segments per clip
}


class IdentifierStage(BaseStage):
    """Stage 2 — multi-frame OSNet re-ID + DBSCAN is_me identification."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._det_session = load_session(_DET_MODEL_PATH)
        self._reid_session = load_session(_REID_MODEL_PATH)
        inp = self._det_session.get_inputs()[0].shape
        self._infer_h = inp[2] if isinstance(inp[2], int) else 640
        self._infer_w = inp[3] if isinstance(inp[3], int) else 640

    @property
    def name(self) -> str:
        return "identifier"

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("identifier", {})}

        if not context.clips:
            logger.info("Identifier: no clips to process")
            return context

        thumb_dir = os.path.join(context.storage_root, context.session_id, "clips")
        os.makedirs(thumb_dir, exist_ok=True)

        features: list[np.ndarray | None] = []
        for clip in context.clips:
            if not clip.clip_path:
                logger.warning("Identifier: clip %s has no file, skipping", clip.clip_id)
                features.append(None)
                continue

            feat, primary_thumb = self._process_clip(clip.clip_path, thumb_dir, clip.clip_id, cfg)
            clip.thumbnail_path = primary_thumb
            features.append(feat)
            logger.info(
                "Identifier: clip %s → thumbnail=%s feat=%s",
                clip.clip_id,
                "✓" if primary_thumb and os.path.exists(primary_thumb) else "✗",
                "ok" if feat is not None else "none",
            )

        self._assign_is_me(context, features, cfg)
        self._annotate_thumbnails(context)
        return context

    # ------------------------------------------------------------------
    # Per-clip: single VideoCapture, 3-segment scan, batch OSNet
    # ------------------------------------------------------------------

    def _process_clip(
        self,
        clip_path: str,
        thumb_dir: str,
        clip_id: str,
        cfg: dict,
    ) -> tuple[np.ndarray | None, str | None]:
        """Open clip once, scan 3 segments, batch-embed crops, return (avg_emb, primary_thumb)."""
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            logger.error("Identifier: cannot open %s", clip_path)
            return None, None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames < 3:
            cap.release()
            return None, None

        sample_interval = max(1, int(fps / cfg["sample_fps"]))
        n_seg = cfg["n_segments"]
        seg_size = total_frames // n_seg
        segments = [
            (i * seg_size, min((i + 1) * seg_size - 1, total_frames - 1))
            for i in range(n_seg)
        ]

        crops: list[tuple[int, np.ndarray]] = []   # (seg_idx, crop_bgr)
        thumb_paths: list[str | None] = [None] * n_seg

        for seg_idx, (seg_start, seg_end) in enumerate(segments):
            best = _best_frame_in_segment(
                cap, seg_start, seg_end, sample_interval,
                self._det_session, self._infer_h, self._infer_w, cfg,
            )
            if best is None:
                continue
            frame, bbox = best
            crop = _crop_person(frame, bbox, cfg["thumbnail_pad"])
            if crop is None or crop.size == 0:
                continue
            thumb_path = os.path.join(thumb_dir, f"{clip_id}_thumb_{seg_idx}.jpg")
            cv2.imwrite(thumb_path, crop)
            thumb_paths[seg_idx] = thumb_path
            crops.append((seg_idx, crop))

        cap.release()

        primary_thumb = thumb_paths[1] or thumb_paths[0] or thumb_paths[2]

        if not crops:
            _save_middle_frame(clip_path, thumb_dir, clip_id)
            return None, os.path.join(thumb_dir, f"{clip_id}_thumb_1.jpg")

        # --- Batch OSNet: all crops in one session.run ---
        crop_list = [c for _, c in crops]
        reid_input = np.concatenate(
            [preprocess_reid(c) for c in crop_list], axis=0
        )  # [N, 3, 256, 128]
        embeddings = self._reid_session.run(
            None, {self._reid_session.get_inputs()[0].name: reid_input}
        )[0]  # [N, D]

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embeddings = embeddings / norms
        avg_emb = embeddings.mean(axis=0)
        avg_norm = np.linalg.norm(avg_emb)
        if avg_norm > 0:
            avg_emb /= avg_norm

        return avg_emb.astype(np.float32), primary_thumb

    # ------------------------------------------------------------------
    # is_me assignment via DBSCAN (cosine distance)
    # ------------------------------------------------------------------

    def _assign_is_me(
        self,
        context: PipelineContext,
        features: list[np.ndarray | None],
        cfg: dict,
    ) -> None:
        valid_idx = [i for i, f in enumerate(features) if f is not None]

        if len(valid_idx) == 0:
            for clip in context.clips:
                clip.is_me = True
            logger.warning("Identifier: no features extracted, marking all is_me=True")
            return

        if len(valid_idx) == 1:
            for clip in context.clips:
                clip.is_me = True
            logger.info("Identifier: single clip, marking is_me=True")
            return

        mat = np.array([features[i] for i in valid_idx], dtype=np.float32)

        labels = DBSCAN(
            eps=cfg["dbscan_eps"],
            min_samples=cfg["dbscan_min_samples"],
            metric="cosine",
        ).fit_predict(mat)

        unique = set(labels) - {-1}
        if not unique:
            for clip in context.clips:
                clip.is_me = True
            logger.warning("Identifier: all DBSCAN noise, marking all is_me=True")
            return

        # Score = (cluster size, video diversity) — prefer clips spanning multiple videos
        def cluster_score(lbl: int) -> tuple[int, int]:
            members = [valid_idx[j] for j, l in enumerate(labels) if l == lbl]
            return len(members), len({context.clips[i].raw_video_id for i in members})

        largest = max(unique, key=cluster_score)
        me_set = {valid_idx[j] for j, lbl in enumerate(labels) if lbl == largest}

        logger.info(
            "Identifier: %d cluster(s) found; largest=%d (%d/%d clips)",
            len(unique), largest, len(me_set), len(context.clips),
        )
        for i, clip in enumerate(context.clips):
            clip.is_me = i in me_set
            logger.info("Identifier: clip %s → is_me=%s", clip.clip_id, clip.is_me)

    # ------------------------------------------------------------------
    # Thumbnail annotation
    # ------------------------------------------------------------------

    @staticmethod
    def _annotate_thumbnails(context: PipelineContext) -> None:
        for clip in context.clips:
            if not clip.thumbnail_path or not os.path.exists(clip.thumbnail_path):
                continue
            img = cv2.imread(clip.thumbnail_path)
            if img is None:
                continue
            color = (74, 175, 74) if clip.is_me else (100, 100, 100)
            thickness = 6 if clip.is_me else 3
            h, w = img.shape[:2]
            cv2.rectangle(img, (0, 0), (w - 1, h - 1), color, thickness)

            src = clip.raw_video_id.replace("rv-", "")[:12]
            label = f"{src}  {clip.start_time:.0f}-{clip.end_time:.0f}s"
            cv2.rectangle(img, (0, h - 22), (w, h), (0, 0, 0), -1)
            cv2.putText(img, label, (4, h - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1, cv2.LINE_AA)

            me_label = "ME" if clip.is_me else "other"
            me_color = (74, 175, 74) if clip.is_me else (100, 100, 100)
            cv2.rectangle(img, (0, 0), (54, 22), (0, 0, 0), -1)
            cv2.putText(img, me_label, (4, 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, me_color, 1, cv2.LINE_AA)

            cv2.imwrite(clip.thumbnail_path, img)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _best_frame_in_segment(
    cap: cv2.VideoCapture,
    seg_start: int,
    seg_end: int,
    sample_interval: int,
    det_session,
    infer_h: int,
    infer_w: int,
    cfg: dict,
) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
    """Scan [seg_start, seg_end] using an open cap; grab() skips non-sample frames."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, seg_start)

    climb_thresh = cfg["climb_threshold"]
    min_area = cfg["min_area_frac"]
    conf_thresh = cfg["conf_threshold"]

    best_score = -1.0
    best_frame: np.ndarray | None = None
    best_bbox: tuple[int, int, int, int] | None = None

    frame_pos = seg_start
    while frame_pos <= seg_end:
        ret, frame = cap.read()
        if not ret:
            break

        fh, fw = frame.shape[:2]
        blob, r, pad = preprocess(frame, infer_h, infer_w)
        raw = det_session.run(None, {det_session.get_inputs()[0].name: blob})[0]
        dets = postprocess_det(raw, r, pad, (fh, fw), conf_thresh)

        for det in dets:
            x1, y1, x2, y2, conf = det[0], det[1], det[2], det[3], det[4]
            center_y = ((y1 + y2) / 2) / fh
            area_frac = (x2 - x1) * (y2 - y1) / (fw * fh)
            if center_y >= climb_thresh or area_frac < min_area:
                continue
            score = float(conf) * area_frac
            if score > best_score:
                best_score = score
                best_frame = frame.copy()
                best_bbox = (int(x1), int(y1), int(x2), int(y2))

        next_pos = frame_pos + sample_interval
        if next_pos > seg_end:
            break

        # Skip frames [frame_pos+1 .. next_pos-1] without decoding
        grabs = next_pos - (frame_pos + 1)
        for _ in range(grabs):
            if not cap.grab():
                return (best_frame, best_bbox) if best_frame is not None else None

        frame_pos = next_pos

    return (best_frame, best_bbox) if best_frame is not None else None


def _crop_person(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    pad_frac: float,
) -> np.ndarray | None:
    fh, fw = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return None
    pad_x = int((x2 - x1) * pad_frac)
    pad_y = int((y2 - y1) * pad_frac)
    crop = frame[max(0, y1 - pad_y):min(fh, y2 + pad_y),
                 max(0, x1 - pad_x):min(fw, x2 + pad_x)]
    return crop if crop.size > 0 else None


def _save_middle_frame(clip_path: str, thumb_dir: str, clip_id: str) -> None:
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(os.path.join(thumb_dir, f"{clip_id}_thumb_1.jpg"), frame)
    cap.release()
